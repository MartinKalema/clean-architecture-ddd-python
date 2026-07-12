"""HTTP representation of application query pages."""

from fastapi import Response


def set_page_headers(
    response: Response,
    *,
    next_cursor: str | None,
    total: int | None,
) -> None:
    """Expose continuation metadata for list responses."""
    if next_cursor is not None:
        response.headers["X-Next-Cursor"] = next_cursor
    if total is not None:
        response.headers["X-Total-Count"] = str(total)
