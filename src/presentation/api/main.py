from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.container import Container
from src.domain.catalog import (
    BookAlreadyBorrowedException,
    BookNotFoundException,
    ConcurrentModificationException,
    DomainException,
)
from src.infrastructure.exceptions import (
    CircuitBreakerOpenException,
    InfrastructureException,
    SearchEngineException,
)
from src.presentation.api.routes import book_routes, health_routes, loan_routes, patron_routes


class App(FastAPI):
    """FastAPI application carrying its composition root."""
    container: Container


@asynccontextmanager
async def lifespan(app: App):
    db = app.container.postgresql()
    await db.init_models()
    # Instantiate circuit breakers eagerly: they register with the global
    # registry on creation, so /health/circuits reports every breaker from
    # startup instead of only after the first protected call
    app.container.sendgrid_circuit_breaker()
    app.container.elasticsearch_circuit_breaker()
    yield
    await db.engine.dispose()


async def infrastructure_exception_handler(request: Request, exc: Exception):
    # Search backend unavailable (and PostgreSQL fallback also failed):
    # temporary condition, not a server bug
    if isinstance(exc, (SearchEngineException, CircuitBreakerOpenException)):
        return JSONResponse(status_code=503, content={"message": "Search temporarily unavailable"})
    return JSONResponse(status_code=500, content={"message": "Internal Server Error"})


async def domain_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, BookNotFoundException):
        return JSONResponse(status_code=404, content={"message": str(exc)})
    if isinstance(exc, BookAlreadyBorrowedException):
        return JSONResponse(status_code=409, content={"message": str(exc)})
    if isinstance(exc, ConcurrentModificationException):
        return JSONResponse(status_code=409, content={"message": str(exc)})
    return JSONResponse(status_code=400, content={"message": str(exc)})


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

    app.include_router(health_routes.router)
    app.include_router(book_routes.router)
    app.include_router(loan_routes.router)
    app.include_router(patron_routes.router)

    return app
