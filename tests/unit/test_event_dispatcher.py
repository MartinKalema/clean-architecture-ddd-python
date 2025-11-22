import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from src.infrastructure.adapters.messaging.rabbitmq_event_dispatcher import RabbitMQEventDispatcher
from src.infrastructure.adapters.email.sendgrid_email_service import SendGridEmailService
from src.application.handlers.book_handlers import BookHandlers
from src.domain.events.book_events import BookBorrowed

@pytest.mark.asyncio
async def test_rabbitmq_dispatcher():
    # Mock the client
    mock_client = AsyncMock()
    
    dispatcher = RabbitMQEventDispatcher(client=mock_client)
    event = BookBorrowed(
        book_id="123",
        title="Test Book",
        borrowed_at=datetime.now(),
        return_due_date=datetime.now() + timedelta(days=14),
        borrower_email="test@example.com"
    )
    
    await dispatcher.dispatch(event)
    
    # Verify
    mock_client.connect.assert_called_once()
    mock_client.publish.assert_called_once()

@pytest.mark.asyncio
async def test_sendgrid_service():
    # Mock the client
    mock_client = MagicMock()
    
    service = SendGridEmailService(client=mock_client, from_email="from@test.com", admin_email="admin@test.com")
    
    await service.send_email("to@test.com", "Subject", "Body")
    
    # Verify
    mock_client.send.assert_called_once()

@pytest.mark.asyncio
async def test_book_handler():
    mock_email_service = AsyncMock()
    handler = BookHandlers(email_service=mock_email_service)
    
    event = BookBorrowed(
        book_id="123",
        title="Test Book",
        borrowed_at=datetime.now(),
        return_due_date=datetime.now() + timedelta(days=14),
        borrower_email="user@example.com"
    )
    
    await handler.handle_book_borrowed(event)
    
    mock_email_service.send_email.assert_called_once()
    call_args = mock_email_service.send_email.call_args
    assert call_args.kwargs['to_email'] == "user@example.com"
    assert "Test Book" in call_args.kwargs['subject']
