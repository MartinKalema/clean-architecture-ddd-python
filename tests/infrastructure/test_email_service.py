"""
Unit tests for SendGrid email service failure classification.

The breaker must trip on service-health failures (timeouts, 5xx,
connection errors) but NOT on request-level rejections (4xx) — a 401
means SendGrid is up and answering, and retrying it cannot succeed.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.domain.shared_kernel import EmailDeliveryException
from src.infrastructure.adapters.email.sendgrid_email_service import (
    SendGridEmailService,
)
from src.infrastructure.adapters.resilience import CircuitBreaker


class _HttpError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP Error {status_code}")
        self.status_code = status_code


def _service(send_error=None) -> SendGridEmailService:
    client = MagicMock()
    if send_error is not None:
        client.send.side_effect = send_error
    return SendGridEmailService(
        client=client,
        from_email="library@example.com",
        admin_email="admin@example.com",
        logger=MagicMock(),
        circuit_breaker=CircuitBreaker(
            name="sendgrid-test",
            failure_threshold=2,
            excluded_exceptions=(EmailDeliveryException,),
        ),
    )


@pytest.mark.asyncio
async def test_4xx_raises_permanent_and_never_trips_the_breaker():
    service = _service(send_error=_HttpError(401))

    # Far more failures than the threshold...
    for _ in range(5):
        with pytest.raises(EmailDeliveryException):
            await service.send_email("p@example.com", "s", "c")

    # ...but SendGrid is up and answering: the circuit stays closed
    assert service._circuit_breaker.is_closed


@pytest.mark.asyncio
async def test_5xx_counts_as_service_failure_and_trips_the_breaker():
    service = _service(send_error=_HttpError(503))

    for _ in range(2):
        with pytest.raises(_HttpError):
            await service.send_email("p@example.com", "s", "c")

    assert service._circuit_breaker.is_open


@pytest.mark.asyncio
async def test_successful_send_reports_success():
    service = _service()

    await service.send_email("p@example.com", "subject", "content")

    service.client.send.assert_called_once()
    assert service._circuit_breaker.is_closed
