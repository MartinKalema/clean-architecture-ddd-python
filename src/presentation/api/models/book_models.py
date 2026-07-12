from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    author: str = Field(min_length=1, max_length=200)

    @field_validator("title", "author")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("value cannot be blank")
        return value


class BorrowRequest(BaseModel):
    borrower_email: str

    @field_validator('borrower_email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not v or '@' not in v or len(v) > 254:
            raise ValueError('Invalid email address')
        return v


class BookResponse(BaseModel):
    id: str
    title: str
    author: str
    is_borrowed: bool
    # available | reserved | borrowed — reserved means a borrow is being
    # confirmed and the book is temporarily withheld
    status: str = "available"

    model_config = ConfigDict(from_attributes=True)


class BorrowBookResponse(BookResponse):
    """Trackable acknowledgement of the asynchronous borrow workflow."""

    reservation_id: str
    reservation_generation: int
    operation_id: str
    return_due_date: Optional[datetime] = None


class BorrowOperationResponse(BaseModel):
    operation_id: str
    book_id: str
    patron_id: str
    reservation_generation: int
    status: str
    loan_id: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
