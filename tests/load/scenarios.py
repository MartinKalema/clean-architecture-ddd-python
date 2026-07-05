"""
Realistic User Scenarios for Load Testing.

Models different user personas based on actual usage patterns:
- Browser: Casual user just looking around
- Borrower: Active library patron using new loan system
- Librarian: Admin user managing books and patrons
- PatronManager: Staff managing patron accounts
"""
import random
import uuid

from locust import between, tag, task

from base import BaseLibraryUser


class BrowserUser(BaseLibraryUser):
    """
    Casual browser - mostly reads, rarely interacts.

    Represents 50% of typical library traffic.
    """

    weight = 50
    wait_time = between(2, 5)

    @task(10)
    @tag("read", "browse")
    def list_books(self):
        """Browse the book catalog."""
        self.client.get("/books")

    @task(5)
    @tag("read", "browse")
    def view_random_book(self):
        """View a specific book's details."""
        response = self.client.get("/books", name="/books (for browse)")
        if response.status_code == 200:
            books = response.json()
            if books:
                book = random.choice(books)
                self.get_book(book["id"])

    @task(3)
    @tag("read", "browse")
    def list_patrons(self):
        """Browse patrons list."""
        self.client.get("/patrons")

    @task(1)
    @tag("read", "health")
    def check_health(self):
        """Occasional health check."""
        self.client.get("/health")


class BorrowerUser(BaseLibraryUser):
    """
    Active patron - creates loans and returns books.

    Represents 30% of typical library traffic.
    Uses the new Loan API instead of book borrow/return.
    """

    weight = 30
    wait_time = between(1, 3)

    def on_start(self):
        """Setup: create a patron and book for this user's session."""
        self._patron = self.create_patron(
            first_name=f"Patron_{uuid.uuid4().hex[:6]}",
            last_name="LoadTest",
            email=f"patron_{self._test_run_id}@loadtest.com"
        )
        self._book = None
        book_id = self.create_book(
            title=f"BorrowerBook_{uuid.uuid4().hex[:6]}",
            author="Test Author"
        )
        if book_id:
            response = self.client.get(f"/books/{book_id}")
            if response.status_code == 200:
                self._book = response.json()

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

    @task(3)
    @tag("write", "saga")
    def borrow_via_saga(self):
        """
        Borrow through the saga endpoint: reserve -> loan -> confirm.

        Creates a fresh book so the reservation is uncontended; the loan
        and confirmation happen asynchronously in the event worker.
        """
        if not self._patron:
            return

        book_id = self.create_book(
            title=f"SagaBook_{uuid.uuid4().hex[:6]}",
            author="Saga Author"
        )
        if book_id:
            self.borrow_book(book_id, self._patron["email"])

    @task(3)
    @tag("write", "loan")
    def create_new_loan(self):
        """Create a loan using the Loan API."""
        if not self._patron:
            return

        response = self.client.get("/books", name="/books (for loan)")
        if response.status_code == 200:
            books = response.json()
            available = [b for b in books if not b.get("is_borrowed", False)]
            if available:
                book = random.choice(available)
                self.create_loan(
                    patron_id=self._patron["id"],
                    patron_email=self._patron["email"],
                    book_id=book["id"],
                    book_title=book["title"]
                )

    @task(2)
    @tag("read", "loan")
    def view_my_loans(self):
        """View current loans."""
        if self._patron:
            self.list_patron_loans(self._patron["id"])

    @task(1)
    @tag("write", "loan")
    def extend_active_loan(self):
        """Extend an active loan."""
        if self._my_loans:
            loan_id = random.choice(self._my_loans)
            self.extend_loan(loan_id)

    @task(1)
    @tag("write", "loan")
    def return_active_loan(self):
        """Return a loan."""
        if self._my_loans:
            loan_id = random.choice(self._my_loans)
            self.return_loan(loan_id)


class LibrarianUser(BaseLibraryUser):
    """
    Librarian/Admin - manages the book catalog.

    Represents 10% of typical library traffic.
    """

    weight = 10
    wait_time = between(0.5, 2)

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
        self.client.get("/health/ready")

    @task(1)
    @tag("read", "admin", "health")
    def check_circuit_breakers(self):
        """Monitor circuit breaker status."""
        self.client.get("/health/circuits")


class PatronManagerUser(BaseLibraryUser):
    """
    Staff managing patron accounts.

    Represents 10% of typical library traffic.
    """

    weight = 10
    wait_time = between(1, 3)

    @task(5)
    @tag("read", "patron")
    def list_all_patrons(self):
        """View all patrons."""
        self.client.get("/patrons")

    @task(3)
    @tag("read", "patron")
    def view_patron_details(self):
        """View specific patron."""
        if self._my_patrons:
            patron = random.choice(self._my_patrons)
            self.get_patron(patron["id"])

    @task(2)
    @tag("write", "patron")
    def register_new_patron(self):
        """Register a new patron."""
        self.create_patron(
            first_name=f"New_{uuid.uuid4().hex[:6]}",
            last_name="Patron",
            email=f"new_{uuid.uuid4().hex[:8]}@loadtest.com"
        )

    @task(2)
    @tag("read", "loan")
    def view_patron_loans(self):
        """View loans for a patron."""
        if self._my_patrons:
            patron = random.choice(self._my_patrons)
            self.list_patron_loans(patron["id"])


class StressTestUser(BaseLibraryUser):
    """
    Aggressive user for stress testing - rapid requests.

    Used specifically for stress/spike tests.
    """

    weight = 0  # Not used in normal tests - enable explicitly
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Setup for stress testing."""
        self._patron = self.create_patron(
            first_name="Stress",
            last_name="Tester",
            email=f"stress_{self._test_run_id}@loadtest.com"
        )

    @task(5)
    def rapid_list(self):
        """Rapid catalog queries."""
        self.client.get("/books")

    @task(3)
    def rapid_create_and_loan(self):
        """Rapid create book and loan cycle."""
        if not self._patron:
            return

        book_id = self.create_book(
            title=f"Stress_{uuid.uuid4().hex[:8]}",
            author="StressBot"
        )
        if book_id:
            response = self.client.get(f"/books/{book_id}")
            if response.status_code == 200:
                book = response.json()
                self.create_loan(
                    patron_id=self._patron["id"],
                    patron_email=self._patron["email"],
                    book_id=book_id,
                    book_title=book["title"]
                )

    @task(2)
    def health_spam(self):
        """Spam health endpoints."""
        self.client.get("/health")
        self.client.get("/health/circuits")

    @task(2)
    def patron_operations(self):
        """Rapid patron operations."""
        self.client.get("/patrons")
        if self._my_patrons:
            patron = random.choice(self._my_patrons)
            self.list_patron_loans(patron["id"])
