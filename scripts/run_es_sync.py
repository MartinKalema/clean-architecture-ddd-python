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
import os
import signal
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.container import Container


def main() -> None:
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

    def signal_handler(sig: int, frame) -> None:
        logger.info(f"Received signal {sig}, shutting down...")
        consumer.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        consumer.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        consumer.stop()


if __name__ == "__main__":
    main()
