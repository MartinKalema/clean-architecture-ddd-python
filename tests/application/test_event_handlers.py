"""
Unit tests for application-layer event handlers.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.event_handlers import SendLoanConfirmationEmailHandler
from src.domain.lending import LoanCreated


@pytest.mark.asyncio
async def test_loan_created_sends_confirmation_email():
    email_service = AsyncMock()
    handler = SendLoanConfirmationEmailHandler(email_service, logger=MagicMock())

    event = LoanCreated(
        loan_id="loan-1",
        patron_id="patron-1",
        patron_email="patron@example.com",
        book_id="book-1",
        book_title="Clean Architecture",
        borrowed_at=datetime(2026, 7, 4, 12, 0),
        due_date=datetime(2026, 7, 18, 12, 0),
    )

    await handler.handle(event)

    email_service.send_email.assert_awaited_once()
    kwargs = email_service.send_email.await_args.kwargs
    assert kwargs["to_email"] == "patron@example.com"
    assert "Clean Architecture" in kwargs["subject"]
    assert "2026-07-18" in kwargs["content"]
