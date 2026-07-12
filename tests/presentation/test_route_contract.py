"""Public command surface for the authoritative borrow/return workflows."""
from src.presentation.api.routes.book_routes import router as book_router
from src.presentation.api.routes.loan_routes import router as loan_router


def _operations(router) -> set[tuple[str, str]]:
    return {
        (route.path, method)
        for route in router.routes
        for method in (route.methods or set())
    }


def test_only_authoritative_borrow_and_return_commands_are_public():
    operations = _operations(book_router) | _operations(loan_router)

    assert ("/books/{book_id}/borrow", "POST") in operations
    assert ("/loans/{loan_id}/return", "POST") in operations
    assert ("/loans", "POST") not in operations
    assert ("/books/{book_id}/return", "POST") not in operations
