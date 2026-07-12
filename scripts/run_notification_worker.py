#!/usr/bin/env python
"""Run the independently scaled optional-notification consumer."""
from __future__ import annotations

import asyncio
import os
import signal
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.composition.bootstrap import bootstrap_container
from src.composition.lifecycle import notification_resources
from src.composition.runtime_config import ProcessRole
from src.container import NotificationContainer


async def main() -> None:
    container = NotificationContainer()
    bootstrap_container(container, ProcessRole.NOTIFICATION)

    logger = container.logger()
    async with notification_resources(container) as consumer:
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


if __name__ == "__main__":
    asyncio.run(main())
