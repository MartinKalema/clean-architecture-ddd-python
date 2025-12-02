"""
Realistic User Scenarios for Load Testing.

Models different user personas based on actual usage patterns:
- Browser: Casual user just looking around
- Borrower: Active library patron
- Librarian: Admin user managing books
"""
import random
import uuid

from locust import between, tag, task

from .base import BaseBookUser


class BrowserUser(BaseBookUser):
    """
    Casual browser - mostly reads, rarely interacts.

    Represents 60% of typical library traffic.
    """

    weight = 60  # 60% of users
    wait_time = between(2, 5)  # Slower, casual browsing

    @task(10)
    @tag("read", "browse")
    def list_books(self):
        """Browse the book catalog."""
        self.client.get("/books")

    @task(5)
    @tag("read", "browse")
    def view_random_book(self):
        """View a specific book's details."""
        # First get the list
        response = self.client.get("/books", name="/books (for browse)")
        if response.status_code == 200:
            books = response.json()
            if books:
                book = random.choice(books)
                self.get_book(book["id"])

    @task(1)
    @tag("read", "health")
    def check_health(self):
        """Occasional health check."""
        self.client.get("/health")


class BorrowerUser(BaseBookUser):
    """
    Active patron - browses and borrows books.

    Represents 30% of typical library traffic.
    """

    weight = 30  # 30% of users
    wait_time = between(1, 3)  # More engaged

    def on_start(self):
        """Setup: ensure we have a book to work with."""
        # Create a book for this user's session
        self.create_book(
            title=f"BorrowerBook_{uuid.uuid4().hex[:6]}",
            author="Test Author"
        )

    @task(5)
    @tag("read", "browse")
    def list_books(self):
        """Browse available books."""
        self.client.get("/books")

    @task(3)
    @tag("read")
    def view_book_details(self):
        """Check book details before borrowing."""
        if self._my_books:
            self.get_book(random.choice(self._my_books))

    @task(2)
    @tag("write", "borrow")
    def borrow_available_book(self):
        """Borrow a book from the catalog."""
        response = self.client.get("/books", name="/books (for borrow)")
        if response.status_code == 200:
            books = response.json()
            # Find an available book
            available = [b for b in books if not b.get("is_borrowed", False)]
            if available:
                book = random.choice(available)
                self.borrow_book(
                    book["id"],
                    f"borrower_{self._test_run_id}@loadtest.com"
                )

    @task(1)
    @tag("write", "return")
    def return_borrowed_book(self):
        """Return a previously borrowed book."""
        if self._borrowed_books:
            book_id = random.choice(self._borrowed_books)
            self.return_book(book_id)


class LibrarianUser(BaseBookUser):
    """
    Librarian/Admin - manages the book catalog.

    Represents 10% of typical library traffic.
    """

    weight = 10  # 10% of users
    wait_time = between(0.5, 2)  # Faster, task-oriented

    @task(3)
    @tag("read", "admin")
    def list_all_books(self):
        """Review catalog."""
        self.client.get("/books")

    @task(2)
    @tag("write", "admin")
    def add_new_book(self):
        """Add a new book to the catalog."""
        self.create_book(
            title=f"NewBook_{uuid.uuid4().hex[:6]}",
            author=f"Author_{random.randint(1, 100)}"
        )

    @task(2)
    @tag("read", "admin", "health")
    def check_system_health(self):
        """Monitor system health."""
        self.client.get("/health")
        self.client.get("/health/live")
        self.client.get("/health/ready")

    @task(1)
    @tag("read", "admin", "health")
    def check_circuit_breakers(self):
        """Monitor circuit breaker status."""
        self.client.get("/health/circuits")


class StressTestUser(BaseBookUser):
    """
    Aggressive user for stress testing - rapid requests.

    Used specifically for stress/spike tests.
    """

    weight = 0  # Not used in normal tests - enable explicitly
    wait_time = between(0.1, 0.5)  # Very fast

    @task(5)
    def rapid_list(self):
        """Rapid catalog queries."""
        self.client.get("/books")

    @task(3)
    def rapid_create_and_borrow(self):
        """Rapid create and borrow cycle."""
        book_id = self.create_book(
            title=f"Stress_{uuid.uuid4().hex[:8]}",
            author="StressBot"
        )
        if book_id:
            self.borrow_book(book_id, "stress@loadtest.com")

    @task(2)
    def health_spam(self):
        """Spam health endpoints."""
        self.client.get("/health")
        self.client.get("/health/circuits")
