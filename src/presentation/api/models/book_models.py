from pydantic import BaseModel, ConfigDict, field_validator


class BookCreate(BaseModel):
    title: str
    author: str


class BorrowRequest(BaseModel):
    borrower_email: str

    @field_validator('borrower_email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not v or '@' not in v:
            raise ValueError('Invalid email address')
        return v


class BookResponse(BaseModel):
    id: str
    title: str
    author: str
    is_borrowed: bool

    model_config = ConfigDict(from_attributes=True)
