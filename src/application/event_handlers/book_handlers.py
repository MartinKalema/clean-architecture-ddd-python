"""
Event handlers for book-related domain events.

These handlers are invoked by the event consumer when events
are received from the message broker.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Union

from src.domain.catalog import CatalogBookBorrowed
from src.domain.shared_kernel import EmailTemplate

if TYPE_CHECKING:
    from src.domain.shared_kernel import EmailService, Logger, TemplateRenderer


class BookHandlers:
    """Handles book-related domain events."""

    def __init__(self, email_service: EmailService, template_renderer: TemplateRenderer, logger: Logger):
        self.email_service = email_service
        self.template_renderer = template_renderer
        self.logger = logger

    async def handle_book_borrowed(self, event: Union[CatalogBookBorrowed, dict]):
        """
        Handle CatalogBookBorrowed event - send notification email to borrower.

        Args:
            event: Either a CatalogBookBorrowed domain event or a dict payload from the consumer
        """
        try:
            if isinstance(event, dict):
                title = event.get("title")
                borrower_email = event.get("borrower_email")
                borrowed_at = event.get("borrowed_at")
                return_due_date = event.get("return_due_date")

                if isinstance(borrowed_at, str):
                    borrowed_at = datetime.fromisoformat(borrowed_at.replace("Z", "+00:00"))
                if isinstance(return_due_date, str):
                    return_due_date = datetime.fromisoformat(return_due_date.replace("Z", "+00:00"))
            else:
                title = event.title
                borrower_email = event.borrower_email
                borrowed_at = event.borrowed_at
                return_due_date = event.return_due_date

            self.logger.info(f"Handling CatalogBookBorrowed event for book: {title}")

            email_content = self.template_renderer.render(
                EmailTemplate.BOOK_BORROWED,
                context={
                    "title": title,
                    "borrowed_at": borrowed_at.strftime("%Y-%m-%d") if borrowed_at else "N/A",
                    "return_due_date": return_due_date.strftime("%Y-%m-%d") if return_due_date else "N/A"
                }
            )

            if borrower_email:
                await self.email_service.send_email(
                    to_email=borrower_email,
                    subject=f"Book Borrowed: {title}",
                    content=email_content
                )
                self.logger.info(f"Sent borrowed notification email to {borrower_email}")
            else:
                self.logger.warning("No borrower email provided, skipping notification")

        except Exception as e:
            self.logger.error("Error handling CatalogBookBorrowed event", exception=e)
            raise

    async def handle_book_returned(self, event: Union[dict, object]):
        """
        Handle CatalogBookReturned event.

        Args:
            event: Either a CatalogBookReturned domain event or a dict payload
        """
        try:
            if isinstance(event, dict):
                book_id = event.get("book_id")
            else:
                book_id = getattr(event, "book_id", None)

            self.logger.info(f"Handling CatalogBookReturned event for book: {book_id}")

        except Exception as e:
            self.logger.error("Error handling CatalogBookReturned event", exception=e)
            raise
