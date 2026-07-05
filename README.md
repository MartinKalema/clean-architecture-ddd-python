# Clean Architecture & DDD in Python

A production-grade implementation of **Clean Architecture**, **Domain-Driven Design (DDD)**, and **CQRS** principles in Python. This project demonstrates enterprise patterns for building scalable, maintainable, and resilient backend applications.

## Performance

Load tested with production-like traffic distribution (93% reads, 7% writes):

| Concurrent Users | Requests | Error Rate | P50 | P95 | P99 | RPS |
|------------------|----------|------------|-----|-----|-----|-----|
| 2,000 | 44,000+ | 0% | 4ms | 49ms | - | 295 |
| 3,000 | 183,593 | 0% | 8ms | 66ms | 560ms | 358 |

**System Capacity:**
- **Comfortable load**: 2k users (~295 RPS, sub-50ms P95)
- **Maximum stable load**: 3k users (~358 RPS, 0% errors)
- **Bottleneck**: Elasticsearch GC at higher loads

**Infrastructure**: 8 API instances, PgBouncer (300 pool), Redis cache (120s TTL), single-node Elasticsearch (4GB heap)

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

### Run with CDC Pipeline (Elasticsearch)

```bash
# Start with CDC profile (includes Kafka, Debezium, Elasticsearch)
docker compose --profile cdc up --build

# Kibana available at http://localhost:5601
# Elasticsearch at http://localhost:9200
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
                         ↓                        ↓
                   Redis (Cache)            Debezium (CDC)
                         ↓                        ↓
                   etcd (Config)              Kafka
                                                  ↓
                                           Elasticsearch
```

| Component | Purpose |
|-----------|---------|
| **Nginx** | Load balancer across 8 API instances |
| **PgBouncer** | Connection pooling (300 pool, 10k max connections) |
| **Redis** | Cache layer with TTL-based expiry (120s) |
| **etcd** | Centralized configuration |
| **PostgreSQL** | Primary database (write model) |
| **Debezium** | Change Data Capture from PostgreSQL WAL |
| **Kafka** | Event streaming for CDC pipeline |
| **Elasticsearch** | Read-optimized search (CQRS read model) |

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

        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        books = await self.repository.find_all(**query.__dict__)
        await self.cache.set(cache_key, books)
        return books
```

### Circuit Breaker Pattern

```python
circuit_breaker = CircuitBreaker(
    name="sendgrid",
    failure_threshold=3,
    success_threshold=2,
    timeout=60.0
)

@circuit_breaker
async def send_email(to, subject, content):
    await sendgrid.send(to, subject, content)
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
- [Sagas & Consistency](docs/SAGAS_AND_CONSISTENCY.md) - Sagas, compensation, semantic locks, and apologies in simple English
- [Control Planes](docs/CONTROL_PLANES.md) - Who creates the topics: from auto-create to self-service platforms, in simple English

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
