from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.application.exceptions import (
    ApplicationException,
    BorrowOperationNotFoundException,
    BorrowOperationTransitionException,
    IdempotencyKeyConflictException,
    InvalidIdempotencyKeyException,
)
from src.application.query_handlers.pagination import InvalidPaginationError
from src.container import Container
from src.domain.catalog import (
    BookAlreadyBorrowedException,
    BookNotBorrowedException,
    BookNotFoundException,
    BookNotReservedException,
    BorrowerEmailRequiredException,
    BorrowerNotEligibleException,
    ConcurrentModificationException as CatalogConcurrentModificationException,
    InvalidBorrowPeriodException,
    InvalidCatalogReferenceException,
    InvalidCatalogStateException,
    InvalidReservationReasonException,
    LoanCorrelationMismatchException,
    StaleLoanCompletionException,
    StaleReservationException,
)
from src.domain.lending import (
    BookNotAvailableException,
    CannotExtendOverdueLoanException,
    ConcurrentLoanCreationException,
    ConcurrentModificationException as LoanConcurrentModificationException,
    InvalidCancellationReasonException,
    InvalidLoanDurationException,
    InvalidLoanExtensionException,
    InvalidLoanIdException,
    InvalidLoanReferenceException,
    InvalidLoanReturnDateException,
    InvalidLoanStateException,
    InvalidReservationGenerationException,
    InvalidReservationIdException,
    LoanAlreadyReturnedException,
    LoanNotActiveException,
    LoanNotFoundException,
    LoanNotOverdueException,
    PatronBorrowingLimitReachedException,
    PatronNotEligibleForLoanException,
    ReservationCorrelationMismatchException,
)
from src.domain.patron import (
    InvalidPatronIdException,
    InvalidPatronNameException,
    InvalidPatronStateException,
    InvalidSuspensionReasonException,
    InvalidTierUpgradeException,
    PatronAlreadySuspendedException,
    PatronEmailAlreadyRegisteredException,
    PatronNotFoundException,
    PatronNotSuspendedException,
)
from src.domain.patron.exceptions import (
    ConcurrentModificationException as PatronConcurrentModificationException,
)
from src.domain.shared_kernel import DomainException, ValidationException
from src.infrastructure.exceptions import (
    CircuitBreakerOpenException,
    InfrastructureException,
    SearchEngineException,
)
from src.presentation.api.routes import book_routes, health_routes, loan_routes, patron_routes


_DOMAIN_CONFLICTS = (
    BookAlreadyBorrowedException,
    BookNotBorrowedException,
    BookNotReservedException,
    BookNotAvailableException,
    CannotExtendOverdueLoanException,
    CatalogConcurrentModificationException,
    ConcurrentLoanCreationException,
    InvalidTierUpgradeException,
    LoanAlreadyReturnedException,
    LoanConcurrentModificationException,
    LoanCorrelationMismatchException,
    LoanNotActiveException,
    LoanNotOverdueException,
    PatronAlreadySuspendedException,
    PatronConcurrentModificationException,
    PatronEmailAlreadyRegisteredException,
    PatronNotSuspendedException,
    PatronBorrowingLimitReachedException,
    ReservationCorrelationMismatchException,
    StaleLoanCompletionException,
    StaleReservationException,
)

_DOMAIN_VALIDATION_ERRORS = (
    BorrowerEmailRequiredException,
    InvalidBorrowPeriodException,
    InvalidCancellationReasonException,
    InvalidCatalogReferenceException,
    InvalidCatalogStateException,
    InvalidLoanDurationException,
    InvalidLoanExtensionException,
    InvalidLoanIdException,
    InvalidLoanReferenceException,
    InvalidLoanReturnDateException,
    InvalidLoanStateException,
    InvalidPatronIdException,
    InvalidPatronNameException,
    InvalidPatronStateException,
    InvalidReservationGenerationException,
    InvalidReservationIdException,
    InvalidReservationReasonException,
    InvalidSuspensionReasonException,
    ValidationException,
)


class App(FastAPI):
    """FastAPI application carrying its composition root."""
    container: Container


@asynccontextmanager
async def lifespan(app: App):
    db = app.container.postgresql()
    try:
        # Migrations are a deployment responsibility. Refuse traffic when the
        # migrator has not brought PostgreSQL exactly to this release's head.
        await db.verify_schema_current()

        # Instantiate circuit breakers eagerly: they register with the global
        # registry on creation, so /health/circuits reports every breaker from
        # startup instead of only after the first protected call
        app.container.sendgrid_circuit_breaker()
        app.container.elasticsearch_circuit_breaker()
        yield
    finally:
        # Lazy clients may have opened pools during a request. Close every API
        # process-owned transport even when startup or request handling fails;
        # one cleanup failure must not prevent the remaining resources closing.
        logger = app.container.logger()
        cleanup_errors: list[tuple[str, Exception]] = []
        for name, provider, close_method in (
            ("redis", app.container.redis_client, "close"),
            ("elasticsearch", app.container.elasticsearch_client, "close"),
            ("projection freshness", app.container.projection_freshness, "close"),
            ("postgresql", lambda: db, "dispose"),
        ):
            try:
                resource = provider()
                await getattr(resource, close_method)()
            except Exception as cleanup_error:
                cleanup_errors.append((name, cleanup_error))
        try:
            app.container.etcd_adapter().close()
        except Exception as cleanup_error:
            cleanup_errors.append(("etcd", cleanup_error))
        for name, resource_error in cleanup_errors:
            logger.error(
                f"Failed to close {name} client", exception=resource_error
            )


async def infrastructure_exception_handler(request: Request, exc: Exception):
    # Search backend unavailable (and PostgreSQL fallback also failed):
    # temporary condition, not a server bug
    if isinstance(exc, (SearchEngineException, CircuitBreakerOpenException)):
        return _error_response(503, "service_unavailable", "Search temporarily unavailable")
    return _error_response(500, "internal_error", "Internal Server Error")


async def domain_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, (BookNotFoundException, LoanNotFoundException, PatronNotFoundException)):
        return _error_response(404, "not_found", str(exc))
    if isinstance(exc, (BorrowerNotEligibleException, PatronNotEligibleForLoanException)):
        return _error_response(403, "borrower_not_eligible", str(exc))
    if isinstance(exc, _DOMAIN_CONFLICTS):
        return _error_response(409, "conflict", str(exc))
    if isinstance(exc, _DOMAIN_VALIDATION_ERRORS):
        return _error_response(422, "validation_error", str(exc))
    return _error_response(400, "domain_error", str(exc))


async def application_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, BorrowOperationNotFoundException):
        return _error_response(404, "not_found", str(exc))
    if isinstance(exc, IdempotencyKeyConflictException):
        return _error_response(409, "idempotency_conflict", str(exc))
    if isinstance(exc, BorrowOperationTransitionException):
        return _error_response(409, "workflow_conflict", str(exc))
    if isinstance(exc, (InvalidIdempotencyKeyException, InvalidPaginationError)):
        return _error_response(422, "validation_error", str(exc))
    return _error_response(400, "application_error", str(exc))


async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    details = [
        {
            "location": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return _error_response(
        422,
        "validation_error",
        "Request validation failed",
        details=details,
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    code = {
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        503: "service_unavailable",
    }.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return _error_response(exc.status_code, code, message)


def _error_response(
    status: int,
    code: str,
    message: str,
    *,
    details: list[dict[str, str]] | None = None,
) -> JSONResponse:
    error: dict[str, object] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return JSONResponse(
        status_code=status,
        content={"error": error},
    )


def create_app() -> App:
    """
    Application factory - the Main component.

    All composition happens here, on explicit invocation: importing this
    module has no side effects (no container build, no etcd calls), which
    keeps tests and tooling free to import without infrastructure.
    Run with: uvicorn --factory src.presentation.api.main:create_app
    """
    container = Container()
    etcd_adapter = container.etcd_adapter()
    etcd_adapter.load()
    container.configurations.from_dict(etcd_adapter.get_all())

    app = App(
        title="Library API",
        description="Clean Architecture Library Management System",
        version="1.0.0",
        lifespan=lifespan
    )
    app.container = container

    app.add_exception_handler(InfrastructureException, infrastructure_exception_handler)
    app.add_exception_handler(DomainException, domain_exception_handler)
    app.add_exception_handler(ApplicationException, application_exception_handler)
    app.add_exception_handler(
        RequestValidationError,
        cast(Any, request_validation_exception_handler),
    )
    app.add_exception_handler(
        HTTPException,
        cast(Any, http_exception_handler),
    )

    app.include_router(health_routes.router)
    app.include_router(book_routes.router)
    app.include_router(loan_routes.router)
    app.include_router(patron_routes.router)

    return app
