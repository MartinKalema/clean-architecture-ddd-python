from src.domain.events.book_events import BookBorrowed
from src.domain.interfaces.email_service import EmailService

class BookHandlers:
    def __init__(self, email_service: EmailService):
        self.email_service = email_service

    async def handle_book_borrowed(self, event: BookBorrowed):
        print(f"[Handler] Handling BookBorrowed event for book {event.book_id}")
        
        date_format = "%Y-%m-%d"
        borrowed_date = event.borrowed_at.strftime(date_format)
        return_date = event.return_due_date.strftime(date_format)
        
        content = f"""
        <strong>Book Title:</strong> {event.title}<br>
        <strong>Borrowed On:</strong> {borrowed_date}<br>
        <strong>Return Due:</strong> {return_date}<br>
        <br>
        Please return the book by the due date to avoid penalties.
        """
        
        await self.email_service.send_email(
            to_email=event.borrower_email,
            subject=f"Book Borrowed: {event.title}",
            content=content
        )
