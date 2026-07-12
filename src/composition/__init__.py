"""Process composition, validated configuration, and resource ownership."""

from .runtime_config import ProcessRole, RuntimeConfig, load_runtime_config

__all__ = ["ProcessRole", "RuntimeConfig", "load_runtime_config"]
