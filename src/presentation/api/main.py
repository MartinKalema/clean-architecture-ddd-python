from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.infrastructure.external.database import engine, Base
from src.domain.exceptions.book_exceptions import DomainException, BookNotFoundException, BookAlreadyBorrowedException
from src.presentation.api.routes import book_routes
from src.container import Container

# Create tables
Base.metadata.create_all(bind=engine)

container = Container()

app = FastAPI()
app.container = container

@app.exception_handler(DomainException)
async def domain_exception_handler(request: Request, exc: DomainException):
    if isinstance(exc, BookNotFoundException):
        return JSONResponse(status_code=404, content={"message": str(exc)})
    if isinstance(exc, BookAlreadyBorrowedException):
        return JSONResponse(status_code=409, content={"message": str(exc)})
    return JSONResponse(status_code=400, content={"message": str(exc)})

app.include_router(book_routes.router)

