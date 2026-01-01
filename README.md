# Clean Architecture & DDD in Python

A production-grade implementation of **Clean Architecture**, **Domain-Driven Design (DDD)**, and **CQRS** principles in Python. This project demonstrates enterprise patterns for building scalable, maintainable, and resilient backend applications.

## Performance

Tested with 10,000 concurrent users:

| Metric | Value |
|--------|-------|
| Requests | 299,048 |
| Error Rate | 0% |
| P50 Latency | 1,500ms |
| P95 Latency | 4,800ms |
| P99 Latency | 6,600ms |
| Peak RPS | 1,219 |

## Quick Start

```bash
# Clone the repository
git clone https://github.com/MartinKalema/clean-architecture-ddd-python.git
cd clean-architecture-ddd-python

# Start all services with Docker
docker compose up --build

# API available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### Run Load Tests

```bash
# Start with load testing profile
docker compose --profile loadtest up --build --scale locust-worker=4

# Open Locust UI at http://localhost:8089
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                        │
│              (FastAPI, CLI, Background Workers)              │
├─────────────────────────────────────────────────────────────┤
│                    Application Layer                         │
│      (Command Handlers, Query Handlers, Event Handlers)      │
├─────────────────────────────────────────────────────────────┤
│                      Domain Layer                            │
│        (Entities, Value Objects, Domain Events, Interfaces)  │
├─────────────────────────────────────────────────────────────┤
│                   Infrastructure Layer                       │
│    (Repositories, Message Brokers, Cache, Circuit Breakers)  │
└─────────────────────────────────────────────────────────────┘
```

### Infrastructure Stack

```
Client → Nginx (LB) → API (x8) → PgBouncer → PostgreSQL
                         ↓
                   Redis (Cache)
                         ↓
                   RabbitMQ (Events)
                         ↓
                   etcd (Config)
```

| Component | Purpose |
|-----------|---------|
| **Nginx** | Load balancer across 8 API instances |
| **PgBouncer** | Connection pooling (300 pool, 10k max connections) |
| **Redis** | Cache layer with 5-minute TTL |
| **RabbitMQ** | Async event messaging |
| **etcd** | Centralized configuration |
| **PostgreSQL** | Primary database |

## Layer Responsibilities

### Domain Layer (`src/domain/`)

Pure business logic with no external dependencies:

- **Entities**: `Book`, `Loan`, `Patron` aggregates
- **Value Objects**: `BookId`, `Title`, `EmailAddress`
- **Domain Events**: `BookBorrowed`, `BookReturned`
- **Interfaces**: `ILogger`, `IEventDispatcher`, `IEmailService`, `ICache`
- **Bounded Contexts**: Catalog, Lending, Patron

### Application Layer (`src/application/`)

CQRS handlers for business operations:

- **Command Handlers**: `AddBook`, `BorrowBook`, `CreateLoan`, `ReturnBook`
- **Query Handlers**: `ListBooks`, `GetBook`, `ListPatrons` (with caching)
- **Event Handlers**: Async reactions to domain events

### Infrastructure Layer (`src/infrastructure/`)

External integrations and technical concerns:

- **Adapters**: Repository implementations, messaging, email, caching
- **Resilience**: Circuit breakers for RabbitMQ and SendGrid
- **Outbox**: Transactional event delivery guarantee
- **External Clients**: Redis, RabbitMQ, SendGrid, etcd

### Presentation Layer (`src/presentation/`)

API and user interfaces:

- **FastAPI Routes**: REST endpoints for books, loans, patrons
- **Health Checks**: `/health`, `/health/ready`, `/health/circuit-breakers`

## Key Features

### CQRS with Caching

```python
class ListBooksHandler:
    def __init__(self, repository: BookQueryRepository, cache: ICache, logger: ILogger):
        self.repository = repository
        self.cache = cache

    async def handle(self, query: ListBooksQuery) -> List[BookReadModel]:
        cache_key = self.cache.build_list_key("book", **query.__dict__)

        cached = self.cache.get(cache_key)
        if cached:
            return cached

        books = await self.repository.find_all(**query.__dict__)
        self.cache.set(cache_key, books)
        return books
```

### Circuit Breaker Pattern

```python
circuit_breaker = CircuitBreaker(
    name="rabbitmq",
    failure_threshold=5,
    success_threshold=2,
    timeout=30.0
)

@circuit_breaker
async def publish_event(event):
    await rabbitmq.publish(event)
```

### Transactional Outbox

Events are stored atomically with aggregate changes, then dispatched asynchronously:

```python
async with uow:
    book.borrow(patron_email)
    await uow.books.update(book)
    await uow.outbox.add(BookBorrowedEvent(...))
    await uow.commit()  # Both saved in same transaction
```

### Race Condition Prevention

Partial unique index prevents duplicate active loans:

```sql
CREATE UNIQUE INDEX ix_loans_active_book_unique
ON loans (catalog_book_id)
WHERE status = 'active'
```

## Directory Structure

```
src/
├── domain/                      # Domain Layer (Pure Python)
│   ├── catalog/                 # Catalog Bounded Context
│   ├── lending/                 # Lending Bounded Context
│   ├── patron/                  # Patron Bounded Context
│   └── shared_kernel/           # Cross-context interfaces
├── application/                 # Application Layer (CQRS)
│   ├── command_handlers/        # Write operations
│   ├── query_handlers/          # Read operations (cached)
│   └── event_handlers/          # Async event processing
├── infrastructure/              # Infrastructure Layer
│   ├── adapters/
│   │   ├── cache/               # Redis cache adapter
│   │   ├── messaging/           # RabbitMQ dispatcher
│   │   ├── email/               # SendGrid service
│   │   ├── resilience/          # Circuit breakers
│   │   └── outbox/              # Transactional outbox
│   └── external/                # External service clients
├── presentation/                # Presentation Layer
│   └── api/                     # FastAPI routes
└── container.py                 # Dependency Injection

tests/
├── domain/                      # Entity & value object tests
├── unit/                        # Isolated unit tests
├── integration/                 # Repository & handler tests
├── e2e/                         # API tests
└── load/                        # Locust performance tests
    ├── scenarios.py             # User behavior definitions
    ├── shapes/                  # Load test shapes
    └── run_*.py                 # Test runners
```

## Configuration

Configuration is managed through etcd with environment variable overrides:

```bash
# Core services
DATABASE_URL=postgresql+asyncpg://user:pass@pgbouncer:6432/db
REDIS_URL=redis://redis:6379/0
REDIS_ENABLED=true
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

# Circuit breakers
CB_RABBITMQ_FAILURE_THRESHOLD=5
CB_RABBITMQ_TIMEOUT=30.0
```

## Testing

```bash
# All tests
pytest

# By category
pytest tests/domain          # Domain logic
pytest tests/unit            # Unit tests
pytest tests/integration     # Repository & handler tests
pytest tests/e2e             # API tests

# With coverage
pytest --cov=src --cov-report=html
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/books` | List all books |
| POST | `/books` | Add a new book |
| GET | `/books/{id}` | Get book details |
| POST | `/books/{id}/borrow` | Borrow a book |
| POST | `/books/{id}/return` | Return a book |
| GET | `/patrons` | List all patrons |
| POST | `/patrons` | Register a patron |
| GET | `/loans` | List all loans |
| POST | `/loans` | Create a loan |
| GET | `/health` | Liveness check |
| GET | `/health/ready` | Readiness check |

## Documentation

- [Deployment Guide](docs/DEPLOYMENT.md) - Docker, Kubernetes, Cloud Run
- [Strategic DDD Guide](docs/STRATEGIC_DDD_GUIDE.md) - Domain modeling approach
- [Context Map](docs/CONTEXT_MAP.md) - Bounded context relationships
- [Event Storming](docs/EVENT_STORMING.md) - Domain event flows
- [Ubiquitous Language](docs/UBIQUITOUS_LANGUAGE.md) - Domain terminology

## Code Conventions

### Interface Naming

All interfaces use `I` prefix:

```python
class ILogger(Protocol):
    def info(self, message: str) -> None: ...

class IEventDispatcher(Protocol):
    async def dispatch(self, event: DomainEvent) -> None: ...
```

### TYPE_CHECKING Pattern

Interface imports go under `TYPE_CHECKING` to avoid runtime overhead:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger

class MyService:
    def __init__(self, logger: ILogger): ...
```

## License

MIT License
