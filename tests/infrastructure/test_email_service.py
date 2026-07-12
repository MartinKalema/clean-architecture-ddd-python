"""
Unit tests for SendGrid email service failure classification.

The breaker must trip on service-health failures (rate limits, timeouts, 5xx,
connection errors) but not deterministic request-level rejections.
"""
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import pytest

from src.application.ports import EmailDeliveryException
from src.infrastructure.adapters.email.sendgrid_email_service import (
    SendGridEmailService,
)
from src.infrastructure.adapters.resilience import CircuitBreaker
from src.infrastructure.external.sendgrid_client import SendGridClient


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
        logger=MagicMock(),
        circuit_breaker=CircuitBreaker(
            name="sendgrid-test",
            failure_threshold=2,
            excluded_exceptions=(EmailDeliveryException,),
        ),
    )


@pytest.mark.asyncio
async def test_recipient_payload_rejection_is_permanent_and_never_trips_breaker():
    service = _service(send_error=_HttpError(422))

    # Far more failures than the threshold...
    for _ in range(5):
        with pytest.raises(EmailDeliveryException):
            await service.send_email("p@example.com", "s", "c")

    # ...but SendGrid is up and answering: the circuit stays closed
    assert service._circuit_breaker.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 404, 405])
async def test_auth_and_endpoint_failures_are_operational_and_trip_breaker(
    status_code,
):
    service = _service(send_error=_HttpError(status_code))

    for _ in range(2):
        with pytest.raises(_HttpError):
            await service.send_email("p@example.com", "s", "c")

    assert service._circuit_breaker.is_open


@pytest.mark.asyncio
async def test_rate_limit_is_transient_and_trips_the_breaker():
    service = _service(send_error=_HttpError(429))

    for _ in range(2):
        with pytest.raises(_HttpError):
            await service.send_email("p@example.com", "s", "c")

    assert service._circuit_breaker.is_open


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

    service.client.send.assert_called_once_with(
        from_email="library@example.com",
        to_email="p@example.com",
        subject="subject",
        content_str="content",
    )
    assert service._circuit_breaker.is_closed


def test_sendgrid_sdk_receives_a_real_transport_timeout():
    sdk = MagicMock()
    sdk.client.mail.send.post.return_value = SimpleNamespace(status_code=202)

    with (
        patch(
            "src.infrastructure.external.sendgrid_client.sendgrid.SendGridAPIClient",
            return_value=sdk,
        ),
        patch(
            "src.infrastructure.external.sendgrid_client.Email",
            side_effect=lambda value: value,
        ),
        patch(
            "src.infrastructure.external.sendgrid_client.To",
            side_effect=lambda value: value,
        ),
        patch(
            "src.infrastructure.external.sendgrid_client.Content",
            side_effect=lambda *values: values,
        ),
        patch(
            "src.infrastructure.external.sendgrid_client.Mail",
            return_value=MagicMock(get=lambda: {"mail": "payload"}),
        ),
    ):
        client = SendGridClient(
            api_key="SG.test",
            logger=MagicMock(),
            request_timeout_seconds=7.5,
        )
        status = client.send(
            from_email="library@example.com",
            to_email="patron@example.com",
            subject="subject",
            content_str="<p>content</p>",
        )

    assert status == 202
    sdk.client.mail.send.post.assert_called_once_with(
        request_body=ANY,
        timeout=7.5,
    )
