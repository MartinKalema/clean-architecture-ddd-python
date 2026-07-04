#!/usr/bin/env python
"""
Read-Model Reindex Worker

Rebuilds the Elasticsearch read models from PostgreSQL (the source of
truth) with zero downtime:

1. Creates a fresh timestamped physical index (books-20260704120000)
2. Bulk-indexes every row from PostgreSQL, using the same transforms
   as the CDC sync consumer
3. Atomically swaps the read alias (books) to the new index
4. Deletes the old physical indices (unless --keep-old)

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
import os
import sys
import time
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.container import Container
from src.infrastructure.adapters.catalog.book_model import BookModel
from src.infrastructure.adapters.lending.loan_model import LoanModel
from src.infrastructure.adapters.patron.patron_model import PatronModel

MAPPINGS_DIR = os.path.join(PROJECT_ROOT, "deploy", "elasticsearch", "mappings")
BATCH_SIZE = 500

ALIASES = {
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


async def reindex_alias(alias: str, container: Container, keep_old: bool) -> None:
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
    new_index = f"{alias}-{time.strftime('%Y%m%d%H%M%S')}"

    logger.info(f"Reindexing '{alias}': {old_indices or 'no current index'} -> {new_index}")
    await es_client.create_index(
        index=new_index,
        mappings=body["mappings"],
        settings=body.get("settings"),
    )

    model = ALIASES[alias]
    total = 0
    offset = 0
    async with session_factory() as session:
        while True:
            result = await session.execute(
                select(model).order_by(model.id).limit(BATCH_SIZE).offset(offset)
            )
            rows = result.scalars().all()
            if not rows:
                break

            documents = [transform(_row_to_dict(row)) for row in rows]
            success, errors = await es_client.bulk_index(new_index, documents)
            if errors:
                raise RuntimeError(
                    f"{errors} documents failed to index into {new_index}; "
                    f"aborting before alias swap ('{alias}' still serves the old index)"
                )

            total += success
            offset += BATCH_SIZE
            logger.info(f"  {alias}: indexed {total} documents")

    await es_client.refresh(new_index)
    await es_client.swap_alias(alias, new_index)
    logger.info(f"Alias '{alias}' swapped to {new_index} ({total} documents)")

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
    args = parser.parse_args()

    container = Container()

    # Load configuration from etcd
    etcd_adapter = container.etcd_adapter()
    etcd_adapter.load()
    container.configurations.from_dict(etcd_adapter.get_all())

    logger = container.logger()
    aliases = list(ALIASES) if args.index == "all" else [args.index]
    logger.info(f"Starting read-model reindex for: {aliases}")

    es_client = container.elasticsearch_client()
    try:
        for alias in aliases:
            await reindex_alias(alias, container, keep_old=args.keep_old)
        logger.info("Reindex complete")
    finally:
        await es_client.close()
        await container.postgresql().dispose()


if __name__ == "__main__":
    asyncio.run(main())
