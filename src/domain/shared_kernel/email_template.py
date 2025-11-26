"""
Email templates used across bounded contexts.
"""
from enum import Enum


class EmailTemplate(Enum):
    BOOK_BORROWED = "book_borrowed"
    BOOK_RETURNED = "book_returned"
    BOOK_OVERDUE = "book_overdue"
