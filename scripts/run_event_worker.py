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

from src.composition.bootstrap import bootstrap_container
from src.composition.lifecycle import workflow_resources
from src.composition.runtime_config import ProcessRole
from src.container import WorkflowContainer


async def main() -> None:
    """Main entry point."""
    container = WorkflowContainer()
    settings = bootstrap_container(container, ProcessRole.WORKFLOW)

    logger = container.logger()
    logger.info("Starting Domain Event Worker")
    logger.info(f"Kafka: {settings.kafka.bootstrap_servers}")

    async with workflow_resources(container) as consumer:
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
        except Exception as error:
            logger.error("Consumer failed", exception=error)
            raise


if __name__ == "__main__":
    asyncio.run(main())
