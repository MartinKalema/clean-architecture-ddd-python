"""
Base classes for load testing.

Provides common functionality for all user types:
- Proper state management (per-user, not shared)
- Test data isolation
- Cleanup support
- Custom metrics
"""
import uuid
import time
from typing import Optional
from locust import HttpUser, events
from locust.runners import MasterRunner, WorkerRunner

from .config import TEST_DATA_PREFIX, DEFAULT_SLA


class BaseBookUser(HttpUser):
    """
    Base user class with proper state management.

    Each user instance has its own state - no shared class variables.
    """

    abstract = True  # Don't instantiate directly

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Per-user state - NOT shared across users
        self._my_books: list[str] = []
        self._borrowed_books: list[str] = []
        self._test_run_id = str(uuid.uuid4())[:8]

    @property
    def test_prefix(self) -> str:
        """Unique prefix for this user's test data."""
        return f"{TEST_DATA_PREFIX}_{self._test_run_id}"

    def create_book(self, title: str, author: str) -> Optional[str]:
        """
        Create a book and track it for cleanup.

        Returns book ID if successful, None otherwise.
        """
        response = self.client.post("/books", json={
            "title": f"{self.test_prefix}_{title}",
            "author": author,
        })

        if response.status_code == 200:
            book_id = response.json()["id"]
            self._my_books.append(book_id)
            return book_id
        return None

    def borrow_book(self, book_id: str, email: str) -> bool:
        """
        Borrow a book with proper response handling.

        Returns True if successful or already borrowed (expected in concurrent tests).
        """
        with self.client.post(
            f"/books/{book_id}/borrow",
            json={"borrower_email": email},
            catch_response=True,
            name="/books/{id}/borrow",  # Group in stats
        ) as response:
            if response.status_code == 200:
                self._borrowed_books.append(book_id)
                response.success()
                return True
            elif response.status_code == 409:
                # Already borrowed - expected in concurrent tests
                response.success()
                return False
            elif response.status_code == 404:
                response.failure("Book not found")
                return False
            else:
                response.failure(f"Unexpected: {response.status_code}")
                return False

    def return_book(self, book_id: str) -> bool:
        """Return a borrowed book."""
        with self.client.post(
            f"/books/{book_id}/return",
            catch_response=True,
            name="/books/{id}/return",
        ) as response:
            if response.status_code == 200:
                if book_id in self._borrowed_books:
                    self._borrowed_books.remove(book_id)
                response.success()
                return True
            elif response.status_code == 400:
                # Not borrowed - expected race condition
                response.success()
                return False
            else:
                response.failure(f"Unexpected: {response.status_code}")
                return False

    def get_book(self, book_id: str) -> bool:
        """Get book details."""
        with self.client.get(
            f"/books/{book_id}",
            catch_response=True,
            name="/books/{id}",
        ) as response:
            if response.status_code == 200:
                response.success()
                return True
            elif response.status_code == 404:
                response.failure("Book not found")
                return False
            else:
                response.failure(f"Unexpected: {response.status_code}")
                return False

    def on_stop(self):
        """Cleanup when user stops - return borrowed books."""
        for book_id in list(self._borrowed_books):
            self.return_book(book_id)


# Custom metrics tracking
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, **kwargs):
    """Track custom metrics for SLA validation."""
    # This runs for every request - can be used for custom dashboards
    pass


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Validate SLAs at test end."""
    if isinstance(environment.runner, (MasterRunner, WorkerRunner)):
        return  # Only run on local/standalone

    stats = environment.stats.total

    # Check error rate
    if stats.num_requests > 0:
        error_rate = (stats.num_failures / stats.num_requests) * 100
        if error_rate > DEFAULT_SLA.max_error_rate:
            print(f"\n[SLA VIOLATION] Error rate {error_rate:.2f}% > {DEFAULT_SLA.max_error_rate}%")

    # Check P95 latency
    if stats.num_requests > 0:
        p95 = stats.get_response_time_percentile(0.95) or 0
        if p95 > DEFAULT_SLA.p95_latency_ms:
            print(f"\n[SLA VIOLATION] P95 latency {p95:.0f}ms > {DEFAULT_SLA.p95_latency_ms}ms")

    # Check P99 latency
    if stats.num_requests > 0:
        p99 = stats.get_response_time_percentile(0.99) or 0
        if p99 > DEFAULT_SLA.p99_latency_ms:
            print(f"\n[SLA VIOLATION] P99 latency {p99:.0f}ms > {DEFAULT_SLA.p99_latency_ms}ms")

    print(f"\n[SLA CHECK] Error rate: {error_rate:.2f}%, P95: {p95:.0f}ms, P99: {p99:.0f}ms")
