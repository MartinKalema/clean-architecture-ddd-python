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
from src.infrastructure.exceptions import InfrastructureException
from src.presentation.api.routes import book_routes, health_routes, loan_routes, patron_routes


container = Container()
etcd_adapter = container.etcd_adapter()
etcd_adapter.load()
container.configurations.from_dict(etcd_adapter.get_all())


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = container.postgresql()
    await db.init_models()
    yield
    await db.engine.dispose()


app = FastAPI(
    title="Library API",
    description="Clean Architecture Library Management System",
    version="1.0.0",
    lifespan=lifespan
)
app.container = container


@app.exception_handler(InfrastructureException)
async def infrastructure_exception_handler(request: Request, exc: InfrastructureException):
    return JSONResponse(status_code=500, content={"message": "Internal Server Error"})


@app.exception_handler(DomainException)
async def domain_exception_handler(request: Request, exc: DomainException):
    if isinstance(exc, BookNotFoundException):
        return JSONResponse(status_code=404, content={"message": str(exc)})
    if isinstance(exc, BookAlreadyBorrowedException):
        return JSONResponse(status_code=409, content={"message": str(exc)})
    if isinstance(exc, ConcurrentModificationException):
        return JSONResponse(status_code=409, content={"message": str(exc)})
    return JSONResponse(status_code=400, content={"message": str(exc)})


app.include_router(health_routes.router)
app.include_router(book_routes.router)
app.include_router(loan_routes.router)
app.include_router(patron_routes.router)
