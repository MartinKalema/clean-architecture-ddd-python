#!/usr/bin/env python
"""Prune old Debezium outbox rows in bounded transactions.

The database-owned ``inserted_at`` timestamp starts the retention window when
the row reaches this outbox, so a delayed historical event cannot be deleted
immediately. The replication slot must remain durable and the retention
horizon must exceed operational replay requirements; recreating a slot cannot
recover rows already pruned from the table.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.composition.bootstrap import bootstrap_container
from src.composition.lifecycle import database_resources
from src.composition.runtime_config import ProcessRole
from src.container import MaintenanceContainer
from src.infrastructure.adapters.outbox import OutboxRetentionService


async def main() -> None:
    parser = argparse.ArgumentParser(description="Prune old transactional-outbox rows")
    parser.add_argument("--retention-hours", type=int, default=24 * 7)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-batches", type=int, default=20)
    parser.add_argument(
        "--max-slot-lag-bytes",
        type=int,
        default=int(os.environ.get("OUTBOX_MAX_SLOT_LAG_BYTES", 1_073_741_824)),
    )
    parser.add_argument(
        "--replication-slot",
        default=os.environ.get(
            "DEBEZIUM_OUTBOX_SLOT_NAME", "library_outbox_slot"
        ),
        help="Active Debezium PostgreSQL slot required before deleting rows",
    )
    args = parser.parse_args()
    if args.retention_hours < 1:
        parser.error("--retention-hours must be positive")

    container = MaintenanceContainer()
    bootstrap_container(container, ProcessRole.MAINTENANCE)
    logger = container.logger()
    async with database_resources(container) as database:
        deleted = await OutboxRetentionService(database.session_factory).prune(
            retention_hours=args.retention_hours,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            replication_slot=args.replication_slot,
            max_slot_lag_bytes=args.max_slot_lag_bytes,
        )
        logger.info(
            f"Pruned {deleted} outbox row(s) using the database-owned "
            f"{args.retention_hours}h retention clock"
        )


if __name__ == "__main__":
    asyncio.run(main())
