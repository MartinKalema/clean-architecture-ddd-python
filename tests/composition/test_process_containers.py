"""Each executable has an isolated composition root and resource budget."""
import pytest

from scripts.seed_etcd_config import build_config
from src.composition.runtime_config import ProcessRole, load_runtime_config
from src.container import (
    CliContainer,
    Container,
    MaintenanceContainer,
    NotificationContainer,
    ProjectionContainer,
    ReaperContainer,
    WorkflowContainer,
)


def _configure(container, role: ProcessRole):
    settings = load_runtime_config(build_config())
    container.bootstrap.from_dict(
        {"etcd": {"host": "localhost", "port": 2379, "prefix": "/config/"}}
    )
    container.configurations.from_dict(settings.for_process(role))
    container.check_dependencies()
    return container


def test_api_and_cli_wire_only_their_own_delivery_modules():
    assert all("presentation.api" in module for module in Container.wiring_config.modules)
    assert all("presentation.cli" in module for module in CliContainer.wiring_config.modules)


def test_circuit_registry_is_container_scoped_and_api_reports_only_api_usage():
    first = _configure(Container(), ProcessRole.API)
    second = _configure(Container(), ProcessRole.API)
    try:
        first.elasticsearch_circuit_breaker()
        second.elasticsearch_circuit_breaker()

        assert first.circuit_breaker_registry() is not second.circuit_breaker_registry()
        assert set(first.circuit_breaker_registry().get_all_status()) == {
            "elasticsearch"
        }
        assert set(second.circuit_breaker_registry().get_all_status()) == {
            "elasticsearch"
        }
    finally:
        first.unwire()
        second.unwire()


def test_database_pool_budget_is_selected_per_process():
    api = _configure(Container(), ProcessRole.API)
    workflow = _configure(WorkflowContainer(), ProcessRole.WORKFLOW)
    notification = _configure(NotificationContainer(), ProcessRole.NOTIFICATION)
    try:
        assert api.postgresql().engine.pool.size() == 20
        assert workflow.postgresql().engine.pool.size() == 5
        assert notification.postgresql().engine.pool.size() == 3
    finally:
        api.unwire()


@pytest.mark.parametrize(
    ("container_type", "role", "providers"),
    [
        (
            Container,
            ProcessRole.API,
            ("add_book", "get_book_handler", "get_loan_handler"),
        ),
        (
            WorkflowContainer,
            ProcessRole.WORKFLOW,
            ("domain_event_consumer",),
        ),
        (
            NotificationContainer,
            ProcessRole.NOTIFICATION,
            ("notification_event_consumer",),
        ),
        (
            ProjectionContainer,
            ProcessRole.PROJECTION,
            ("elasticsearch_sync_consumer",),
        ),
        (
            ReaperContainer,
            ProcessRole.REAPER,
            ("release_expired_reservations",),
        ),
        (
            MaintenanceContainer,
            ProcessRole.MAINTENANCE,
            ("postgresql", "kafka_client", "elasticsearch_client"),
        ),
        (
            CliContainer,
            ProcessRole.CLI,
            ("add_book", "list_books_handler", "borrow_book"),
        ),
    ],
)
def test_every_production_process_graph_resolves(
    container_type,
    role: ProcessRole,
    providers: tuple[str, ...],
):
    container = _configure(container_type(), role)
    try:
        for provider_name in providers:
            assert getattr(container, provider_name)() is not None
    finally:
        container.unwire()
