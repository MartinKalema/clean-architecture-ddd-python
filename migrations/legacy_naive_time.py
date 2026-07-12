"""Safety helpers for converting legacy naive timestamps.

The pre-006 application used local ``datetime.now()`` values.  A migration
cannot infer which wall-clock timezone produced those values, and PostgreSQL's
session timezone is not a reliable substitute.  Contract migrations must ask
the operator for that historical timezone whenever rows actually need to be
converted.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import sqlalchemy as sa


LEGACY_NAIVE_TIMEZONE_ENV = "LEGACY_NAIVE_TIMEZONE"
UNSAFE_REVISION_002_ACK_ENV = "ACKNOWLEDGE_UNSAFE_LEGACY_002"
UNSAFE_REVISION_002_ACK_VALUE = "I_AUDITED_BACKUP_AND_WAL_FOR_REVISION_002"
_IANA_TIMEZONE_NAME = re.compile(
    r"[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*\Z"
)


def require_legacy_naive_timezone(
    *,
    has_legacy_timestamps: bool,
    revision: str,
) -> str:
    """Return a validated IANA zone for a legacy timestamp conversion.

    Empty installations have no instant to reinterpret, so they deliberately
    use UTC without requiring deployment configuration.  Any non-empty legacy
    source must be accompanied by an explicit operator decision.
    """
    if not has_legacy_timestamps:
        return "UTC"

    timezone_name = os.environ.get(LEGACY_NAIVE_TIMEZONE_ENV)
    if timezone_name is None or not timezone_name:
        raise RuntimeError(
            f"Migration {revision} found legacy naive timestamps. Set "
            f"{LEGACY_NAIVE_TIMEZONE_ENV} to the IANA timezone used by the "
            "legacy application hosts (for example, 'UTC' or 'Asia/Qatar') "
            "before retrying."
        )
    if timezone_name != timezone_name.strip():
        raise RuntimeError(
            f"Migration {revision}: {LEGACY_NAIVE_TIMEZONE_ENV} must not "
            "contain surrounding whitespace."
        )
    if _IANA_TIMEZONE_NAME.fullmatch(timezone_name) is None:
        raise RuntimeError(
            f"Migration {revision}: {LEGACY_NAIVE_TIMEZONE_ENV}="
            f"{timezone_name!r} is not a valid IANA timezone name."
        )
    try:
        if timezone_name not in available_timezones():
            raise ZoneInfoNotFoundError(timezone_name)
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise RuntimeError(
            f"Migration {revision}: {LEGACY_NAIVE_TIMEZONE_ENV}="
            f"{timezone_name!r} is not available in the IANA timezone "
            "database."
        ) from error
    return timezone_name


def timezone_sql_literal(timezone_name: str) -> str:
    """Return a SQL literal after validating the restricted IANA grammar.

    Alembic's PostgreSQL ``USING`` clause is SQL text and cannot carry a bind
    parameter.  The same grammar used above excludes quotes and SQL syntax;
    escaping remains defense in depth for future timezone database changes.
    """
    if _IANA_TIMEZONE_NAME.fullmatch(timezone_name) is None:
        raise ValueError("timezone_name must be a validated IANA timezone")
    return "'" + timezone_name.replace("'", "''") + "'"


def require_safe_revision_002_provenance(connection) -> None:
    """Fail closed when the running 002 body cannot be proven lossless.

    An installation stamped by the historical destructive 002 skips the
    patched migration body. Revision 004 ensures the marker table exists but
    deliberately does not forge this proof. Operators may continue only after
    an explicit backup/WAL audit acknowledgement.
    """
    value = connection.scalar(
        sa.text(
            """
            SELECT value
              FROM migration_safety_markers
             WHERE name = 'revision-002-lossless-outbox'
            """
        )
    )
    if value == "locked-copy-and-explicit-timezone-v2":
        return

    if os.environ.get(UNSAFE_REVISION_002_ACK_ENV) != UNSAFE_REVISION_002_ACK_VALUE:
        raise RuntimeError(
            "Cannot prove that revision 002 preserved pending outbox rows and "
            "timestamp provenance. Recover/audit the pre-002 backup and WAL, "
            f"then set {UNSAFE_REVISION_002_ACK_ENV}="
            f"{UNSAFE_REVISION_002_ACK_VALUE} to acknowledge the result."
        )

    connection.execute(
        sa.text(
            """
            INSERT INTO migration_safety_markers (name, value)
            VALUES ('revision-002-operator-audit', :value)
            ON CONFLICT (name) DO UPDATE
                SET value = EXCLUDED.value, recorded_at = CURRENT_TIMESTAMP
            """
        ),
        {"value": UNSAFE_REVISION_002_ACK_VALUE},
    )


_SQL_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_VALIDATION_BATCH_SIZE = 500


def localize_unambiguous_legacy_datetime(
    value: datetime,
    *,
    timezone_name: str,
    location: str,
) -> datetime:
    """Attach a legacy timezone only when the wall time has one UTC instant.

    PostgreSQL's ``AT TIME ZONE`` silently chooses one side of a repeated DST
    hour and silently shifts a wall time that never existed.  Contract
    migrations must reject both cases so an operator can reconcile the source
    row instead of committing an invented instant.
    """
    if not isinstance(value, datetime):
        raise RuntimeError(f"Cannot migrate {location}: timestamp is invalid")
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value

    zone = ZoneInfo(timezone_name)
    candidates: list[datetime] = []
    instants: set[datetime] = set()
    for fold in (0, 1):
        candidate = value.replace(tzinfo=zone, fold=fold)
        instant = candidate.astimezone(timezone.utc)
        round_trip = instant.astimezone(zone).replace(tzinfo=None)
        if round_trip == value and instant not in instants:
            candidates.append(candidate)
            instants.add(instant)

    if len(candidates) != 1:
        kind = "ambiguous" if candidates else "nonexistent"
        raise RuntimeError(
            f"Cannot migrate {location}: timestamp is an {kind} local time "
            f"in {timezone_name}; reconcile it manually."
        )
    return candidates[0]


def validate_legacy_timestamp_columns(
    connection,
    *,
    table_columns: Mapping[str, Sequence[str]],
    timezone_name: str,
    revision: str,
    row_filters: Mapping[str, str] | None = None,
    trusted_utc_flags: Mapping[tuple[str, str], str] | None = None,
) -> None:
    """Keyset-scan legacy timestamp columns and reject lossy DST conversion.

    ``row_filters`` is migration-authored SQL, never operator input. It exists
    for mixed-provenance transitions such as revision 005, where rows marked
    as UTC-naive have an exact instant and must not be reinterpreted as local
    wall time.
    """
    for table_name, column_names in table_columns.items():
        flag_names = tuple(
            flag
            for (flag_table, _flag_column), flag in (trusted_utc_flags or {}).items()
            if flag_table == table_name
        )
        identifiers = (table_name, "id", *column_names, *flag_names)
        if any(_SQL_IDENTIFIER.fullmatch(name) is None for name in identifiers):
            raise ValueError("legacy timestamp validation requires SQL identifiers")

        selected_columns = ", ".join(("id", *column_names, *flag_names))
        non_null = " OR ".join(f"{name} IS NOT NULL" for name in column_names)
        row_filter = (row_filters or {}).get(table_name, "TRUE")
        query = sa.text(
            f"""
            SELECT {selected_columns}
              FROM {table_name}
             WHERE ({non_null})
               AND ({row_filter})
               AND (:last_id IS NULL OR id > :last_id)
             ORDER BY id
             LIMIT :batch_size
            """
        ).bindparams(
            sa.bindparam("last_id", type_=sa.String()),
            sa.bindparam("batch_size", type_=sa.Integer()),
        )

        last_id = None
        while True:
            rows = connection.execute(
                query,
                {
                    "last_id": last_id,
                    "batch_size": _VALIDATION_BATCH_SIZE,
                },
            ).mappings().all()
            if not rows:
                break
            for row in rows:
                for column_name in column_names:
                    value = row[column_name]
                    flag_name = (trusted_utc_flags or {}).get(
                        (table_name, column_name)
                    )
                    if value is not None and not (
                        flag_name is not None and row[flag_name]
                    ):
                        localize_unambiguous_legacy_datetime(
                            value,
                            timezone_name=timezone_name,
                            location=(
                                f"revision {revision} row "
                                f"{table_name}.{row['id']}.{column_name}"
                            ),
                        )
            last_id = rows[-1]["id"]
