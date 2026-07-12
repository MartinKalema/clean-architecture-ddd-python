"""Patron-to-borrowing anti-corruption mapping."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.adapters.patron.borrower_directory import (
    PatronBorrowerDirectoryAdapter,
)
from src.infrastructure.adapters.patron.patron_model import PatronModel


def _patron(*, tier: str = "premium", suspended: bool = False):
    return PatronModel(
        id="patron-1",
        first_name="Test",
        last_name="Patron",
        email="patron@example.com",
        membership_tier=tier,
        is_suspended=suspended,
        suspended_reason="policy" if suspended else None,
        registered_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _directory(patron: PatronModel):
    result = MagicMock()
    result.scalar_one_or_none.return_value = patron
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    return PatronBorrowerDirectoryAdapter(MagicMock(return_value=context))


@pytest.mark.asyncio
async def test_translates_only_borrowing_entitlements():
    directory = _directory(_patron())

    profile = await directory.find_by_email("patron@example.com")

    assert profile is not None
    assert profile.patron_id == "patron-1"
    assert profile.membership_tier == "premium"
    assert profile.is_eligible is True


@pytest.mark.asyncio
async def test_suspension_is_translated_without_leaking_patron_dto():
    directory = _directory(_patron(suspended=True))

    profile = await directory.get_by_id("patron-1")

    assert profile is not None
    assert profile.is_eligible is False
    assert profile.ineligible_reason == "patron is suspended"
