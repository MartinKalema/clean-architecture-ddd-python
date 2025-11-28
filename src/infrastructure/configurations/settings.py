"""
Configuration management with environment variable support.

In production, secrets should be provided via environment variables.
The YAML file serves as default values for development only.

Environment Variables:
    DATABASE_URL: Database connection URL
    DB_POOL_SIZE: Connection pool size (default: 20)
    DB_MAX_OVERFLOW: Max overflow connections (default: 30)
    DB_POOL_TIMEOUT: Pool timeout in seconds (default: 30)
    DB_POOL_RECYCLE: Recycle connections after N seconds (default: 1800)
    RABBITMQ_URL: RabbitMQ connection URL
    RABBITMQ_EXCHANGE: RabbitMQ exchange name
    SENDGRID_API_KEY: SendGrid API key
    SENDGRID_FROM_EMAIL: Sender email address
    SENDGRID_ADMIN_EMAIL: Admin email for CC
    TEMPLATES_DIR: Directory for email templates
    LOG_FORMAT: Logging format (json or standard)
    LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR)
    ENVIRONMENT: Environment name (development, staging, production)
"""
import os
import yaml
from typing import Dict, Any


def _get_env(key: str, default: Any = None) -> Any:
    """Get environment variable with optional default."""
    return os.environ.get(key, default)


def _load_yaml_config(config_path: str = "src/infrastructure/configurations/settings.yaml") -> Dict[str, Any]:
    """Load YAML config file if it exists."""
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def load_config(config_path: str = "src/infrastructure/configurations/settings.yaml") -> Dict[str, Any]:
    """
    Load configuration with environment variables taking precedence.

    Environment variables override YAML config values.
    This allows for secure secret management in production while
    maintaining easy development setup with YAML defaults.
    """
    # Load YAML defaults
    yaml_config = _load_yaml_config(config_path)

    # Build config with env var overrides
    config = {
        "environment": _get_env("ENVIRONMENT", "development"),
        "logging": {
            "format": _get_env("LOG_FORMAT", "json"),  # json or standard
            "level": _get_env("LOG_LEVEL", "INFO"),
        },
        "database": {
            "url": _get_env(
                "DATABASE_URL",
                yaml_config.get("database", {}).get("url", "sqlite:///./books.db")
            ),
            "pool_size": int(_get_env("DB_POOL_SIZE", yaml_config.get("database", {}).get("pool_size", 20))),
            "max_overflow": int(_get_env("DB_MAX_OVERFLOW", yaml_config.get("database", {}).get("max_overflow", 30))),
            "pool_timeout": int(_get_env("DB_POOL_TIMEOUT", yaml_config.get("database", {}).get("pool_timeout", 30))),
            "pool_recycle": int(_get_env("DB_POOL_RECYCLE", yaml_config.get("database", {}).get("pool_recycle", 1800))),
        },
        "rabbitmq": {
            "url": _get_env(
                "RABBITMQ_URL",
                yaml_config.get("rabbitmq", {}).get("url", "amqp://guest:guest@localhost:5672/")
            ),
            "exchange_name": _get_env(
                "RABBITMQ_EXCHANGE",
                yaml_config.get("rabbitmq", {}).get("exchange_name", "domain_events")
            ),
        },
        "sendgrid": {
            "api_key": _get_env(
                "SENDGRID_API_KEY",
                yaml_config.get("sendgrid", {}).get("api_key", "")
            ),
            "from_email": _get_env(
                "SENDGRID_FROM_EMAIL",
                yaml_config.get("sendgrid", {}).get("from_email", "admin@library.com")
            ),
            "admin_email": _get_env(
                "SENDGRID_ADMIN_EMAIL",
                yaml_config.get("sendgrid", {}).get("admin_email", "admin@library.com")
            ),
        },
        "templates": {
            "dir": _get_env(
                "TEMPLATES_DIR",
                yaml_config.get("templates", {}).get("dir", "src/infrastructure/templates")
            ),
            "map": yaml_config.get("templates", {}).get("map", {
                "book_borrowed": "email/book_borrowed.html"
            }),
        },
    }

    return config
