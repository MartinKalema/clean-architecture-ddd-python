import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_add_and_list_books(client: AsyncClient):
    # 1. Add a book
    response = await client.post(
        "/books",
        json={"title": "E2E API Book", "author": "E2E Tester"}
    )
    assert response.status_code == 200
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
    # 1. Add
    response = await client.post(
        "/books",
        json={"title": "Borrow API Book", "author": "E2E Tester"}
    )
    book_id = response.json()["id"]

    # 2. Borrow
    response = await client.post(
        f"/books/{book_id}/borrow",
        json={"borrower_email": "borrower@example.com"}
    )
    assert response.status_code == 200
    assert response.json()["is_borrowed"] is True

    # 3. Borrow again (fail)
    response = await client.post(
        f"/books/{book_id}/borrow",
        json={"borrower_email": "another@example.com"}
    )
    assert response.status_code == 409, f"Expected 409, got {response.status_code}. Body: {response.text}"
