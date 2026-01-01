"""
Search API Routes

Full-text search endpoints powered by Elasticsearch.
These routes query the read model (Elasticsearch) which is
populated via CDC from the write model (PostgreSQL).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query

from src.container import Container
from src.presentation.api.models.search_models import (
    BookSearchResponse,
    BookSearchResult,
    LoanSearchResponse,
    LoanSearchResult,
    PatronSearchResponse,
    PatronSearchResult,
)

if TYPE_CHECKING:
    from src.infrastructure.external.elasticsearch_client import ElasticsearchClient

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/books", response_model=BookSearchResponse)
@inject
async def search_books(
    q: str = Query(..., min_length=1, description="Search query"),
    size: int = Query(10, ge=1, le=100, description="Number of results"),
    from_: int = Query(0, ge=0, alias="from", description="Offset for pagination"),
    available_only: bool = Query(False, description="Only show available books"),
    es_client: ElasticsearchClient = Depends(Provide[Container.elasticsearch_client]),
):
    """
    Search books by title or author.

    Uses Elasticsearch full-text search with fuzzy matching.
    Data is synced from PostgreSQL via CDC (Debezium).
    """
    try:
        # Build query
        must = [
            {
                "multi_match": {
                    "query": q,
                    "fields": ["title^2", "title.autocomplete", "author", "author.autocomplete"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        ]

        if available_only:
            must.append({"term": {"is_borrowed": False}})

        query = {"bool": {"must": must}}

        result = es_client.search(index="books", query=query, size=size, from_=from_)

        return BookSearchResponse(
            total=result["total"],
            hits=[
                BookSearchResult(
                    id=hit["id"],
                    score=hit["score"],
                    title=hit.get("title", ""),
                    author=hit.get("author", ""),
                    is_borrowed=hit.get("is_borrowed", False),
                )
                for hit in result["hits"]
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Search service unavailable: {str(e)}")


@router.get("/patrons", response_model=PatronSearchResponse)
@inject
async def search_patrons(
    q: str = Query(..., min_length=1, description="Search query"),
    size: int = Query(10, ge=1, le=100, description="Number of results"),
    from_: int = Query(0, ge=0, alias="from", description="Offset for pagination"),
    tier: Optional[str] = Query(None, description="Filter by membership tier"),
    es_client: ElasticsearchClient = Depends(Provide[Container.elasticsearch_client]),
):
    """
    Search patrons by name or email.

    Uses Elasticsearch full-text search with fuzzy matching.
    """
    try:
        must = [
            {
                "multi_match": {
                    "query": q,
                    "fields": [
                        "first_name^2",
                        "last_name^2",
                        "full_name^3",
                        "full_name.autocomplete",
                        "email",
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        ]

        if tier:
            must.append({"term": {"membership_tier": tier}})

        query = {"bool": {"must": must}}

        result = es_client.search(index="patrons", query=query, size=size, from_=from_)

        return PatronSearchResponse(
            total=result["total"],
            hits=[
                PatronSearchResult(
                    id=hit["id"],
                    score=hit["score"],
                    first_name=hit.get("first_name", ""),
                    last_name=hit.get("last_name", ""),
                    full_name=hit.get("full_name", ""),
                    email=hit.get("email", ""),
                    membership_tier=hit.get("membership_tier"),
                    is_suspended=hit.get("is_suspended", False),
                )
                for hit in result["hits"]
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Search service unavailable: {str(e)}")


@router.get("/loans", response_model=LoanSearchResponse)
@inject
async def search_loans(
    patron_id: Optional[str] = Query(None, description="Filter by patron ID"),
    book_id: Optional[str] = Query(None, description="Filter by book ID"),
    status: Optional[str] = Query(None, description="Filter by status (active, returned)"),
    overdue_only: bool = Query(False, description="Only show overdue loans"),
    size: int = Query(10, ge=1, le=100, description="Number of results"),
    from_: int = Query(0, ge=0, alias="from", description="Offset for pagination"),
    es_client: ElasticsearchClient = Depends(Provide[Container.elasticsearch_client]),
):
    """
    Search loans with filtering.

    At least one filter (patron_id, book_id, status, or overdue_only) is required.
    """
    try:
        filters = []

        if patron_id:
            filters.append({"term": {"patron_id": patron_id}})
        if book_id:
            filters.append({"term": {"catalog_book_id": book_id}})
        if status:
            filters.append({"term": {"status": status}})
        if overdue_only:
            filters.append({"term": {"is_overdue": True}})

        if not filters:
            raise HTTPException(
                status_code=400,
                detail="At least one filter (patron_id, book_id, status, or overdue_only) is required",
            )

        query = {"bool": {"filter": filters}}

        result = es_client.search(index="loans", query=query, size=size, from_=from_)

        return LoanSearchResponse(
            total=result["total"],
            hits=[
                LoanSearchResult(
                    id=hit["id"],
                    score=hit["score"],
                    patron_id=hit.get("patron_id", ""),
                    patron_email=hit.get("patron_email", ""),
                    catalog_book_id=hit.get("catalog_book_id", ""),
                    book_title=hit.get("book_title", ""),
                    status=hit.get("status", ""),
                    is_overdue=hit.get("is_overdue", False),
                )
                for hit in result["hits"]
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Search service unavailable: {str(e)}")
