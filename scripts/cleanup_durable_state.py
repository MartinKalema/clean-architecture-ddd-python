#!/usr/bin/env python3
"""Prune bounded command, operation, inbox, and quarantine history."""
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
from src.infrastructure.adapters.maintenance import DurableStateRetentionService


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command-receipt-days", type=int, default=30)
    parser.add_argument("--terminal-operation-days", type=int, default=120)
    parser.add_argument("--processed-inbox-days", type=int, default=120)
    parser.add_argument("--quarantine-days", type=int, default=365)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-batches", type=int, default=20)
    args = parser.parse_args()

    container = MaintenanceContainer()
    bootstrap_container(container, ProcessRole.MAINTENANCE)
    async with database_resources(container) as database:
        deleted = await DurableStateRetentionService(
            database.session_factory
        ).prune(
            command_receipt_days=args.command_receipt_days,
            terminal_operation_days=args.terminal_operation_days,
            processed_inbox_days=args.processed_inbox_days,
            quarantine_days=args.quarantine_days,
            batch_size=args.batch_size,
            max_batches_per_table=args.max_batches,
        )
        container.logger().info(f"Durable-state retention deleted: {deleted}")


if __name__ == "__main__":
    asyncio.run(main())
