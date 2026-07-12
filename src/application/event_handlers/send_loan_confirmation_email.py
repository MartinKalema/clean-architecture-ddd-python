"""
Send Loan Confirmation Email - Application event handler.

Reacts to CatalogBookBorrowed by emailing the patron a confirmation. This
event is emitted only after Catalog accepted the exact Lending loan, so a
tentative loan that is later compensated never produces a confirmation.
Runs in the event worker, in a separate transaction from the one that created the loan:
if SendGrid is down the loan still exists, and the failure is logged for
retry rather than failing the borrow request.
"""
from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from src.application.ports import EmailDeliveryException

if TYPE_CHECKING:
    from src.domain.catalog import CatalogBookBorrowed
    from src.application.ports import IEmailService, ILogger


class SendLoanConfirmationEmailHandler:
    """Sends a confirmation only after Catalog finalizes a borrow."""

    inbox_consumer_name = "notification.send-loan-confirmation.v1"

    def __init__(self, email_service: IEmailService, logger: ILogger):
        self.email_service = email_service
        self.logger = logger

    async def handle(self, event: CatalogBookBorrowed) -> None:
        # Catalog text originated at a public command boundary. Keep it data
        # in both the message header and its HTML body.
        subject_title = event.title.replace("\r", " ").replace("\n", " ")
        escaped_title = escape(event.title, quote=True)
        subject = f"Loan confirmation: {subject_title}"
        content = (
            f"<p>You borrowed <strong>{escaped_title}</strong> "
            f"on {event.borrowed_at:%Y-%m-%d}.</p>"
            f"<p>Please return it by "
            f"<strong>{event.return_due_date:%Y-%m-%d}</strong>.</p>"
        )

        try:
            await self.email_service.send_email(
                to_email=event.borrower_email,
                subject=subject,
                content=content,
                # SendGrid does not offer an idempotency key. This stable ID is
                # attached as provider metadata so the unavoidable accepted-
                # send/inbox-commit crash window is traceable and suppressible
                # by a webhook/delivery system that supports deduplication.
                delivery_id=event.event_id,
            )
        except EmailDeliveryException as e:
            # A retry is unlikely to fix the payload, but acknowledging it
            # would erase the notification obligation. Propagation lets the
            # worker place the original event on its replayable DLQ after
            # bounded retries, where operators can repair/replay it.
            self.logger.error(
                f"Confirmation email for loan {event.loan_id} to "
                f"{event.borrower_email} permanently rejected; "
                f"manual follow-up required",
                exception=e,
            )
            raise

        self.logger.info(
            f"Loan confirmation email sent for loan {event.loan_id} "
            f"to {event.borrower_email}"
        )
