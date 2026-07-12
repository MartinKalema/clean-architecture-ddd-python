"""Explicit records for legacy workflows that could not be replayed safely."""

from dataclasses import dataclass

from src.domain.shared_kernel import DomainEvent


@dataclass(frozen=True)
class LegacyWorkflowCompensated(DomainEvent):
    """A pre-correlation event was reconciled during a schema migration.

    This is an operational integration event, not a new domain transition.
    It keeps a transferred polling-outbox row consumable while the companion
    migration-audit table retains the exact reason for operator review.
    """

    original_event_type: str
    aggregate_type: str
    aggregate_id: str
    reason: str
