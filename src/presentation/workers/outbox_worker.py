#!/usr/bin/env python
"""
Outbox Worker

Processes the transactional outbox by polling for unprocessed messages
and dispatching them to RabbitMQ.

This ensures at-least-once delivery of domain events.

Usage:
    python -m src.presentation.workers.outbox_worker
"""
import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.container import Container
from src.infrastructure.adapters.outbox.outbox_processor import OutboxProcessor


async def main():
    """Main entry point for the outbox worker."""
    container = Container()

    logger = container.logger()
    database = container.database()
    event_dispatcher = container.event_dispatcher()

    processor = OutboxProcessor(
        session_factory=database.session_factory,
        event_dispatcher=event_dispatcher,
        logger=logger,
        poll_interval=1.0,
        batch_size=100
    )

    loop = asyncio.get_event_loop()

    def shutdown():
        logger.info("Received shutdown signal")
        asyncio.create_task(processor.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown)

    logger.info("Starting outbox worker...")
    try:
        await processor.start()
    except Exception as e:
        logger.error("Outbox worker crashed", exception=e)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
