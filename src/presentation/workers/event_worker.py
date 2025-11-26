#!/usr/bin/env python
"""
Event Worker

Runs the event consumer that listens to RabbitMQ and dispatches
events to the appropriate handlers.

Usage:
    python -m src.presentation.workers.event_worker
"""
import asyncio
import signal
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.container import Container
from src.infrastructure.adapters.messaging.event_consumer import EventConsumer


async def main():
    """Main entry point for the event worker."""
    # Initialize container
    container = Container()

    # Get dependencies
    config = container.config()
    logger = container.logger()
    book_handlers = container.book_handlers()

    # Create consumer
    consumer = EventConsumer(
        amqp_url=config["rabbitmq"]["url"],
        exchange_name=config["rabbitmq"]["exchange_name"],
        queue_name="library_events",
        logger=logger
    )

    # Register handlers
    consumer.register_handler("BookBorrowed", book_handlers.handle_book_borrowed)
    consumer.register_handler("BookReturned", book_handlers.handle_book_returned)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def shutdown():
        logger.info("Received shutdown signal")
        asyncio.create_task(consumer.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown)

    # Start consumer
    logger.info("Starting event worker...")
    try:
        await consumer.start()
    except Exception as e:
        logger.error("Event worker crashed", exception=e)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
