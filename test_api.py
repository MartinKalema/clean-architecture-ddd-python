import pytest
from httpx import AsyncClient, ASGITransport
from src.presentation.api.main import app

@pytest.mark.asyncio
async def test_add_and_list_books():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Add a book
        response = await ac.post(
            "/books",
            json={"title": "Clean Code", "author": "Robert C. Martin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Clean Code"
        assert "id" in data
        book_id = data["id"]
        print(f"Added book: {data}")

        # 2. List books
        response = await ac.get("/books")
        assert response.status_code == 200
        books = response.json()
        assert len(books) > 0
        print(f"Books: {books}")

        # 3. Borrow book
        response = await ac.post(f"/books/{book_id}/borrow")
        assert response.status_code == 200
        data = response.json()
        assert data["is_borrowed"] is True
        print(f"Borrowed book: {data}")

        # 4. Test Validation
        response = await ac.post(
            "/books",
            json={"title": "", "author": "No Title"}
        )
        assert response.status_code == 400
        print(f"Validation failed as expected: {response.json()}")
