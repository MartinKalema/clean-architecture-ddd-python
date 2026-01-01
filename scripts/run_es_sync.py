#!/usr/bin/env python
"""
Elasticsearch Sync Worker

Runs the CDC consumer that syncs PostgreSQL changes to Elasticsearch.

Usage:
    python scripts/run_es_sync.py

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
    logger.info("Starting Elasticsearch Sync Consumer")
    logger.info(f"Kafka: {container.configurations.kafka.bootstrap_servers()}")
    logger.info(f"Elasticsearch: {container.configurations.elasticsearch.url()}")

    consumer = container.elasticsearch_sync_consumer()

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


if __name__ == "__main__":
    asyncio.run(main())
