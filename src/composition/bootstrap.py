"""Fail-fast process bootstrap from the immutable etcd startup snapshot."""
from __future__ import annotations

from typing import Any, Protocol

from pydantic import ValidationError

from src.composition.runtime_config import (
    EtcdBootstrapConfig,
    ProcessRole,
    RuntimeConfig,
    load_runtime_config,
)
from src.infrastructure.exceptions import ConfigurationException


class ConfigurableContainer(Protocol):
    bootstrap: Any
    configurations: Any

    def etcd_adapter(self) -> Any: ...

    def check_dependencies(self) -> None: ...


def bootstrap_container(
    container: ConfigurableContainer,
    role: ProcessRole,
) -> RuntimeConfig:
    """Configure a container or close etcd and fail before clients are built."""
    try:
        bootstrap = EtcdBootstrapConfig.from_environment()
    except (ValidationError, ValueError) as error:
        raise ConfigurationException(_safe_validation_message("bootstrap", error)) from error

    container.bootstrap.from_dict({"etcd": bootstrap.model_dump(mode="python")})
    adapter = container.etcd_adapter()
    try:
        adapter.load()
        settings = load_runtime_config(adapter.get_all())
        container.configurations.from_dict(settings.for_process(role))
        container.check_dependencies()
        return settings
    except ValidationError as error:
        adapter.close()
        raise ConfigurationException(_safe_validation_message("runtime", error)) from error
    except Exception:
        adapter.close()
        raise


def _safe_validation_message(scope: str, error: Exception) -> str:
    """Describe bad fields without echoing secret configuration values."""
    if not isinstance(error, ValidationError):
        return f"Invalid {scope} configuration: {error}"
    problems = []
    for problem in error.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in problem["loc"])
        problems.append(f"{location}: {problem['msg']}")
    return f"Invalid {scope} configuration: " + "; ".join(problems)
