"""Application-owned integration events that are not domain facts."""

from .migration_events import LegacyWorkflowCompensated

__all__ = ["LegacyWorkflowCompensated"]
