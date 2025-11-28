"""
SendGrid Email Service with Circuit Breaker protection.

The circuit breaker prevents cascading failures when SendGrid is unavailable,
allowing the system to queue emails for later delivery or use fallback
notification mechanisms.
"""
from src.infrastructure.external.sendgrid_client import SendGridClient
from src.domain.shared_kernel import EmailService, Logger
from src.infrastructure.adapters.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenException,
)


class SendGridEmailService(EmailService):
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
        logger: Logger,
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
        self.client.send(
            from_email=self.from_email,
            to_email=to_email,
            subject=subject,
            content_str=content,
            cc_email=self.admin_email
        )

    async def send_email(self, to_email: str, subject: str, content: str) -> None:
        """
        Send an email via SendGrid.

        Protected by circuit breaker - will fail fast if SendGrid is down.
        Failed emails should be queued for retry.

        Args:
            to_email: Recipient email address
            subject: Email subject
            content: Email body (HTML supported)

        Raises:
            CircuitBreakerOpenException: If circuit is open (SendGrid unhealthy)
            EmailServiceException: If send fails
        """
        try:
            # Execute with circuit breaker protection
            # Note: SendGrid client is synchronous, but circuit breaker handles it
            await self._circuit_breaker.execute(
                self._do_send_email,
                to_email=to_email,
                subject=subject,
                content=content,
            )
            self.logger.info(
                f"Email sent to {to_email} (CC: {self.admin_email})"
            )

        except CircuitBreakerOpenException as e:
            # Circuit is open - fail fast
            self.logger.warning(
                f"Circuit breaker OPEN for SendGrid. Email to {to_email} not sent. "
                f"Retry in {e.time_remaining:.1f}s. Consider queueing for later."
            )
            raise

        except Exception as e:
            from src.infrastructure.exceptions.infrastructure_exceptions import EmailServiceException
            self.logger.error(f"Failed to send email to {to_email}", exception=e)
            raise EmailServiceException(
                f"Failed to send email to {to_email}: {str(e)}",
                original_exception=e
            )

    async def is_healthy(self) -> bool:
        """
        Check if the email service is healthy.

        Returns False if circuit breaker is open (SendGrid is down).
        """
        return not self._circuit_breaker.is_open
