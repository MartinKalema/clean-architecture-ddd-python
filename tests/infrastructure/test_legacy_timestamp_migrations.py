"""Contract tests for deterministic conversion of pre-UTC timestamps."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

from migrations.legacy_naive_time import (
    UNSAFE_REVISION_002_ACK_ENV,
    UNSAFE_REVISION_002_ACK_VALUE,
    localize_unambiguous_legacy_datetime,
    require_safe_revision_002_provenance,
    require_legacy_naive_timezone,
    timezone_sql_literal,
)


ROOT = Path(__file__).resolve().parents[2]


def _load_revision_002():
    path = (
        ROOT
        / "migrations/versions/20260704_000002_debezium_outbox.py"
    )
    spec = importlib.util.spec_from_file_location("legacy_revision_002", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_revision(filename: str, module_name: str):
    path = ROOT / "migrations/versions" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_empty_schema_does_not_require_legacy_timezone(monkeypatch):
    monkeypatch.delenv("LEGACY_NAIVE_TIMEZONE", raising=False)

    assert require_legacy_naive_timezone(
        has_legacy_timestamps=False,
        revision="005",
    ) == "UTC"


def test_nonempty_schema_requires_explicit_legacy_timezone(monkeypatch):
    monkeypatch.delenv("LEGACY_NAIVE_TIMEZONE", raising=False)

    with pytest.raises(RuntimeError, match="LEGACY_NAIVE_TIMEZONE"):
        require_legacy_naive_timezone(
            has_legacy_timestamps=True,
            revision="006",
        )


@pytest.mark.parametrize(
    "timezone_name",
    (
        " UTC",
        "UTC ",
        "UTC'; DROP TABLE loans; --",
        "Not/A_Timezone",
    ),
)
def test_legacy_timezone_must_be_a_safe_available_iana_name(
    monkeypatch,
    timezone_name,
):
    monkeypatch.setenv("LEGACY_NAIVE_TIMEZONE", timezone_name)

    with pytest.raises(RuntimeError, match="LEGACY_NAIVE_TIMEZONE"):
        require_legacy_naive_timezone(
            has_legacy_timestamps=True,
            revision="006",
        )


def test_valid_legacy_timezone_has_a_safe_sql_literal(monkeypatch):
    monkeypatch.setenv("LEGACY_NAIVE_TIMEZONE", "Asia/Qatar")

    timezone_name = require_legacy_naive_timezone(
        has_legacy_timestamps=True,
        revision="006",
    )

    assert timezone_name == "Asia/Qatar"
    assert timezone_sql_literal(timezone_name) == "'Asia/Qatar'"


def test_revision_002_provenance_is_required_before_contract_migrations(
    monkeypatch,
):
    monkeypatch.delenv(UNSAFE_REVISION_002_ACK_ENV, raising=False)

    class Connection:
        @staticmethod
        def scalar(_statement):
            return None

    with pytest.raises(RuntimeError, match="Cannot prove that revision 002"):
        require_safe_revision_002_provenance(Connection())


def test_revision_002_operator_audit_acknowledgement_is_recorded(monkeypatch):
    monkeypatch.setenv(
        UNSAFE_REVISION_002_ACK_ENV,
        UNSAFE_REVISION_002_ACK_VALUE,
    )

    class Connection:
        statements = []

        @staticmethod
        def scalar(_statement):
            return None

        @classmethod
        def execute(cls, statement, parameters):
            cls.statements.append((str(statement), parameters))

    require_safe_revision_002_provenance(Connection())

    assert Connection.statements
    assert Connection.statements[0][1]["value"] == UNSAFE_REVISION_002_ACK_VALUE


@pytest.mark.parametrize(
    ("has_rows", "configured_timezone", "expected_timezone"),
    (
        (False, None, "UTC"),
        (True, "Asia/Qatar", "Asia/Qatar"),
    ),
)
def test_revision_006_uses_default_only_for_empty_legacy_tables(
    monkeypatch,
    has_rows,
    configured_timezone,
    expected_timezone,
):
    migration = _load_revision(
        "20260711_000006_command_correctness.py",
        f"legacy_revision_006_{has_rows}",
    )
    if configured_timezone is None:
        monkeypatch.delenv("LEGACY_NAIVE_TIMEZONE", raising=False)
    else:
        monkeypatch.setenv(
            "LEGACY_NAIVE_TIMEZONE",
            configured_timezone,
        )

    class Connection:
        @staticmethod
        def scalar(_statement):
            return has_rows

    conversions = []
    monkeypatch.setattr(
        migration.op,
        "alter_column",
        lambda table, column, **kwargs: conversions.append(
            (table, column, kwargs["postgresql_using"])
        ),
    )
    monkeypatch.setattr(
        migration,
        "validate_legacy_timestamp_columns",
        lambda *_args, **_kwargs: None,
    )

    migration._timestamps_to_utc(Connection())

    assert len(conversions) == 7
    assert all(
        f"'{expected_timezone}'" in clause
        for _table, _column, clause in conversions
    )
    returned_clause = next(
        clause
        for table, column, clause in conversions
        if table == "loans" and column == "returned_at"
    )
    assert "legacy_returned_at_utc" in returned_clause
    assert "AT TIME ZONE 'UTC'" in returned_clause


def test_revision_006_aborts_nonempty_conversion_without_timezone(
    monkeypatch,
):
    migration = _load_revision(
        "20260711_000006_command_correctness.py",
        "legacy_revision_006_missing_timezone",
    )
    monkeypatch.delenv("LEGACY_NAIVE_TIMEZONE", raising=False)

    class Connection:
        @staticmethod
        def scalar(_statement):
            return True

    monkeypatch.setattr(
        migration.op,
        "alter_column",
        lambda *_args, **_kwargs: pytest.fail(
            "DDL must not start before timezone validation"
        ),
    )

    with pytest.raises(RuntimeError, match="LEGACY_NAIVE_TIMEZONE"):
        migration._timestamps_to_utc(Connection())


def test_revision_002_normalizes_naive_and_aware_values_to_same_instant():
    migration = _load_revision_002()
    local_wall_time = datetime(2026, 7, 11, 12, 0)
    same_aware_instant = datetime(2026, 7, 11, 9, 0, tzinfo=timezone.utc)

    normalized_naive = migration._legacy_datetime_as_utc(
        local_wall_time,
        row_id="legacy-row",
        field_name="occurred_at",
        legacy_timezone="Asia/Qatar",
    )
    normalized_aware = migration._legacy_datetime_as_utc(
        same_aware_instant,
        row_id="legacy-row",
        field_name="occurred_at",
        legacy_timezone="Asia/Qatar",
    )

    assert normalized_naive == normalized_aware == same_aware_instant
    assert migration._legacy_occurred_at(
        normalized_naive.isoformat(),
        fallback=None,
        row_id="legacy-row",
        legacy_timezone="Asia/Qatar",
    ) == same_aware_instant.replace(tzinfo=None)


def test_revision_002_preserves_aware_repeated_hour_as_exact_utc():
    migration = _load_revision_002()
    repeated_hour = datetime.fromisoformat("2024-11-03T01:30:00-04:00")

    stored = migration._legacy_occurred_at(
        repeated_hour,
        fallback=None,
        row_id="legacy-aware-dst",
        legacy_timezone="America/New_York",
    )

    assert stored == datetime(2024, 11, 3, 5, 30)


def test_revision_004_preserves_correlated_return_instant_through_utc_flag():
    migration = _load_revision(
        "20260711_000004_reservation_correlation.py",
        "legacy_revision_004_return_timestamp",
    )
    repeated_hour = datetime.fromisoformat("2024-11-03T01:30:00-04:00")

    assert migration._legacy_utc_naive(
        repeated_hour,
        row_id="legacy-return",
    ) == datetime(2024, 11, 3, 5, 30)


@pytest.mark.parametrize(
    ("value", "kind"),
    (
        (datetime(2024, 3, 10, 2, 30), "nonexistent"),
        (datetime(2024, 11, 3, 1, 30), "ambiguous"),
    ),
)
def test_revision_002_rejects_dst_times_with_no_unique_instant(value, kind):
    migration = _load_revision_002()

    with pytest.raises(RuntimeError, match=kind):
        migration._legacy_datetime_as_utc(
            value,
            row_id="legacy-row",
            field_name="occurred_at",
            legacy_timezone="America/New_York",
        )


@pytest.mark.parametrize(
    ("value", "kind"),
    (
        (datetime(2024, 3, 10, 2, 30), "nonexistent"),
        (datetime(2024, 11, 3, 1, 30), "ambiguous"),
    ),
)
def test_contract_timestamp_validator_rejects_lossy_dst_conversion(value, kind):
    with pytest.raises(RuntimeError, match=kind):
        localize_unambiguous_legacy_datetime(
            value,
            timezone_name="America/New_York",
            location="revision 006 row loans.loan-1.borrowed_at",
        )


def test_revision_002_fences_legacy_writers_during_transfer():
    source = (
        ROOT / "migrations/versions/20260704_000002_debezium_outbox.py"
    ).read_text()

    assert "LOCK TABLE outbox_messages IN ACCESS EXCLUSIVE MODE" in source


def test_timestamp_contract_migrations_do_not_hardcode_utc_interpretation():
    revision_paths = (
        ROOT / "migrations/versions/20260711_000005_event_delivery.py",
        ROOT / "migrations/versions/20260711_000006_command_correctness.py",
    )

    for path in revision_paths:
        source = path.read_text()
        assert "require_legacy_naive_timezone" in source
        assert "validate_legacy_timestamp_columns" in source
        if "000005" in path.name:
            assert "occurred_at_storage" in source
            assert "AT TIME ZONE 'UTC'" in source
        else:
            assert "legacy_returned_at_utc" in source
            assert "AT TIME ZONE 'UTC'" in source


def test_revision_002_datetime_map_covers_every_migratable_event():
    migration = _load_revision_002()

    assert set(migration._LEGACY_DATETIME_FIELDS) == set(
        migration._AGGREGATE_BY_EVENT
    )
    assert all(
        "occurred_at" in field_names
        for field_names in migration._LEGACY_DATETIME_FIELDS.values()
    )
