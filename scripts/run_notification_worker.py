#!/usr/bin/env python
"""Run the independently scaled optional-notification consumer."""
from __future__ import annotations

import asyncio
import os
import signal
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.container import Container


async def main() -> None:
    container = Container()
    etcd_adapter = container.etcd_adapter()
    etcd_adapter.load()
    container.configurations.from_dict(etcd_adapter.get_all())

    logger = container.logger()
    database = container.postgresql()
    await database.verify_schema_current()
    consumer = container.notification_event_consumer()

    loop = asyncio.get_running_loop()

    def signal_handler() -> None:
        logger.info("Received shutdown signal, stopping notification worker...")
        asyncio.create_task(consumer.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    logger.info("Starting isolated notification worker")
    try:
        await consumer.start()
    except asyncio.CancelledError:
        logger.info("Notification consumer cancelled")
    except Exception as error:
        logger.error("Notification consumer failed", exception=error)
        raise
    finally:
        try:
            await database.dispose()
        finally:
            etcd_adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
