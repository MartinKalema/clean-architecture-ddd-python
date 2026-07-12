"""
Book Aggregate Root for the Catalog bounded context.

The book's availability is a state machine, not a boolean:

    AVAILABLE --reserve()--> RESERVED --confirm_borrow()--> BORROWED
                                 |                              |
                             release()                    return_book()
                                 v                              v
                             AVAILABLE                      AVAILABLE

RESERVED is a semantic lock for the borrow saga: it withholds the book
from other borrowers while the Lending context creates the loan, without
pretending the borrow is final. Only one saga can hold a book at a time —
reserve() rejects anything not AVAILABLE.
"""
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Optional

from src.domain.catalog.events import (
    CatalogBookBorrowed,
    CatalogBookReleased,
    CatalogBookReserved,
    CatalogBookReturned,
)
from src.domain.catalog.exceptions import (
    BookAlreadyBorrowedException,
    BorrowerEmailRequiredException,
    InvalidBorrowPeriodException,
    InvalidCatalogReferenceException,
    InvalidCatalogStateException,
    InvalidReservationReasonException,
    LoanCorrelationMismatchException,
    StaleLoanCompletionException,
    StaleReservationException,
)
from src.domain.catalog.value_objects import (
    Author,
    BookId,
    BookStatus,
    ReservationId,
    Title,
)
from src.domain.shared_kernel import (
    AggregateRoot,
    EmailAddress,
    aggregate_transition,
    require_utc_datetime,
)


@dataclass
class Book(AggregateRoot):
    """A book in the library catalog."""
    title: Title
    author: Author
    id: BookId = field(default_factory=BookId.next_id)
    status: BookStatus = BookStatus.AVAILABLE
    reserved_at: Optional[datetime] = None
    borrowed_at: Optional[datetime] = None
    return_due_date: Optional[datetime] = None
    reservation_id: Optional[ReservationId] = None
    reservation_generation: int = 0
    reserved_patron_id: Optional[str] = None
    reserved_patron_email: Optional[str] = None
    current_loan_id: Optional[str] = None
    last_completed_loan_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.title, Title):
            self.title = Title(self.title)
        if not isinstance(self.author, Author):
            self.author = Author(self.author)
        if not isinstance(self.id, BookId):
            self.id = BookId(self.id)
        try:
            if not isinstance(self.status, BookStatus):
                self.status = BookStatus(self.status)
        except (TypeError, ValueError) as error:
            raise InvalidCatalogStateException("unknown status") from error
        if (
            isinstance(self.reservation_generation, bool)
            or not isinstance(self.reservation_generation, int)
            or self.reservation_generation < 0
        ):
            raise InvalidCatalogStateException(
                "reservation generation must be non-negative"
            )
        if self.reservation_id is not None and not isinstance(
            self.reservation_id, ReservationId
        ):
            self.reservation_id = ReservationId(self.reservation_id)
        for field_name in (
            "reserved_patron_id",
            "current_loan_id",
            "last_completed_loan_id",
        ):
            value = getattr(self, field_name)
            if value is not None:
                setattr(
                    self,
                    field_name,
                    self._normalize_reference(value, field_name),
                )
        if self.reserved_patron_email is not None:
            self.reserved_patron_email = EmailAddress(
                self.reserved_patron_email
            ).value
        for field_name in ("reserved_at", "borrowed_at", "return_due_date"):
            value = getattr(self, field_name)
            if value is not None:
                setattr(
                    self,
                    field_name,
                    require_utc_datetime(value, field_name),
                )
        self._validate_state()
        super().__post_init__()

    def _validate_state(self) -> None:
        correlation = (
            self.reservation_id,
            self.reserved_patron_id,
            self.reserved_patron_email,
        )
        if self.status is BookStatus.AVAILABLE:
            if any(
                value is not None
                for value in (
                    self.reserved_at,
                    self.borrowed_at,
                    self.return_due_date,
                    self.current_loan_id,
                )
            ):
                raise InvalidCatalogStateException(
                    "available book retains an active lifecycle field"
                )
            if any(value is not None for value in correlation) and not all(
                value is not None for value in correlation
            ):
                raise InvalidCatalogStateException(
                    "historical reservation correlation is incomplete"
                )
        elif self.status is BookStatus.RESERVED:
            if (
                not all(value is not None for value in correlation)
                or self.reserved_at is None
                or self.reservation_generation < 1
                or any(
                    value is not None
                    for value in (
                        self.borrowed_at,
                        self.return_due_date,
                        self.current_loan_id,
                    )
                )
            ):
                raise InvalidCatalogStateException(
                    "reserved book lacks exact reservation state"
                )
        elif self.status is BookStatus.BORROWED:
            if (
                not all(value is not None for value in correlation)
                or self.reservation_generation < 1
                or self.reserved_at is not None
                or self.current_loan_id is None
                or self.borrowed_at is None
                or self.return_due_date is None
                or self.return_due_date <= self.borrowed_at
            ):
                raise InvalidCatalogStateException(
                    "borrowed book lacks exact loan correlation and dates"
                )

    @property
    def is_borrowed(self) -> bool:
        """Whether a Lending loan has definitively been confirmed."""
        return self.status == BookStatus.BORROWED

    @property
    def is_unavailable(self) -> bool:
        """Whether this book is reserved or definitively borrowed."""
        return self.status != BookStatus.AVAILABLE

    @aggregate_transition
    def reserve(
        self,
        patron_id: str,
        borrower_email: str,
        reserved_at: datetime,
        *,
        reservation_id: str | ReservationId | None = None,
    ) -> ReservationId:
        """
        Reserve the book for a borrower (tentative first step of the
        borrow saga).
        """
        if self.status != BookStatus.AVAILABLE:
            raise BookAlreadyBorrowedException(self.id.value)

        if not borrower_email or not borrower_email.strip():
            raise BorrowerEmailRequiredException()
        patron_id = self._normalize_reference(patron_id, "patron_id")
        borrower_email = EmailAddress(borrower_email).value
        reserved_at = require_utc_datetime(reserved_at, "reserved_at")

        token = (
            reservation_id
            if isinstance(reservation_id, ReservationId)
            else ReservationId(reservation_id)
            if reservation_id is not None
            else ReservationId.next_id()
        )

        self.status = BookStatus.RESERVED
        self.reserved_at = reserved_at
        # Lending owns loan-duration policy. These remain unset until the
        # correlated LoanCreated event supplies its authoritative dates.
        self.borrowed_at = None
        self.return_due_date = None
        self.reservation_id = token
        self.reservation_generation += 1
        self.reserved_patron_id = patron_id
        self.reserved_patron_email = borrower_email
        self.current_loan_id = None

        self.add_event(CatalogBookReserved(
            book_id=self.id.value,
            title=self.title.value,
            reservation_id=token.value,
            reservation_generation=self.reservation_generation,
            patron_id=patron_id,
            reserved_at=reserved_at,
            borrower_email=borrower_email
        ))
        return token

    @aggregate_transition
    def confirm_borrow(
        self,
        reservation_id: str | ReservationId,
        reservation_generation: int,
        patron_id: str,
        loan_id: str,
        borrowed_at: datetime,
        return_due_date: datetime,
    ) -> bool:
        """
        Confirm exactly the reservation for which Lending created a loan.

        Returns ``False`` for an exact redelivery that was already applied.
        A message for any other reservation is stale and can never mutate the
        current state, even if the book has since been reserved again.
        """
        token = self._require_matching_reservation(
            reservation_id, reservation_generation, patron_id, "confirm borrow"
        )
        loan_id = self._normalize_reference(loan_id, "loan_id")
        borrowed_at = require_utc_datetime(borrowed_at, "borrowed_at")
        return_due_date = require_utc_datetime(
            return_due_date, "return_due_date"
        )
        if self.status == BookStatus.BORROWED and self.current_loan_id == loan_id:
            if (
                self.borrowed_at != borrowed_at
                or self.return_due_date != return_due_date
            ):
                raise StaleReservationException(
                    self.id.value,
                    token.value,
                    reservation_generation,
                    "confirm borrow",
                )
            return False
        if self.status != BookStatus.RESERVED or self.current_loan_id is not None:
            raise StaleReservationException(
                self.id.value, token.value, reservation_generation, "confirm borrow"
            )
        if return_due_date <= borrowed_at:
            raise InvalidBorrowPeriodException()
        if self.reserved_at is not None and borrowed_at < self.reserved_at:
            raise InvalidBorrowPeriodException()

        assert self.reserved_patron_email is not None

        self.status = BookStatus.BORROWED
        self.reserved_at = None
        self.current_loan_id = loan_id
        self.borrowed_at = borrowed_at
        self.return_due_date = return_due_date

        self.add_event(CatalogBookBorrowed(
            book_id=self.id.value,
            title=self.title.value,
            reservation_id=token.value,
            reservation_generation=self.reservation_generation,
            patron_id=patron_id,
            loan_id=loan_id,
            borrowed_at=borrowed_at,
            return_due_date=return_due_date,
            borrower_email=self.reserved_patron_email,
        ))
        return True

    @aggregate_transition
    def release(
        self,
        reservation_id: str | ReservationId,
        reservation_generation: int,
        patron_id: str,
        reason: str,
    ) -> bool:
        """Release exactly the reservation named by a compensation/expiry."""
        token = self._require_matching_reservation(
            reservation_id, reservation_generation, patron_id, "release reservation"
        )
        reason = " ".join(str(reason).split())
        if not reason or len(reason) > 500:
            raise InvalidReservationReasonException()
        if self.status == BookStatus.AVAILABLE:
            return False
        if self.status != BookStatus.RESERVED:
            raise StaleReservationException(
                self.id.value,
                token.value,
                reservation_generation,
                "release reservation",
            )

        self.status = BookStatus.AVAILABLE
        self.reserved_at = None
        self.borrowed_at = None
        self.return_due_date = None

        self.add_event(CatalogBookReleased(
            book_id=self.id.value,
            reservation_id=token.value,
            reservation_generation=reservation_generation,
            patron_id=patron_id,
            reason=reason,
        ))
        return True

    @aggregate_transition
    def return_book(
        self,
        loan_id: str,
        reservation_id: str | ReservationId,
        reservation_generation: int,
        patron_id: str,
    ) -> bool:
        """Return only the exact loan and reservation that Catalog recorded."""
        loan_id = self._normalize_reference(loan_id, "loan_id")
        token = (
            reservation_id
            if isinstance(reservation_id, ReservationId)
            else ReservationId(reservation_id)
        )
        if self.status == BookStatus.AVAILABLE and self.last_completed_loan_id == loan_id:
            if self.reservation_generation > reservation_generation:
                raise StaleLoanCompletionException(self.id.value, loan_id)
            self._require_return_correlation(
                loan_id, token, reservation_generation, patron_id
            )
            return False
        if self.status != BookStatus.BORROWED or self.current_loan_id != loan_id:
            raise StaleLoanCompletionException(self.id.value, loan_id)

        self._require_return_correlation(
            loan_id, token, reservation_generation, patron_id
        )
        assert self.reservation_id is not None
        assert self.reserved_patron_id is not None

        self.status = BookStatus.AVAILABLE
        self.borrowed_at = None
        self.return_due_date = None
        self.current_loan_id = None
        self.last_completed_loan_id = loan_id

        self.add_event(CatalogBookReturned(
            book_id=self.id.value,
            loan_id=loan_id,
            reservation_id=self.reservation_id.value,
            reservation_generation=self.reservation_generation,
            patron_id=self.reserved_patron_id,
        ))
        return True

    def _require_return_correlation(
        self,
        loan_id: str,
        token: ReservationId,
        reservation_generation: int,
        patron_id: str,
    ) -> None:
        mismatches = []
        if self.reservation_id != token:
            mismatches.append("reservation_id")
        if self.reservation_generation != reservation_generation:
            mismatches.append("reservation_generation")
        if self.reserved_patron_id != patron_id:
            mismatches.append("patron_id")
        if mismatches:
            raise LoanCorrelationMismatchException(
                self.id.value,
                loan_id,
                f"{', '.join(mismatches)} differ",
            )

    def _require_matching_reservation(
        self,
        reservation_id: str | ReservationId,
        reservation_generation: int,
        patron_id: str,
        operation: str,
    ) -> ReservationId:
        token = (
            reservation_id
            if isinstance(reservation_id, ReservationId)
            else ReservationId(reservation_id)
        )
        if (
            self.reservation_id != token
            or self.reservation_generation != reservation_generation
            or self.reserved_patron_id != patron_id
        ):
            raise StaleReservationException(
                self.id.value, token.value, reservation_generation, operation
            )
        return token

    @staticmethod
    def _normalize_reference(value: str, field: str) -> str:
        normalized = str(value).strip()
        if (
            not normalized
            or len(normalized) > 64
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", normalized)
        ):
            raise InvalidCatalogReferenceException(field)
        return normalized
