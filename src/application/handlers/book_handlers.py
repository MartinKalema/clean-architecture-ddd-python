from src.domain.events.book_events import BookBorrowed
from src.domain.interfaces.email_service import EmailService
from src.domain.interfaces.template_renderer import TemplateRenderer
from src.domain.value_objects.email_template import EmailTemplate

class BookHandlers:
    def __init__(self, email_service: EmailService, template_renderer: TemplateRenderer):
        self.email_service = email_service
        self.template_renderer = template_renderer

    async def handle_book_borrowed(self, event: BookBorrowed):
        print(f"[Handler] Handling BookBorrowed event for book {event.book_id}")
        
        date_format = "%Y-%m-%d"
        context = {
            "title": event.title,
            "borrowed_date": event.borrowed_at.strftime(date_format),
            "return_date": event.return_due_date.strftime(date_format)
        }
        
        content = self.template_renderer.render(EmailTemplate.BOOK_BORROWED, context)
        
        await self.email_service.send_email(
            to_email=event.borrower_email,
            subject=f"Book Borrowed: {event.title}",
            content=content
        )
