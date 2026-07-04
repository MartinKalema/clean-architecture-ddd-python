"""
Send Loan Confirmation Email - Application event handler.

Reacts to LoanCreated by emailing the patron a confirmation. Runs in the
event worker, in a separate transaction from the one that created the loan:
if SendGrid is down the loan still exists, and the failure is logged for
retry rather than failing the borrow request.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.shared_kernel import EmailDeliveryException

if TYPE_CHECKING:
    from src.domain.lending import LoanCreated
    from src.domain.shared_kernel import IEmailService, ILogger


class SendLoanConfirmationEmailHandler:
    """Sends a confirmation email when a loan is created."""

    def __init__(self, email_service: IEmailService, logger: ILogger):
        self.email_service = email_service
        self.logger = logger

    async def handle(self, event: LoanCreated) -> None:
        subject = f"Loan confirmation: {event.book_title}"
        content = (
            f"<p>You borrowed <strong>{event.book_title}</strong> "
            f"on {event.borrowed_at:%Y-%m-%d}.</p>"
            f"<p>Please return it by <strong>{event.due_date:%Y-%m-%d}</strong>.</p>"
        )

        try:
            await self.email_service.send_email(
                to_email=event.patron_email,
                subject=subject,
                content=content,
            )
        except EmailDeliveryException as e:
            # Permanent rejection: retrying the message will not change the
            # outcome, and raising would head-of-line block the pipeline
            # behind pointless retries. Escalate and move on. Transient
            # failures (timeout, open circuit) propagate and are retried.
            self.logger.error(
                f"Confirmation email for loan {event.loan_id} to "
                f"{event.patron_email} permanently rejected; "
                f"manual follow-up required",
                exception=e,
            )
            return

        self.logger.info(
            f"Loan confirmation email sent for loan {event.loan_id} "
            f"to {event.patron_email}"
        )
