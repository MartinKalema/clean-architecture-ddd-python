"""
SendGrid Email Service with Circuit Breaker protection.

The circuit breaker prevents cascading failures when SendGrid is unavailable,
allowing the system to queue emails for later delivery or use fallback
notification mechanisms.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.shared_kernel import EmailDeliveryException
from src.infrastructure.adapters.resilience import CircuitBreakerOpenException

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger
    from src.infrastructure.adapters.resilience import CircuitBreaker
    from src.infrastructure.external.sendgrid_client import SendGridClient


class SendGridEmailService:
    """
    Email service implementation using SendGrid.

    Features:
    - Circuit breaker protection for resilience (injected)
    - Automatic CC to admin for audit trail
    - Structured logging
    """

    def __init__(
        self,
        client: SendGridClient,
        from_email: str,
        admin_email: str,
        logger: ILogger,
        circuit_breaker: CircuitBreaker,
    ):
        self.client = client
        self.from_email = from_email
        self.admin_email = admin_email
        self.logger = logger
        self._circuit_breaker = circuit_breaker

    @property
    def circuit_breaker_status(self) -> dict:
        """Get circuit breaker status for health checks."""
        return self._circuit_breaker.get_status()

    def _do_send_email(
        self,
        to_email: str,
        subject: str,
        content: str,
    ) -> None:
        """Internal method to send email."""
        try:
            self.client.send(
                from_email=self.from_email,
                to_email=to_email,
                subject=subject,
                content_str=content,
                cc_email=self.admin_email
            )
        except Exception as e:
            status = getattr(e, "status_code", None)
            if status is not None and 400 <= status < 500:
                # A 4xx means SendGrid is up and rejecting this request
                # (bad credentials, invalid recipient). That is a permanent
                # failure, not a service-health signal: it must not trip
                # the circuit breaker (excluded in the container wiring)
                # and retrying it will not change the outcome.
                raise EmailDeliveryException(
                    f"SendGrid rejected the send ({status}): {e}",
                    original_exception=e,
                )
            raise

    async def send_email(self, to_email: str, subject: str, content: str) -> None:
        """
        Send an email via SendGrid.

        Protected by circuit breaker - will fail fast if SendGrid is down.

        Raises:
            EmailDeliveryException: Permanent — SendGrid rejected the send
                                    (4xx: bad credentials, invalid recipient);
                                    retrying will not change the outcome, and
                                    it does not count toward the breaker
            CircuitBreakerOpenException: Transient — circuit is open
                                         (SendGrid unhealthy); worth retrying
            Exception: Transient — timeouts, connection errors, 5xx; these
                       count toward the breaker and are worth retrying
        """
        try:
            await self._circuit_breaker.execute(
                self._do_send_email,
                to_email=to_email,
                subject=subject,
                content=content,
            )
            self.logger.info(
                f"Email sent to {to_email} (CC: {self.admin_email})"
            )

        except EmailDeliveryException as e:
            self.logger.error(f"Email to {to_email} permanently rejected", exception=e)
            raise

        except CircuitBreakerOpenException as e:
            self.logger.warning(
                f"Circuit breaker OPEN for SendGrid. Email to {to_email} not sent. "
                f"Retry in {e.time_remaining:.1f}s. Consider queueing for later."
            )
            raise

        except Exception as e:
            # Service-health failures (timeout, connection error, 5xx):
            # counted by the breaker, propagated for retry
            self.logger.error(f"Failed to send email to {to_email}", exception=e)
            raise

    async def is_healthy(self) -> bool:
        """
        Check if the email service is healthy.

        Returns False if circuit breaker is open (SendGrid is down).
        """
        return not self._circuit_breaker.is_open
