"""
SQLAlchemy models for Catalog bounded context.

These models are shared between command and query repositories.
"""
from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, String, text

from src.domain.catalog import Author, Book, BookId, BookStatus, ReservationId, Title
from src.infrastructure.external.postgresql import Base


class BookModel(Base):
    """SQLAlchemy model for Book aggregate."""

    __tablename__ = "books"
    __table_args__ = (
        Index("ix_books_status_reserved_at", "status", "reserved_at"),
        Index("ix_books_title_lower_id", text("lower(title)"), "id"),
        Index(
            "ix_books_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "ix_books_author_trgm",
            "author",
            postgresql_using="gin",
            postgresql_ops={"author": "gin_trgm_ops"},
        ),
        CheckConstraint(
            "status IN ('available', 'reserved', 'borrowed')",
            name="ck_books_status",
        ),
        CheckConstraint(
            "reservation_generation >= 0", name="ck_books_reservation_generation"
        ),
        CheckConstraint(
            "id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'", name="ck_books_id"
        ),
        CheckConstraint(
            "reservation_id IS NULL OR reservation_id ~* "
            "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="ck_books_reservation_id",
        ),
        CheckConstraint(
            "reserved_patron_id IS NULL OR reserved_patron_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_books_reserved_patron_id",
        ),
        CheckConstraint(
            "current_loan_id IS NULL OR current_loan_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_books_current_loan_id",
        ),
        CheckConstraint(
            "last_completed_loan_id IS NULL OR last_completed_loan_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_books_last_completed_loan_id",
        ),
        CheckConstraint("version >= 0", name="ck_books_version"),
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 100", name="ck_books_title"),
        CheckConstraint("length(trim(author)) BETWEEN 1 AND 200", name="ck_books_author"),
        CheckConstraint(
            "reserved_patron_email IS NULL OR ("
            "reserved_patron_email = lower(trim(reserved_patron_email)) AND "
            "length(reserved_patron_email) BETWEEN 3 AND 254 AND "
            "reserved_patron_email ~ "
            "'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$')",
            name="ck_books_reserved_patron_email",
        ),
        CheckConstraint(
            "status <> 'reserved' OR ("
            "reservation_generation >= 1 AND reservation_id IS NOT NULL AND "
            "reserved_at IS NOT NULL AND "
            "reserved_patron_id IS NOT NULL AND reserved_patron_email IS NOT NULL AND "
            "current_loan_id IS NULL AND borrowed_at IS NULL AND return_due_date IS NULL)",
            name="ck_books_reserved_state",
        ),
        CheckConstraint(
            "status <> 'borrowed' OR ("
            "reservation_generation >= 1 AND reservation_id IS NOT NULL AND "
            "reserved_at IS NULL AND "
            "reserved_patron_id IS NOT NULL AND reserved_patron_email IS NOT NULL AND "
            "current_loan_id IS NOT NULL AND "
            "borrowed_at IS NOT NULL AND return_due_date > borrowed_at)",
            name="ck_books_borrowed_state",
        ),
        CheckConstraint(
            "status <> 'available' OR (current_loan_id IS NULL AND "
            "reserved_at IS NULL AND borrowed_at IS NULL AND return_due_date IS NULL)",
            name="ck_books_available_state",
        ),
    )

    id = Column(String(64), primary_key=True)
    title = Column(String(100), nullable=False)
    author = Column(String(200), nullable=False)
    status = Column(
        String(16),
        default=BookStatus.AVAILABLE.value,
        server_default=BookStatus.AVAILABLE.value,
        nullable=False,
        index=True,
    )
    reserved_at = Column(DateTime(timezone=True), nullable=True)
    borrowed_at = Column(DateTime(timezone=True), nullable=True)
    return_due_date = Column(DateTime(timezone=True), nullable=True)
    reservation_id = Column(String(36), nullable=True, index=True, unique=True)
    reservation_generation = Column(Integer, default=0, nullable=False)
    reserved_patron_id = Column(String(64), nullable=True)
    reserved_patron_email = Column(String(254), nullable=True)
    current_loan_id = Column(String(64), nullable=True, index=True, unique=True)
    last_completed_loan_id = Column(String(64), nullable=True)
    version = Column(Integer, default=0, nullable=False)

    def to_entity(self) -> Book:
        """Convert DB model to domain entity."""
        book = Book(
            id=BookId(self.id),
            title=Title(self.title),
            author=Author(self.author),
            status=BookStatus(self.status),
            reserved_at=self.reserved_at,
            borrowed_at=self.borrowed_at,
            return_due_date=self.return_due_date,
            reservation_id=(
                ReservationId(self.reservation_id) if self.reservation_id else None
            ),
            reservation_generation=self.reservation_generation,
            reserved_patron_id=self.reserved_patron_id,
            reserved_patron_email=self.reserved_patron_email,
            current_loan_id=self.current_loan_id,
            last_completed_loan_id=self.last_completed_loan_id,
        )
        book._version = self.version
        return book

    @staticmethod
    def from_entity(book: Book) -> "BookModel":
        """Convert domain entity to DB model."""
        return BookModel(
            id=book.id.value,
            title=book.title.value,
            author=book.author.value,
            status=book.status.value,
            reserved_at=book.reserved_at,
            borrowed_at=book.borrowed_at,
            return_due_date=book.return_due_date,
            reservation_id=(book.reservation_id.value if book.reservation_id else None),
            reservation_generation=book.reservation_generation,
            reserved_patron_id=book.reserved_patron_id,
            reserved_patron_email=book.reserved_patron_email,
            current_loan_id=book.current_loan_id,
            last_completed_loan_id=book.last_completed_loan_id,
            version=book.version,
        )
