"""Production composition must fail before constructing partially configured clients."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from scripts.seed_etcd_config import build_config
from src.composition.bootstrap import bootstrap_container
from src.composition.runtime_config import ProcessRole, load_runtime_config
from src.infrastructure.exceptions import ConfigurationException


def test_current_runtime_configuration_is_complete_and_role_scoped():
    settings = load_runtime_config(build_config())

    assert settings.for_process(ProcessRole.API)["database"] | {} == {
        "url": settings.database.url,
        "pool_timeout": settings.database.pool_timeout,
        "pool_recycle": settings.database.pool_recycle,
        "pool_size": 20,
        "max_overflow": 10,
    }
    assert settings.for_process(ProcessRole.WORKFLOW)["database"]["pool_size"] == 5
    assert settings.for_process(ProcessRole.NOTIFICATION)["database"]["pool_size"] == 3
    assert settings.for_process(ProcessRole.REAPER)["database"]["pool_size"] == 2


def test_missing_required_configuration_is_rejected():
    raw = deepcopy(build_config())
    del raw["database"]["url"]

    with pytest.raises(ValidationError) as error:
        load_runtime_config(raw)

    assert error.value.errors()[0]["loc"] == ("database", "url")


def test_unknown_pre_baseline_configuration_key_is_rejected():
    raw = deepcopy(build_config())
    raw["database"]["pool_size"] = 200

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_runtime_config(raw)


def test_cross_process_consumer_group_reuse_is_rejected():
    raw = deepcopy(build_config())
    raw["kafka"]["notification_group_id"] = raw["kafka"]["workflow_group_id"]

    with pytest.raises(ValidationError, match="consumer group IDs must be distinct"):
        load_runtime_config(raw)


def test_bootstrap_closes_etcd_and_redacts_secret_values_on_validation_failure(
    monkeypatch,
):
    raw = deepcopy(build_config())
    secret = raw["sendgrid"]["api_key"]
    del raw["database"]["url"]
    adapter = MagicMock()
    adapter.get_all.return_value = raw
    container = SimpleNamespace(
        bootstrap=MagicMock(),
        configurations=MagicMock(),
        etcd_adapter=MagicMock(return_value=adapter),
        check_dependencies=MagicMock(),
    )
    monkeypatch.setenv("ETCD_PORT", "2379")

    with pytest.raises(ConfigurationException) as error:
        bootstrap_container(container, ProcessRole.API)

    adapter.close.assert_called_once()
    assert "database.url" in str(error.value)
    assert secret not in str(error.value)
    container.configurations.from_dict.assert_not_called()
