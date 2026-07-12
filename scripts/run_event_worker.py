#!/usr/bin/env python
"""
Domain Event Worker

Runs the consumer that reads domain events from the outbox Kafka topics
(published by the Debezium Outbox Event Router) and dispatches them to
application-layer event handlers.

Usage:
    python scripts/run_event_worker.py

Environment variables:
    ETCD_HOST: etcd host (default: localhost)
    ETCD_PORT: etcd port (default: 2379)
"""
import asyncio
import os
import signal
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.container import Container


async def main() -> None:
    """Main entry point."""
    container = Container()

    # Load configuration from etcd
    etcd_adapter = container.etcd_adapter()
    etcd_adapter.load()
    container.configurations.from_dict(etcd_adapter.get_all())

    logger = container.logger()
    logger.info("Starting Domain Event Worker")
    logger.info(f"Kafka: {container.configurations.kafka.bootstrap_servers()}")

    database = container.postgresql()
    await database.verify_schema_current()
    consumer = container.domain_event_consumer()

    loop = asyncio.get_running_loop()

    def signal_handler() -> None:
        logger.info("Received shutdown signal, stopping...")
        asyncio.create_task(consumer.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await consumer.start()
    except asyncio.CancelledError:
        logger.info("Consumer cancelled")
    except Exception as e:
        logger.error(f"Consumer error: {e}")
        raise
    finally:
        # Workflow handlers invalidate Redis after committed writes. The
        # consumer owns that lazy transport in this process and must close it
        # during a graceful worker replacement.
        try:
            await container.redis_client().close()
        finally:
            try:
                await database.dispose()
            finally:
                etcd_adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
