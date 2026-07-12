#!/usr/bin/env python
"""
Reservation Reaper Worker

Periodically releases book reservations whose borrow saga never
completed (semantic-lock expiry). Released books emit CatalogBookReleased
through the outbox like any other state change.

Usage:
    python scripts/run_reservation_reaper.py

Environment variables:
    ETCD_HOST: etcd host (default: localhost)
    ETCD_PORT: etcd port (default: 2379)
"""
import asyncio
import os
import signal
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.application.command_handlers.release_expired_reservations import (
    ReleaseExpiredReservationsCommand,
)
from src.composition.bootstrap import bootstrap_container
from src.composition.lifecycle import database_resources
from src.composition.runtime_config import ProcessRole
from src.container import ReaperContainer


async def release_all_expired(operation_factory, command) -> int:
    """Drain one sweep while preserving post-commit decoration per batch."""
    released_count = 0
    while True:
        # The production factory returns the cache-invalidating decorator.
        # Constructing and invoking it once per batch guarantees that a later
        # batch failure cannot skip invalidation for an earlier commit.
        result = await operation_factory().handle(command)
        released_count += result.released_count
        if not result.batch_full:
            return released_count


async def main() -> None:
    """Main entry point."""
    container = ReaperContainer()
    settings = bootstrap_container(container, ProcessRole.REAPER)

    logger = container.logger()
    ttl_seconds = settings.catalog.reservation_ttl_seconds
    interval_seconds = settings.catalog.reaper_interval_seconds

    logger.info(
        f"Starting Reservation Reaper (ttl={ttl_seconds}s, "
        f"interval={interval_seconds}s)"
    )

    stopping = asyncio.Event()

    def signal_handler() -> None:
        logger.info("Received shutdown signal, stopping...")
        stopping.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    command = ReleaseExpiredReservationsCommand(ttl_seconds=ttl_seconds)
    heartbeat_path = Path(
        os.environ.get(
            "RESERVATION_REAPER_HEARTBEAT_PATH",
            "/tmp/reservation-reaper-heartbeat",
        )
    )
    async with database_resources(container):
        try:
            while not stopping.is_set():
                try:
                    released_count = await release_all_expired(
                        container.release_expired_reservations,
                        command,
                    )
                    if released_count:
                        logger.info(
                            f"Reaper released {released_count} reservation(s)"
                        )
                    heartbeat_path.touch()
                except Exception as error:
                    logger.error("Reaper sweep failed", exception=error)

                try:
                    await asyncio.wait_for(stopping.wait(), timeout=interval_seconds)
                except asyncio.TimeoutError:
                    pass
        finally:
            logger.info("Reservation reaper stopped")


if __name__ == "__main__":
    asyncio.run(main())
