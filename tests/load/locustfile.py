from locust import HttpUser, task, between
import uuid

class BookUser(HttpUser):
    wait_time = between(1, 3)
    
    # Store created book IDs to borrow them later
    book_ids = []

    @task(3)
    def list_books(self):
        self.client.get("/books")

    @task(1)
    def add_book(self):
        # Create a unique book to avoid conflicts (though DB allows duplicates currently)
        unique_id = str(uuid.uuid4())[:8]
        response = self.client.post("/books", json={
            "title": f"Load Test Book {unique_id}",
            "author": "Locust User"
        })
        if response.status_code == 200:
            book_id = response.json()["id"]
            self.book_ids.append(book_id)

    @task(2)
    def borrow_book(self):
        if not self.book_ids:
            return

        # Try to borrow a recently added book
        book_id = self.book_ids.pop()
        with self.client.post(
            f"/books/{book_id}/borrow",
            json={"borrower_email": "loadtest@example.com"},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 409:
                # It's expected that some books might be already borrowed in a concurrent test
                response.success()
            elif response.status_code == 404:
                 # Also possible if cleanup happened or logic error
                response.failure(f"Book {book_id} not found")
            else:
                response.failure(f"Failed to borrow: {response.status_code} {response.text}")
