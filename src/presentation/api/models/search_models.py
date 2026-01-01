"""Search API models."""
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """A single search result."""
    id: str
    score: float
    data: dict[str, Any]


class SearchResponse(BaseModel):
    """Search response with pagination."""
    total: int
    hits: List[SearchResult]
    query: str
    index: str


class BookSearchResult(BaseModel):
    """Book search result."""
    id: str
    score: float = Field(description="Relevance score")
    title: str
    author: str
    is_borrowed: bool = False


class PatronSearchResult(BaseModel):
    """Patron search result."""
    id: str
    score: float = Field(description="Relevance score")
    first_name: str
    last_name: str
    full_name: str
    email: str
    membership_tier: Optional[str] = None
    is_suspended: bool = False


class LoanSearchResult(BaseModel):
    """Loan search result."""
    id: str
    score: float = Field(description="Relevance score")
    patron_id: str
    patron_email: str
    catalog_book_id: str
    book_title: str
    status: str
    is_overdue: bool = False


class BookSearchResponse(BaseModel):
    """Book search response."""
    total: int
    hits: List[BookSearchResult]


class PatronSearchResponse(BaseModel):
    """Patron search response."""
    total: int
    hits: List[PatronSearchResult]


class LoanSearchResponse(BaseModel):
    """Loan search response."""
    total: int
    hits: List[LoanSearchResult]
