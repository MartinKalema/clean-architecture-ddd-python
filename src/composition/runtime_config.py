"""Validated, immutable configuration used by every process composition root."""
from __future__ import annotations

import math
import os
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProcessRole(str, Enum):
    API = "api"
    WORKFLOW = "workflow"
    NOTIFICATION = "notification"
    REAPER = "reaper"
    PROJECTION = "projection"
    CLI = "cli"
    MAINTENANCE = "maintenance"


class EtcdBootstrapConfig(_ConfigModel):
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65_535)
    prefix: str = Field(min_length=2)

    @field_validator("host", "prefix")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("prefix")
    @classmethod
    def require_absolute_prefix(cls, value: str) -> str:
        if not value.startswith("/") or not value.endswith("/"):
            raise ValueError("must start and end with '/'")
        return value

    @classmethod
    def from_environment(cls) -> "EtcdBootstrapConfig":
        raw_port = os.environ.get("ETCD_PORT", "2379")
        try:
            port = int(raw_port)
        except ValueError as error:
            raise ValueError("ETCD_PORT must be an integer") from error
        return cls(
            host=os.environ.get("ETCD_HOST", "localhost"),
            port=port,
            prefix=os.environ.get("ETCD_CONFIG_PREFIX", "/config/"),
        )


class LoggingConfig(_ConfigModel):
    format: Literal["json", "standard"]
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class DatabasePoolConfig(_ConfigModel):
    pool_size: int = Field(ge=1, le=100)
    max_overflow: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def enforce_total_limit(self) -> "DatabasePoolConfig":
        if self.pool_size + self.max_overflow > 100:
            raise ValueError("pool_size + max_overflow must not exceed 100")
        return self


class DatabasePoolsConfig(_ConfigModel):
    api: DatabasePoolConfig
    workflow: DatabasePoolConfig
    notification: DatabasePoolConfig
    reaper: DatabasePoolConfig
    projection: DatabasePoolConfig
    cli: DatabasePoolConfig
    maintenance: DatabasePoolConfig


class DatabaseConfig(_ConfigModel):
    url: str = Field(min_length=1)
    pool_timeout: int = Field(ge=1, le=300)
    pool_recycle: int = Field(ge=0, le=86_400)
    pools: DatabasePoolsConfig

    @field_validator("url")
    @classmethod
    def require_supported_database_url(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgres://", "postgresql+asyncpg://", "sqlite://", "sqlite+aiosqlite://")):
            raise ValueError("must be a PostgreSQL or SQLite URL")
        return value


class SendGridConfig(_ConfigModel):
    api_key: str = Field(min_length=1)
    from_email: str = Field(min_length=3)
    request_timeout_seconds: float = Field(gt=0, le=60)

    @field_validator("api_key", "from_email")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("from_email")
    @classmethod
    def require_email_shape(cls, value: str) -> str:
        local, separator, domain = value.rpartition("@")
        if not separator or not local or "." not in domain:
            raise ValueError("must be a valid email address")
        return value


class CircuitBreakerConfig(_ConfigModel):
    name: str = Field(min_length=1, max_length=64)
    failure_threshold: int = Field(ge=1, le=10_000)
    success_threshold: int = Field(ge=1, le=10_000)
    timeout: float = Field(gt=0, le=86_400)
    failure_rate_threshold: float = Field(gt=0, le=100)
    window_seconds: float = Field(gt=0, le=86_400)
    minimum_calls: int = Field(ge=1, le=1_000_000)
    half_open_max_calls: int = Field(ge=1, le=10_000)
    call_timeout: float | None = Field(default=None, gt=0, le=600)

    @field_validator("name")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator(
        "timeout", "failure_rate_threshold", "window_seconds", "call_timeout"
    )
    @classmethod
    def require_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("must be finite")
        return value


class CircuitBreakersConfig(_ConfigModel):
    sendgrid: CircuitBreakerConfig
    elasticsearch: CircuitBreakerConfig

    @model_validator(mode="after")
    def require_distinct_names(self) -> "CircuitBreakersConfig":
        if self.sendgrid.name == self.elasticsearch.name:
            raise ValueError("circuit breaker names must be distinct")
        return self


class RedisConfig(_ConfigModel):
    url: str = Field(min_length=1)
    cache_ttl: int = Field(ge=1, le=86_400)
    enabled: bool

    @field_validator("url")
    @classmethod
    def require_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://")):
            raise ValueError("must be a Redis URL")
        return value


class KafkaConfig(_ConfigModel):
    bootstrap_servers: str = Field(min_length=1)
    projection_group_id: str = Field(min_length=1, max_length=255)
    consumer_max_retries: int = Field(ge=0, le=100)
    retry_backoff_seconds: float = Field(ge=0, le=300)
    consumer_max_poll_interval_ms: int = Field(ge=1_000, le=86_400_000)
    message_processing_timeout_seconds: float = Field(gt=0, le=240)
    internal_topic_replication_factor: int = Field(ge=1, le=32_767)
    workflow_group_id: str = Field(min_length=1, max_length=255)
    notification_group_id: str = Field(min_length=1, max_length=255)

    @field_validator(
        "bootstrap_servers",
        "projection_group_id",
        "workflow_group_id",
        "notification_group_id",
    )
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def require_distinct_consumer_groups(self) -> "KafkaConfig":
        group_ids = {
            self.projection_group_id,
            self.workflow_group_id,
            self.notification_group_id,
        }
        if len(group_ids) != 3:
            raise ValueError("Kafka consumer group IDs must be distinct")
        retry_delay_budget = sum(
            min(self.retry_backoff_seconds * (2 ** min(attempt, 10)), 60.0)
            for attempt in range(self.consumer_max_retries)
        )
        poll_cycle_seconds = (
            self.message_processing_timeout_seconds
            * (self.consumer_max_retries + 1)
            + retry_delay_budget
            + 60.0
            + 5.0
        )
        if poll_cycle_seconds * 1_000 >= self.consumer_max_poll_interval_ms:
            raise ValueError(
                "Kafka max poll interval must exceed the complete processing, "
                "retry, and dead-letter budget"
            )
        return self


class ElasticsearchConfig(_ConfigModel):
    enabled: bool
    url: str = Field(min_length=1)
    max_connections: int = Field(ge=1, le=1_000)
    request_timeout: int = Field(ge=1, le=300)
    max_retries: int = Field(ge=0, le=100)
    username: str
    password: str
    verify_certs: bool

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("must be an HTTP(S) URL")
        return value

    @model_validator(mode="after")
    def require_tls_verification_in_production_shape(self) -> "ElasticsearchConfig":
        if self.url.startswith("https://") and not self.verify_certs:
            raise ValueError("HTTPS Elasticsearch must verify certificates")
        if bool(self.username) != bool(self.password):
            raise ValueError("username and password must be configured together")
        return self


class CatalogConfig(_ConfigModel):
    reservation_ttl_seconds: int = Field(ge=1, le=86_400)
    reaper_interval_seconds: int = Field(ge=1, le=3_600)

    @model_validator(mode="after")
    def require_useful_reaper_interval(self) -> "CatalogConfig":
        if self.reaper_interval_seconds >= self.reservation_ttl_seconds:
            raise ValueError("reaper interval must be shorter than reservation TTL")
        return self


class CdcConfig(_ConfigModel):
    topic_to_index: dict[str, str] = Field(min_length=1)

    @field_validator("topic_to_index")
    @classmethod
    def reject_blank_mapping(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not topic.strip() or not index.strip() for topic, index in value.items()):
            raise ValueError("CDC topic and index names must not be blank")
        return value


class RuntimeConfig(_ConfigModel):
    environment: Literal["development", "test", "staging", "production"]
    logging: LoggingConfig
    database: DatabaseConfig
    sendgrid: SendGridConfig
    circuit_breakers: CircuitBreakersConfig
    redis: RedisConfig
    kafka: KafkaConfig
    elasticsearch: ElasticsearchConfig
    catalog: CatalogConfig
    cdc: CdcConfig

    @model_validator(mode="after")
    def require_breaker_timeout_outside_client_timeout(self) -> "RuntimeConfig":
        call_timeout = self.circuit_breakers.elasticsearch.call_timeout
        if call_timeout is None:
            raise ValueError("Elasticsearch circuit breaker requires call_timeout")
        if call_timeout <= self.elasticsearch.request_timeout:
            raise ValueError(
                "Elasticsearch circuit-breaker call timeout must exceed the "
                "client request timeout"
            )
        return self

    def for_process(self, role: ProcessRole) -> dict[str, Any]:
        """Return the provider configuration with the role's DB budget selected."""
        result = self.model_dump(mode="python")
        database = result["database"]
        pools = database.pop("pools")
        database.update(pools[role.value])
        return result


def load_runtime_config(raw_config: dict[str, Any]) -> RuntimeConfig:
    """Validate etcd's complete startup snapshot before any client is built."""
    return RuntimeConfig.model_validate(raw_config)
