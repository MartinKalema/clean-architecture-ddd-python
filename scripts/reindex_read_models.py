#!/usr/bin/env python
"""
Read-Model Reindex Worker

Rebuilds the Elasticsearch read models from PostgreSQL (the source of
truth) with zero downtime:

1. Creates a fresh timestamped physical index (books-20260704120000)
2. Registers it as a CDC dual-write target and waits for target discovery
3. Keyset-scans PostgreSQL in bounded transactions using versioned writes
4. Atomically swaps the read alias (books) to the new index
5. Removes the dual-write target and deletes old indices (unless --keep-old)

Use this to recover from read-model divergence (lost messages, bugs) or
to apply a mapping change. Searches keep hitting the old index until the
swap, then the new one — readers never see a partial index.

Usage:
    python scripts/reindex_read_models.py [--index books|patrons|loans|all] [--keep-old]

Environment variables:
    ETCD_HOST: etcd host (default: localhost)
    ETCD_PORT: etcd port (default: 2379)
"""
import argparse
import asyncio
import json
import math
import os
import sys
import time
from datetime import datetime
from typing import Any

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.composition.bootstrap import bootstrap_container
from src.composition.lifecycle import search_maintenance_resources
from src.composition.runtime_config import ProcessRole
from src.container import MaintenanceContainer
from src.infrastructure.adapters.catalog.book_model import BookModel
from src.infrastructure.adapters.lending.loan_model import LoanModel
from src.infrastructure.adapters.patron.patron_model import PatronModel
from src.infrastructure.adapters.reindex_lock import read_model_reindex_lock
from src.infrastructure.external.elasticsearch_client import ElasticsearchClient

MAPPINGS_DIR = os.path.join(PROJECT_ROOT, "deploy", "elasticsearch", "mappings")
BATCH_SIZE = 500

ALIASES: dict[str, Any] = {
    "books": BookModel,
    "patrons": PatronModel,
    "loans": LoanModel,
}


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy model row to a plain dict of column values."""
    data = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        data[column.name] = value
    return data


async def reindex_alias(
    alias: str,
    container: MaintenanceContainer,
    keep_old: bool,
    dual_write_grace_seconds: float = 2.0,
) -> None:
    """Rebuild one read model behind its alias."""
    logger = container.logger()
    es_client = container.elasticsearch_client()
    session_factory = async_sessionmaker(bind=container.postgresql().engine, expire_on_commit=False)

    # The CDC consumer owns the row -> document transforms; reuse them so a
    # rebuilt document is identical to a streamed one.
    sync_consumer = container.elasticsearch_sync_consumer()
    transform = {
        "books": sync_consumer.transform_book,
        "patrons": sync_consumer.transform_patron,
        "loans": sync_consumer.transform_loan,
    }[alias]

    with open(os.path.join(MAPPINGS_DIR, f"{alias}.json")) as f:
        body = json.load(f)

    old_indices = await es_client.get_alias_indices(alias)
    new_index = f"{alias}-{time.strftime('%Y%m%d%H%M%S')}-{time.time_ns() % 1_000_000:06d}"

    logger.info(f"Reindexing '{alias}': {old_indices or 'no current index'} -> {new_index}")
    model = ALIASES[alias]
    total = 0
    last_id = None
    try:
        await es_client.create_index(
            index=new_index,
            mappings=body["mappings"],
            settings=body.get("settings"),
        )

        # CDC clients cache target discovery for at most one second. Register
        # the target before reading any row and allow every instance to
        # refresh; from this point, changes are mirrored into new_index.
        await es_client.set_reindex_target(alias, new_index)
        await asyncio.sleep(dual_write_grace_seconds)

        while True:
            # One short transaction per batch avoids a long-lived MVCC
            # snapshot and keyset pagination remains O(n) as the table grows.
            async with session_factory() as session:
                statement = select(model).order_by(model.id).limit(BATCH_SIZE)
                if last_id is not None:
                    statement = statement.where(model.id > last_id)
                result = await session.execute(statement)
                rows = result.scalars().all()
                row_data = [_row_to_dict(row) for row in rows]

            if not row_data:
                break

            documents = [transform(row) for row in row_data]
            success, errors = await es_client.bulk_index(new_index, documents)
            if errors:
                raise RuntimeError(
                    f"{errors} documents failed to index into {new_index}; "
                    f"aborting before alias swap ('{alias}' still serves the old index)"
                )

            total += success
            last_id = row_data[-1]["id"]
            logger.info(f"  {alias}: indexed {total} documents")

        await es_client.refresh(new_index)
        await es_client.swap_alias(alias, new_index)
        logger.info(f"Alias '{alias}' swapped to {new_index} ({total} documents)")
        await es_client.clear_reindex_target(
            alias,
            expected_target=new_index,
        )
    except BaseException as error:
        # Cleanup is ownership scoped: never clear a target installed by some
        # other operator. Querying both aliases also handles ambiguous timeout
        # responses: retain the index if it became live, and remove our target
        # if registration succeeded before the response was lost.
        try:
            target_alias = f"{alias}{es_client.REINDEX_TARGET_SUFFIX}"
            target_indices = await es_client.get_alias_indices(target_alias)
            if new_index in target_indices:
                await es_client.clear_reindex_target(
                    alias,
                    expected_target=new_index,
                )
            serving_indices = await es_client.get_alias_indices(alias)
            if new_index not in serving_indices:
                await es_client.delete_index(new_index)
        except BaseException as cleanup_error:
            add_note = getattr(error, "add_note", None)
            if add_note is not None:
                add_note(f"Reindex cleanup was incomplete: {cleanup_error}")
        raise

    if keep_old:
        logger.info(f"Keeping old indices: {old_indices}")
        return

    for old_index in old_indices:
        if old_index != new_index:
            await es_client.delete_index(old_index)
            logger.info(f"Deleted old index: {old_index}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Elasticsearch read models from PostgreSQL")
    parser.add_argument("--index", choices=[*ALIASES, "all"], default="all")
    parser.add_argument("--keep-old", action="store_true", help="Do not delete the old physical indices")
    parser.add_argument(
        "--dual-write-grace-seconds",
        type=float,
        default=2.0,
        help="Wait for CDC instances to discover the temporary target (default: 2)",
    )
    args = parser.parse_args()
    minimum_grace = ElasticsearchClient.REINDEX_TARGET_CACHE_SECONDS
    if (
        not math.isfinite(args.dual_write_grace_seconds)
        or args.dual_write_grace_seconds < minimum_grace
    ):
        parser.error(
            "--dual-write-grace-seconds must be at least "
            f"{minimum_grace:.1f}s (the CDC target-discovery cache window)"
        )

    container = MaintenanceContainer()
    bootstrap_container(container, ProcessRole.MAINTENANCE)

    logger = container.logger()
    aliases = list(ALIASES) if args.index == "all" else [args.index]
    logger.info(f"Starting read-model reindex for: {aliases}")

    async with search_maintenance_resources(container) as (database, _):
        # One session-scoped PostgreSQL advisory lock fences the complete job,
        # including ``--index all``. A competing worker fails before it can
        # create an index or mutate the CDC target alias.
        async with read_model_reindex_lock(database.engine):
            for alias in aliases:
                await reindex_alias(
                    alias,
                    container,
                    keep_old=args.keep_old,
                    dual_write_grace_seconds=args.dual_write_grace_seconds,
                )
        logger.info("Reindex complete")


if __name__ == "__main__":
    asyncio.run(main())
