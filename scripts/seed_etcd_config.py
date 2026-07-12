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

from src.composition.runtime_config import EtcdBootstrapConfig, load_runtime_config
from src.container import MaintenanceContainer


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
            "pool_timeout": get_env_int("DATABASE_POOL_TIMEOUT", 30),
            "pool_recycle": get_env_int("DATABASE_POOL_RECYCLE", 1800),
            "pools": {
                "api": {
                    "pool_size": get_env_int("DATABASE_API_POOL_SIZE", 20),
                    "max_overflow": get_env_int("DATABASE_API_MAX_OVERFLOW", 10),
                },
                "workflow": {
                    "pool_size": get_env_int("DATABASE_WORKFLOW_POOL_SIZE", 5),
                    "max_overflow": get_env_int("DATABASE_WORKFLOW_MAX_OVERFLOW", 5),
                },
                "notification": {
                    "pool_size": get_env_int("DATABASE_NOTIFICATION_POOL_SIZE", 3),
                    "max_overflow": get_env_int("DATABASE_NOTIFICATION_MAX_OVERFLOW", 2),
                },
                "reaper": {
                    "pool_size": get_env_int("DATABASE_REAPER_POOL_SIZE", 2),
                    "max_overflow": get_env_int("DATABASE_REAPER_MAX_OVERFLOW", 0),
                },
                "projection": {
                    "pool_size": get_env_int("DATABASE_PROJECTION_POOL_SIZE", 2),
                    "max_overflow": get_env_int("DATABASE_PROJECTION_MAX_OVERFLOW", 0),
                },
                "cli": {
                    "pool_size": get_env_int("DATABASE_CLI_POOL_SIZE", 2),
                    "max_overflow": get_env_int("DATABASE_CLI_MAX_OVERFLOW", 0),
                },
                "maintenance": {
                    "pool_size": get_env_int("DATABASE_MAINTENANCE_POOL_SIZE", 5),
                    "max_overflow": get_env_int("DATABASE_MAINTENANCE_MAX_OVERFLOW", 0),
                },
            },
        },
        "sendgrid": {
            "api_key": get_env("SENDGRID_API_KEY", "SG.placeholder"),
            "from_email": get_env("SENDGRID_FROM_EMAIL", "admin@library.com"),
            "request_timeout_seconds": get_env_float(
                "SENDGRID_REQUEST_TIMEOUT_SECONDS", 15.0
            ),
        },
        "circuit_breakers": {
            "sendgrid": {
                "name": get_env("CB_SENDGRID_NAME", "sendgrid"),
                "failure_threshold": get_env_int("CB_SENDGRID_FAILURE_THRESHOLD", 3),
                "success_threshold": get_env_int("CB_SENDGRID_SUCCESS_THRESHOLD", 2),
                "timeout": get_env_float("CB_SENDGRID_TIMEOUT", 60.0),
                "failure_rate_threshold": get_env_float("CB_SENDGRID_FAILURE_RATE_THRESHOLD", 50.0),
                "window_seconds": get_env_float("CB_SENDGRID_WINDOW_SECONDS", 60.0),
                "minimum_calls": get_env_int("CB_SENDGRID_MINIMUM_CALLS", 10),
                "half_open_max_calls": get_env_int("CB_SENDGRID_HALF_OPEN_MAX_CALLS", 1),
            },
            "elasticsearch": {
                "name": get_env("CB_ELASTICSEARCH_NAME", "elasticsearch"),
                "failure_threshold": get_env_int("CB_ELASTICSEARCH_FAILURE_THRESHOLD", 5),
                "success_threshold": get_env_int("CB_ELASTICSEARCH_SUCCESS_THRESHOLD", 2),
                "timeout": get_env_float("CB_ELASTICSEARCH_TIMEOUT", 30.0),
                "failure_rate_threshold": get_env_float("CB_ELASTICSEARCH_FAILURE_RATE_THRESHOLD", 50.0),
                "window_seconds": get_env_float("CB_ELASTICSEARCH_WINDOW_SECONDS", 60.0),
                "minimum_calls": get_env_int("CB_ELASTICSEARCH_MINIMUM_CALLS", 10),
                "half_open_max_calls": get_env_int("CB_ELASTICSEARCH_HALF_OPEN_MAX_CALLS", 1),
                # ES client's own request_timeout is 30s; the breaker cuts
                # slightly later so the client timeout fires first
                "call_timeout": get_env_float("CB_ELASTICSEARCH_CALL_TIMEOUT", 35.0),
            },
        },
        "redis": {
            "url": get_env("REDIS_URL", "redis://localhost:6379/0"),
            "cache_ttl": get_env_int("REDIS_CACHE_TTL", 120),
            "enabled": get_env("REDIS_ENABLED", "true").lower() == "true",
        },
        "kafka": {
            "bootstrap_servers": get_env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            "projection_group_id": get_env(
                "KAFKA_PROJECTION_GROUP_ID", "es-sync-consumer"
            ),
            "consumer_max_retries": get_env_int("KAFKA_CONSUMER_MAX_RETRIES", 3),
            "retry_backoff_seconds": get_env_float("KAFKA_RETRY_BACKOFF_SECONDS", 1.0),
            "consumer_max_poll_interval_ms": get_env_int(
                "KAFKA_CONSUMER_MAX_POLL_INTERVAL_MS", 900_000
            ),
            "message_processing_timeout_seconds": get_env_float(
                "KAFKA_MESSAGE_PROCESSING_TIMEOUT_SECONDS", 180.0
            ),
            "internal_topic_replication_factor": get_env_int(
                "KAFKA_INTERNAL_TOPIC_REPLICATION_FACTOR", 3
            ),
            "workflow_group_id": get_env(
                "KAFKA_WORKFLOW_GROUP_ID", "domain-workflow-worker-v1"
            ),
            "notification_group_id": get_env(
                "KAFKA_NOTIFICATION_GROUP_ID", "domain-notification-worker-v1"
            ),
        },
        "elasticsearch": {
            "enabled": get_env("ELASTICSEARCH_ENABLED", "false").lower() == "true",
            "url": get_env("ELASTICSEARCH_URL", "http://localhost:9200"),
            "max_connections": get_env_int("ELASTICSEARCH_MAX_CONNECTIONS", 300),
            "request_timeout": get_env_int("ELASTICSEARCH_REQUEST_TIMEOUT", 30),
            "max_retries": get_env_int("ELASTICSEARCH_MAX_RETRIES", 3),
            "username": get_env("ELASTICSEARCH_USERNAME", ""),
            "password": get_env("ELASTICSEARCH_PASSWORD", ""),
            "verify_certs": get_env("ELASTICSEARCH_VERIFY_CERTS", "true").lower() == "true",
        },
        "catalog": {
            # Keep the TTL comfortably above worst-case event latency. Exact
            # reservation fencing makes expiry safe, but an undersized TTL
            # would still compensate otherwise valid borrows.
            "reservation_ttl_seconds": get_env_int("RESERVATION_TTL_SECONDS", 300),
            "reaper_interval_seconds": get_env_int("RESERVATION_REAPER_INTERVAL_SECONDS", 60),
        },
        "cdc": {
            "topic_to_index": {
                "library.public.books": "books",
                "library.public.patrons": "patrons",
                "library.public.loans": "loans",
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
    """Replace the current config keys without retaining obsolete fields."""
    flat_config = flatten_config(config)
    desired_keys = {f"{config_prefix}{key}" for key in flat_config}

    for key, value in flat_config.items():
        full_key = f"{config_prefix}{key}"
        json_value = json.dumps(value) if not isinstance(value, str) else value
        client.put(full_key, json_value)
        print(f"  Set: {full_key}")

    # Write the complete new snapshot before deleting stale keys. Readers may
    # briefly observe an extra key and fail closed, but can never observe a
    # partially missing current configuration.
    for stale_key in sorted(set(client.get_prefix(config_prefix)) - desired_keys):
        client.delete(stale_key)
        print(f"  Removed obsolete key: {stale_key}")


def main():
    bootstrap = EtcdBootstrapConfig.from_environment()
    config_prefix = bootstrap.prefix

    container = MaintenanceContainer()
    container.bootstrap.from_dict({"etcd": bootstrap.model_dump(mode="python")})
    client = container.etcd_client()

    print(f"Connecting to etcd...")

    try:
        client.connect()
        print("Connected to etcd")

        print(f"\nSeeding configuration with prefix '{config_prefix}'...")
        config = build_config()
        # Never publish a partial or malformed snapshot to the shared source.
        load_runtime_config(config)
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
