from src.domain.catalog import BookBorrowed
from src.domain.shared_kernel import EmailService, TemplateRenderer, Logger, EmailTemplate


class BookHandlers:
    def __init__(self, email_service: EmailService, template_renderer: TemplateRenderer, logger: Logger):
        self.email_service = email_service
        self.template_renderer = template_renderer
        self.logger = logger

    async def handle_book_borrowed(self, event: BookBorrowed):
        try:
            self.logger.info(f"Handling BookBorrowed event for book: {event.title}")

            # Render email content using template
            email_content = self.template_renderer.render(
                EmailTemplate.BOOK_BORROWED,
                context={
                    "title": event.title,
                    "borrowed_at": event.borrowed_at.strftime("%Y-%m-%d"),
                    "return_due_date": event.return_due_date.strftime("%Y-%m-%d")
                }
            )

            await self.email_service.send_email(
                to_email=event.borrower_email,
                subject=f"Book Borrowed: {event.title}",
                content=email_content
            )
            self.logger.info(f"Sent borrowed notification email to {event.borrower_email}")
        except Exception as e:
            self.logger.error(f"Error handling BookBorrowed event", exception=e)
            raise
