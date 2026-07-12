from datetime import datetime, timezone

import pytest

from src.application.query_handlers.pagination import (
    InvalidPaginationError,
    cursor_scope,
    decode_cursor,
    decode_cursor_with_backend,
    encode_cursor,
    validate_pagination,
)
from src.application.query_handlers.read_models import BookReadModel, LoanReadModel


def test_cursor_round_trip_is_scoped_to_query_filters():
    scope = cursor_scope("books", {"only_available": True})
    cursor = encode_cursor(scope, ["A title", "book-1"])

    assert decode_cursor(
        cursor, expected_scope=scope, expected_values=2
    ) == ["A title", "book-1"]

    with pytest.raises(InvalidPaginationError):
        decode_cursor(
            cursor,
            expected_scope=cursor_scope("books", {"only_available": False}),
            expected_values=2,
        )


def test_cursor_carries_backend_affinity_for_stable_fallback_ordering():
    scope = cursor_scope("books", {})
    cursor = encode_cursor(
        scope,
        ["ångström", "book-1"],
        backend="elasticsearch",
    )

    values, backend = decode_cursor_with_backend(
        cursor, expected_scope=scope, expected_values=2
    )

    assert values == ["ångström", "book-1"]
    assert backend == "elasticsearch"


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (1001, 0), (1000, 9001), (1, -1)],
)
def test_offset_pagination_is_bounded(limit: int, offset: int):
    with pytest.raises(InvalidPaginationError):
        validate_pagination(limit=limit, offset=offset)


def test_cursor_and_offset_cannot_be_combined():
    with pytest.raises(InvalidPaginationError):
        validate_pagination(limit=20, offset=1, cursor="cursor")


def test_book_hydration_coerces_dates_and_reserved_is_not_borrowed():
    model = BookReadModel.from_mapping(
        {
            "id": "book-1",
            "title": "Title",
            "author": "Author",
            "status": "reserved",
            "is_borrowed": True,  # stale projection data is ignored
            "borrowed_at": "2026-07-11T10:00:00Z",
        }
    )

    assert model.is_borrowed is False
    assert model.borrowed_at == datetime(2026, 7, 11, 10, tzinfo=timezone.utc)


def test_loan_hydration_never_leaks_iso_strings():
    model = LoanReadModel.from_mapping(
        {
            "id": "loan-1",
            "patron_id": "patron-1",
            "patron_email": "patron@example.test",
            "catalog_book_id": "book-1",
            "book_title": "Title",
            "borrowed_at": "2026-07-01T10:00:00+00:00",
            "due_date": "2026-07-10T10:00:00+00:00",
            "returned_at": None,
            "status": "active",
        }
    )

    assert isinstance(model.borrowed_at, datetime)
    assert isinstance(model.due_date, datetime)
