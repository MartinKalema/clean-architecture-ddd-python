from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.event_handlers.book_handlers import BookHandlers
from src.domain.catalog import BookBorrowed
from src.domain.shared_kernel import EmailTemplate
from src.infrastructure.adapters.email.sendgrid_email_service import (
    SendGridEmailService,
)
from src.infrastructure.adapters.messaging.rabbitmq_event_dispatcher import (
    RabbitMQEventDispatcher,
)
from src.infrastructure.adapters.resilience import CircuitBreaker


@pytest.mark.asyncio
async def test_rabbitmq_dispatcher():
    # Mock the client and dependencies
    mock_client = AsyncMock()
    mock_logger = MagicMock()
    circuit_breaker = CircuitBreaker(name="test_rabbitmq", logger=mock_logger)

    dispatcher = RabbitMQEventDispatcher(
        client=mock_client,
        exchange_name="test_exchange",
        logger=mock_logger,
        circuit_breaker=circuit_breaker,
    )
    event = BookBorrowed(
        book_id="123",
        title="Test Book",
        borrowed_at=datetime.now(),
        return_due_date=datetime.now() + timedelta(days=14),
        borrower_email="test@example.com"
    )

    await dispatcher.dispatch(event)

    mock_client.publish.assert_called_once()


@pytest.mark.asyncio
async def test_sendgrid_service():
    # Mock the client and dependencies
    mock_client = MagicMock()
    mock_logger = MagicMock()
    circuit_breaker = CircuitBreaker(name="test_sendgrid", logger=mock_logger)

    service = SendGridEmailService(
        client=mock_client,
        from_email="from@test.com",
        admin_email="admin@test.com",
        logger=mock_logger,
        circuit_breaker=circuit_breaker,
    )

    await service.send_email("to@test.com", "Subject", "Body")

    mock_client.send.assert_called_once()


@pytest.mark.asyncio
async def test_book_handler():
    mock_email_service = AsyncMock()
    mock_template_renderer = MagicMock()
    mock_logger = MagicMock()
    mock_template_renderer.render.return_value = "<html>Content</html>"

    handler = BookHandlers(email_service=mock_email_service, template_renderer=mock_template_renderer, logger=mock_logger)

    event = BookBorrowed(
        book_id="123",
        title="Test Book",
        borrowed_at=datetime.now(),
        return_due_date=datetime.now() + timedelta(days=14),
        borrower_email="user@example.com"
    )

    await handler.handle_book_borrowed(event)

    mock_template_renderer.render.assert_called_once()
    # Verify it was called with the Enum, not a string
    assert mock_template_renderer.render.call_args[0][0] == EmailTemplate.BOOK_BORROWED

    mock_email_service.send_email.assert_called_once()
    call_args = mock_email_service.send_email.call_args
    assert call_args.kwargs['to_email'] == "user@example.com"
    assert "Test Book" in call_args.kwargs['subject']
    assert call_args.kwargs['content'] == "<html>Content</html>"
