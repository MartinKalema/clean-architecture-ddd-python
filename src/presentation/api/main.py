from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.infrastructure.external.database import Base
from src.domain.exceptions.book_exceptions import DomainException, BookNotFoundException, BookAlreadyBorrowedException
from src.presentation.api.routes import book_routes
from src.container import Container

from src.infrastructure.exceptions import InfrastructureException

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database
    db = container.database()
    await db.init_models()
    yield
    # Shutdown: Dispose engine
    await db.engine.dispose()

container = Container()

app = FastAPI(lifespan=lifespan)
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
    return JSONResponse(status_code=400, content={"message": str(exc)})

app.include_router(book_routes.router)

