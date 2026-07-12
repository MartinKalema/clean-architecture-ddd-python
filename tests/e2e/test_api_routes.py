import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_add_and_list_books(client: AsyncClient):
    # 1. Add a book
    response = await client.post(
        "/books",
        json={"title": "E2E API Book", "author": "E2E Tester"},
        headers={"Idempotency-Key": "e2e-add-book-001"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "E2E API Book"
    book_id = data["id"]
    
    # 2. List books
    response = await client.get("/books")
    assert response.status_code == 200
    books = response.json()
    assert len(books) >= 1
    assert any(b["id"] == book_id for b in books)

@pytest.mark.asyncio
async def test_api_borrow_book(client: AsyncClient):
    # 1. Register the authoritative patron and add the catalog book.
    patron_response = await client.post(
        "/patrons",
        json={
            "first_name": "Borrow",
            "last_name": "Tester",
            "email": "borrower@example.com",
            "membership_tier": "regular",
        },
        headers={"Idempotency-Key": "e2e-register-patron-001"},
    )
    assert patron_response.status_code == 201

    response = await client.post(
        "/books",
        json={"title": "Borrow API Book", "author": "E2E Tester"},
        headers={"Idempotency-Key": "e2e-add-book-002"},
    )
    book_id = response.json()["id"]

    # 2. Borrow
    response = await client.post(
        f"/books/{book_id}/borrow",
        json={"borrower_email": "borrower@example.com"},
        headers={"Idempotency-Key": "e2e-borrow-book-001"},
    )
    assert response.status_code == 202
    assert response.json()["is_borrowed"] is False
    assert response.json()["status"] == "reserved"
    assert response.json()["reservation_id"]
    assert response.json()["reservation_generation"] == 1
    assert response.json()["operation_id"] == response.json()["reservation_id"]
    assert response.headers["location"].endswith(response.json()["operation_id"])

    # 3. Borrow again (fail)
    response = await client.post(
        f"/books/{book_id}/borrow",
        json={"borrower_email": "borrower@example.com"},
        headers={"Idempotency-Key": "e2e-borrow-book-002"},
    )
    assert response.status_code == 409, f"Expected 409, got {response.status_code}. Body: {response.text}"


@pytest.mark.asyncio
async def test_unsafe_direct_loan_and_catalog_return_commands_are_not_public(
    client: AsyncClient,
):
    schema = (await client.get("/openapi.json")).json()

    assert "post" not in schema.get("paths", {}).get("/loans", {})
    assert "post" not in schema.get("paths", {}).get("/books/{book_id}/return", {})
    assert "post" in schema["paths"]["/loans/{loan_id}/return"]
