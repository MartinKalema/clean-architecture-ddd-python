#!/usr/bin/env python3
"""
Seed etcd with initial configuration.

Usage:
    python scripts/seed_etcd_config.py

Environment variables:
    ETCD_HOST: etcd host (default: localhost)
    ETCD_PORT: etcd port (default: 2379)
"""
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.external.etcd_client import EtcdClient


DEFAULT_CONFIG = {
    "environment": "development",
    "logging": {
        "format": "json",
        "level": "INFO",
    },
    "database": {
        "url": "postgresql+asyncpg://library:library_secret@localhost:5432/library_db",
        "pool_size": 20,
        "max_overflow": 30,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    },
    "rabbitmq": {
        "url": "amqp://guest:guest@localhost:5672/",
        "exchange_name": "domain_events",
    },
    "sendgrid": {
        "api_key": "SG.placeholder",
        "from_email": "admin@library.com",
        "admin_email": "admin@library.com",
    },
    "templates": {
        "dir": "src/infrastructure/templates",
        "map": {
            "book_borrowed": "email/book_borrowed.html",
        },
    },
    "circuit_breakers": {
        "rabbitmq": {
            "name": "rabbitmq",
            "failure_threshold": 5,
            "success_threshold": 2,
            "timeout": 30.0,
        },
        "sendgrid": {
            "name": "sendgrid",
            "failure_threshold": 3,
            "success_threshold": 2,
            "timeout": 60.0,
        },
    },
}


def flatten_config(config: dict, prefix: str = "") -> dict:
    """Flatten nested config into etcd key-value pairs."""
    result = {}
    for key, value in config.items():
        full_key = f"{prefix}{key}" if prefix else key
        if isinstance(value, dict):
            result.update(flatten_config(value, f"{full_key}/"))
        else:
            result[full_key] = value
    return result


def seed_config(client: EtcdClient, config: dict, config_prefix: str = "/config/") -> None:
    """Seed configuration into etcd."""
    flat_config = flatten_config(config)

    for key, value in flat_config.items():
        full_key = f"{config_prefix}{key}"
        json_value = json.dumps(value) if not isinstance(value, str) else value
        client.put(full_key, json_value)
        print(f"  Set: {full_key}")


def main():
    host = os.environ.get("ETCD_HOST", "localhost")
    port = int(os.environ.get("ETCD_PORT", "2379"))
    config_prefix = os.environ.get("ETCD_CONFIG_PREFIX", "/config/")

    print(f"Connecting to etcd at {host}:{port}...")
    client = EtcdClient(host=host, port=port)

    try:
        client.connect()
        print("Connected to etcd")

        print(f"\nSeeding configuration with prefix '{config_prefix}'...")
        seed_config(client, DEFAULT_CONFIG, config_prefix)

        print("\nConfiguration seeded successfully!")
        print("\nVerifying configuration...")
        all_keys = client.get_prefix(config_prefix)
        print(f"Total keys: {len(all_keys)}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
