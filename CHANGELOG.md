# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-11-28

### Added
- **API**: Implemented `GET /books/{book_id}` endpoint to retrieve book details.
- **API**: Implemented `POST /books/{book_id}/return` endpoint to return borrowed books.
- **Use Cases**: Added `GetBook` and `ReturnBook` use cases with full domain logic.
- **DTOs**: Added `GetBookInputDto` and `ReturnBookInputDto`.

### Fixed
- **Load Testing**: Resolved 100% failure rate in load tests by implementing missing endpoints and fixing route logic.
- **Concurrency**: Fixed race conditions in `borrow_book` using database transactions and proper error handling (409 Conflict).
- **Logging**: Fixed `stacklevel` in `JsonLogger` to correctly attribute log source to the caller.
- **Stability**: Fixed `ImportError` in `locustfile.py` and syntax errors in `book_routes.py`.

### Performance
- **Server**: Optimized Uvicorn configuration to use `workers=4` for better concurrency handling under load.
