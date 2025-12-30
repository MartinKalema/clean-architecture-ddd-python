"""
Base classes for load testing.

Provides common functionality for all user types:
- Proper state management (per-user, not shared)
- Test data isolation
- Cleanup support
- Custom metrics
"""
import uuid
from typing import Optional

from locust import HttpUser, events
from locust.runners import MasterRunner, WorkerRunner

from .config import DEFAULT_SLA, TEST_DATA_PREFIX


class BaseLibraryUser(HttpUser):
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
        self._my_patrons: list[dict] = []  # {id, email}
        self._my_loans: list[str] = []
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

    # Patron methods
    def create_patron(self, first_name: str, last_name: str, email: str) -> Optional[dict]:
        """
        Create a patron and track it for cleanup.

        Returns patron dict {id, email} if successful, None otherwise.
        """
        response = self.client.post("/patrons", json={
            "first_name": f"{self.test_prefix}_{first_name}",
            "last_name": last_name,
            "email": email,
        })

        if response.status_code == 201:
            data = response.json()
            patron = {"id": data["id"], "email": data["email"]}
            self._my_patrons.append(patron)
            return patron
        return None

    def get_patron(self, patron_id: str) -> bool:
        """Get patron details."""
        with self.client.get(
            f"/patrons/{patron_id}",
            catch_response=True,
            name="/patrons/{id}",
        ) as response:
            if response.status_code == 200:
                response.success()
                return True
            elif response.status_code == 404:
                response.failure("Patron not found")
                return False
            else:
                response.failure(f"Unexpected: {response.status_code}")
                return False

    def list_patrons(self) -> list:
        """List all patrons."""
        response = self.client.get("/patrons")
        if response.status_code == 200:
            return response.json()
        return []

    # Loan methods
    def create_loan(self, patron_id: str, patron_email: str, book_id: str, book_title: str) -> Optional[str]:
        """
        Create a loan and track it.

        Returns loan ID if successful, None otherwise.
        """
        with self.client.post(
            "/loans",
            json={
                "patron_id": patron_id,
                "patron_email": patron_email,
                "catalog_book_id": book_id,
                "book_title": book_title,
                "loan_duration_days": 14,
            },
            catch_response=True,
            name="/loans",
        ) as response:
            if response.status_code == 201:
                loan_id = response.json()["id"]
                self._my_loans.append(loan_id)
                response.success()
                return loan_id
            elif response.status_code == 409:
                # Book already borrowed - expected in concurrent tests
                response.success()
                return None
            else:
                response.failure(f"Unexpected: {response.status_code}")
                return None

    def get_loan(self, loan_id: str) -> bool:
        """Get loan details."""
        with self.client.get(
            f"/loans/{loan_id}",
            catch_response=True,
            name="/loans/{id}",
        ) as response:
            if response.status_code == 200:
                response.success()
                return True
            elif response.status_code == 404:
                response.failure("Loan not found")
                return False
            else:
                response.failure(f"Unexpected: {response.status_code}")
                return False

    def list_patron_loans(self, patron_id: str) -> list:
        """List loans for a patron."""
        with self.client.get(
            f"/loans/patron/{patron_id}",
            catch_response=True,
            name="/loans/patron/{id}",
        ) as response:
            if response.status_code == 200:
                response.success()
                return response.json()
            else:
                response.failure(f"Unexpected: {response.status_code}")
                return []

    def extend_loan(self, loan_id: str, days: int = 7) -> bool:
        """Extend a loan."""
        with self.client.post(
            f"/loans/{loan_id}/extend",
            json={"days": days},
            catch_response=True,
            name="/loans/{id}/extend",
        ) as response:
            if response.status_code == 200:
                response.success()
                return True
            elif response.status_code in (400, 404):
                # Loan not active or not found - expected
                response.success()
                return False
            else:
                response.failure(f"Unexpected: {response.status_code}")
                return False

    def return_loan(self, loan_id: str) -> bool:
        """Return a loan."""
        with self.client.post(
            f"/loans/{loan_id}/return",
            catch_response=True,
            name="/loans/{id}/return",
        ) as response:
            if response.status_code == 200:
                if loan_id in self._my_loans:
                    self._my_loans.remove(loan_id)
                response.success()
                return True
            elif response.status_code in (400, 404):
                # Already returned or not found - expected
                response.success()
                return False
            else:
                response.failure(f"Unexpected: {response.status_code}")
                return False

    def on_stop(self):
        """Cleanup when user stops - return loans and borrowed books."""
        for loan_id in list(self._my_loans):
            self.return_loan(loan_id)
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
