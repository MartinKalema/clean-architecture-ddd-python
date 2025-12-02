"""
Event Handlers - Async handlers for domain events.

These handlers react to domain events published via the message broker.
They are invoked asynchronously by background workers, not by HTTP requests.

Event Handlers vs Command/Query Handlers:
- Command Handlers: Synchronous, user-initiated, mutate state
- Query Handlers: Synchronous, user-initiated, read state
- Event Handlers: Asynchronous, system-initiated, react to state changes
"""
from src.application.event_handlers.book_handlers import BookHandlers

__all__ = ["BookHandlers"]
