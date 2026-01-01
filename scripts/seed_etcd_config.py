#!/usr/bin/env python3
"""
Seed etcd with initial configuration.

Usage:
    python scripts/seed_etcd_config.py

Reads configuration from environment variables.
In Docker: set via env_file in docker-compose.yaml
Locally: load from .env file
"""
import json
import os
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Only load .env if it exists (for local development)
env_file = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(env_file):
    from dotenv import load_dotenv
    load_dotenv(env_file)

from src.container import Container


def get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def get_env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, default))


def get_env_float(key: str, default: float) -> float:
    return float(os.environ.get(key, default))


def build_config() -> dict:
    return {
        "environment": get_env("ENVIRONMENT", "development"),
        "logging": {
            "format": get_env("LOG_FORMAT", "json"),
            "level": get_env("LOG_LEVEL", "INFO"),
        },
        "database": {
            "url": get_env("DATABASE_URL", "postgresql+asyncpg://library:library_secret@localhost:5432/library_db"),
            "pool_size": get_env_int("DATABASE_POOL_SIZE", 20),
            "max_overflow": get_env_int("DATABASE_MAX_OVERFLOW", 30),
            "pool_timeout": get_env_int("DATABASE_POOL_TIMEOUT", 30),
            "pool_recycle": get_env_int("DATABASE_POOL_RECYCLE", 1800),
        },
        "rabbitmq": {
            "url": get_env("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
            "exchange_name": get_env("RABBITMQ_EXCHANGE", "domain_events"),
        },
        "sendgrid": {
            "api_key": get_env("SENDGRID_API_KEY", "SG.placeholder"),
            "from_email": get_env("SENDGRID_FROM_EMAIL", "admin@library.com"),
            "admin_email": get_env("SENDGRID_ADMIN_EMAIL", "admin@library.com"),
        },
        "templates": {
            "dir": get_env("TEMPLATES_DIR", "src/infrastructure/templates"),
            "map": {
                "book_borrowed": "email/book_borrowed.html",
            },
        },
        "circuit_breakers": {
            "rabbitmq": {
                "name": get_env("CB_RABBITMQ_NAME", "rabbitmq"),
                "failure_threshold": get_env_int("CB_RABBITMQ_FAILURE_THRESHOLD", 5),
                "success_threshold": get_env_int("CB_RABBITMQ_SUCCESS_THRESHOLD", 2),
                "timeout": get_env_float("CB_RABBITMQ_TIMEOUT", 30.0),
            },
            "sendgrid": {
                "name": get_env("CB_SENDGRID_NAME", "sendgrid"),
                "failure_threshold": get_env_int("CB_SENDGRID_FAILURE_THRESHOLD", 3),
                "success_threshold": get_env_int("CB_SENDGRID_SUCCESS_THRESHOLD", 2),
                "timeout": get_env_float("CB_SENDGRID_TIMEOUT", 60.0),
            },
        },
        "redis": {
            "url": get_env("REDIS_URL", "redis://localhost:6379/0"),
            "cache_ttl": get_env_int("REDIS_CACHE_TTL", 300),
            "enabled": get_env("REDIS_ENABLED", "true").lower() == "true",
        },
        "kafka": {
            "bootstrap_servers": get_env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            "consumer_group": get_env("KAFKA_CONSUMER_GROUP", "es-sync-consumer"),
        },
        "elasticsearch": {
            "url": get_env("ELASTICSEARCH_URL", "http://localhost:9200"),
            "enabled": get_env("ELASTICSEARCH_ENABLED", "true").lower() == "true",
        },
        "cdc": {
            "topic_to_index": {
                "library.public.books": "books",
                "library.public.patrons": "patrons",
                "library.public.loans": "loans",
            },
            "index_to_cache_type": {
                "books": "book",
                "patrons": "patron",
                "loans": "loan",
            },
        },
    }


def is_leaf_dict(d: dict) -> bool:
    """Check if a dict is a leaf dict (all values are primitives, not nested dicts)."""
    return all(not isinstance(v, dict) for v in d.values())


def flatten_config(config: dict, prefix: str = "") -> dict:
    """Flatten nested config into etcd key-value pairs.

    Leaf dicts (dicts with only primitive values) are stored as JSON strings
    to preserve them as dicts when loaded back.
    """
    result = {}
    for key, value in config.items():
        full_key = f"{prefix}{key}" if prefix else key
        if isinstance(value, dict):
            if is_leaf_dict(value):
                # Store leaf dicts as JSON to preserve structure
                result[full_key] = json.dumps(value)
            else:
                result.update(flatten_config(value, f"{full_key}/"))
        else:
            result[full_key] = value
    return result


def seed_config(client, config: dict, config_prefix: str = "/config/") -> None:
    """Seed configuration into etcd."""
    flat_config = flatten_config(config)

    for key, value in flat_config.items():
        full_key = f"{config_prefix}{key}"
        json_value = json.dumps(value) if not isinstance(value, str) else value
        client.put(full_key, json_value)
        print(f"  Set: {full_key}")


def main():
    config_prefix = os.environ.get("ETCD_CONFIG_PREFIX", "/config/")

    container = Container()
    client = container.etcd_client()

    print(f"Connecting to etcd...")

    try:
        client.connect()
        print("Connected to etcd")

        print(f"\nSeeding configuration with prefix '{config_prefix}'...")
        config = build_config()
        seed_config(client, config, config_prefix)

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
