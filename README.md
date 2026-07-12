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

**Infrastructure**: 8 API instances, role-bounded application pools, PgBouncer, Redis cache, and a single-node Elasticsearch read model

## Quick Start

```bash
# Clone the repository
git clone https://github.com/MartinKalema/clean-architecture-ddd-python.git
cd clean-architecture-ddd-python

# Start the API and all correctness-critical infrastructure
docker compose up --build

# API available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

The default stack runs Alembic migrations before starting the API, then
starts the transactional-outbox pipeline (Debezium, Kafka, durable workflow
workers, and independently scaled notification workers) plus the reservation
reaper, connector monitor, and bounded outbox/durable-state cleaners. These
are part of the operating topology, not optional observability services. Each API instance
refuses to start unless the database revision exactly matches the repository's
Alembic head.

### Add the Elasticsearch Read Model

```bash
# Adds table CDC, Elasticsearch, Kibana, and the ES projection workers.
# The domain-event pipeline already runs in the default stack.
ELASTICSEARCH_ENABLED=true docker compose --profile cdc up --build

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
                   Redis (Cache)          Transactional Outbox
                         ↓                        ↓
                   etcd (Config)      Debezium → Kafka → Event Workers
                                                  ↓
                                  Optional table CDC → Elasticsearch
```

| Component | Purpose |
|-----------|---------|
| **Nginx** | Load balancer across 8 API instances |
| **PgBouncer** | Transaction pooling with a bounded 200-connection backend pool |
| **Redis** | Cache layer with TTL-based expiry (120s) |
| **etcd** | Centralized configuration |
| **PostgreSQL** | Primary database (write model) |
| **Debezium** | Publishes the transactional outbox; optionally publishes table CDC |
| **Kafka** | Delivers domain events to application event workers |
| **Event workers** | Continue cross-context workflows from durable domain events |
| **Connector monitor** | Continuously reports outbox connector/task failure |
| **Reservation reaper** | Releases expired semantic locks when a borrow cannot complete |
| **Outbox cleaner** | Prunes delivered WAL-backed outbox history in bounded batches |
| **Durable-state cleaner** | Bounds idempotency, terminal operation, inbox, and quarantine history |
| **Elasticsearch** | Optional read-optimized search projection (CQRS read model) |

## Layer Responsibilities

### Domain Layer (`src/domain/`)

Pure business logic with no external dependencies:

- **Entities**: `Book`, `Loan`, `Patron` aggregates
- **Value Objects**: `BookId`, `Title`, `EmailAddress`
- **Domain Events**: correlated reservation, borrow, loan, cancellation, and return facts
- **Domain Ports**: aggregate repositories expressed only in domain terms
- **Bounded Contexts**: Catalog, Lending, Patron

### Application Layer (`src/application/`)

CQRS handlers for business operations:

- **Command Handlers**: public catalog/patron/loan use cases plus internal saga transitions
- **Query Handlers**: `ListBooks`, `GetBook`, `ListPatrons` (with caching)
- **Event Handlers**: Async reactions to domain events
- **Application Ports**: clock, cache, logging, email, event delivery, command receipts, and upstream anti-corruption contracts

### Infrastructure Layer (`src/infrastructure/`)

External integrations and technical concerns:

- **Adapters**: Repository implementations, messaging, email, caching
- **Resilience**: Circuit breakers for external services
- **Outbox**: Transactional event delivery guarantee
- **External Clients**: PostgreSQL, Redis, Kafka, Elasticsearch, SendGrid, etcd

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

Two database constraints close the message-redelivery and concurrency races:

```sql
CREATE UNIQUE INDEX ix_loans_reservation_id_unique
ON loans (reservation_id);

CREATE UNIQUE INDEX ix_loans_outstanding_book_unique
ON loans (catalog_book_id)
WHERE status NOT IN ('returned', 'cancelled');
```

Every reservation has a UUID identity and a book-local generation fence.
Catalog stores the exact current loan, so delayed confirmation, compensation,
or return events cannot mutate a newer patron's workflow.
The final Lending decision reloads authoritative Patron facts under a shared
transaction-scoped patron fence. Lending then applies its own tier-to-capacity
and loan-duration policy; Patron does not dictate Lending rules through the ACL.

## Directory Structure

```
src/
├── domain/                      # Domain Layer (Pure Python)
│   ├── catalog/                 # Catalog Bounded Context
│   ├── lending/                 # Lending Bounded Context
│   ├── patron/                  # Patron Bounded Context
│   └── shared_kernel/           # Minimal shared domain concepts
├── application/                 # Application Layer (CQRS)
│   ├── command_handlers/        # Write operations
│   ├── query_handlers/          # Read operations (cached)
│   └── event_handlers/          # Async event processing
├── infrastructure/              # Infrastructure Layer
│   ├── adapters/
│   │   ├── cache/               # Redis cache adapter
│   │   ├── events/              # Kafka event delivery
│   │   ├── email/               # SendGrid service
│   │   ├── resilience/          # Circuit breakers
│   │   └── outbox/              # Transactional outbox
│   └── external/                # External service clients
├── presentation/                # Presentation Layer
│   └── api/                     # FastAPI routes
└── container.py                 # Dependency Injection

tests/
├── domain/                      # Entity & value object tests
├── application/                 # Command/event handler tests
├── infrastructure/              # Adapter and delivery tests
├── integration/                 # Repository & handler tests
├── presentation/                # Public route contracts
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
DATABASE_API_POOL_SIZE=20
DATABASE_API_MAX_OVERFLOW=10
DATABASE_WORKFLOW_POOL_SIZE=5
DATABASE_WORKFLOW_MAX_OVERFLOW=5
REDIS_URL=redis://redis:6379/0
REDIS_ENABLED=true
KAFKA_BOOTSTRAP_SERVERS=kafka:29092

# Circuit breakers
CB_SENDGRID_FAILURE_THRESHOLD=3
CB_SENDGRID_TIMEOUT=60.0
```

Configuration is validated as one immutable startup snapshot before any
database, Kafka, Redis, Elasticsearch, or SendGrid client is constructed.
Unknown or missing keys fail startup without logging secret values. Updating
etcd requires a process restart; running clients are never mutated in place.

### Database Migrations

Alembic is the only schema owner. The application never calls
`metadata.create_all()` and never upgrades the database during startup:

```bash
# Apply this release's schema before starting application processes
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db alembic upgrade head
```

Startup fails fast if `alembic_version` is absent, behind, ahead, or on a
different migration branch. In Docker Compose, the one-shot `migrator` service
runs first and every API instance verifies its result.

The project is pre-release, so revision `baseline_20260712` is the only
supported schema and must be applied to an empty database. Drop and recreate any development
database built from an earlier migration; no old-schema conversion is kept.

## Testing

```bash
# All tests
pytest

# By category
pytest tests/domain          # Domain logic
pytest tests/application     # Application orchestration
pytest tests/infrastructure  # Adapters and messaging
pytest tests/integration     # Repository & handler tests
pytest tests/presentation    # Public HTTP command surface
pytest tests/e2e             # API tests

# With coverage
pytest --cov=src --cov-report=html
```

Database-backed tests intentionally use a migrated PostgreSQL schema; they do
not synthesize one with SQLAlchemy metadata. Migrate a test database first and
point both variables at it:

```bash
DATABASE_URL=postgresql+asyncpg://library:library_secret@localhost:5432/library_test alembic upgrade head
TEST_DATABASE_URL=postgresql+asyncpg://library:library_secret@localhost:5432/library_test pytest tests/integration
```

CI always uses this migrated PostgreSQL path, so PostgreSQL-specific and
migration-only constraints are part of the merge gate.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/books` | List all books |
| POST | `/books` | Add a new book |
| GET | `/books/{id}` | Get book details |
| POST | `/books/{id}/borrow` | Start a borrow (`202` with reservation identity) |
| GET | `/borrow-operations/{id}` | Poll the accepted borrow workflow |
| GET | `/patrons` | List all patrons |
| POST | `/patrons` | Register a patron |
| GET | `/loans/{id}` | Get one loan |
| GET | `/loans/patron/{patron_id}` | List a patron's loans |
| POST | `/loans/{id}/extend` | Extend an active loan |
| POST | `/loans/{id}/return` | Return a loan and reconcile its catalog book |
| GET | `/health` | Liveness check |
| GET | `/health/ready` | Readiness check |

Every public `POST` command requires an `Idempotency-Key` header containing
8–128 URL/log-safe characters. Reusing the key with identical command facts
returns the committed response; reusing it for different facts returns `409`.
The borrow response includes `Location: /borrow-operations/{id}`. List routes
return continuation metadata in `X-Next-Cursor` (and exact totals, when
available, in `X-Total-Count`).

## Documentation

- [Engineering Design System](docs/ENGINEERING_DESIGN_SYSTEM.md) - End-to-end method from outcomes and requirements to evidence and operations
- [Design to Requirements](docs/DESIGN_TO_REQUIREMENTS.md) - Validating, specifying, testing, and tracing engineering requirements
- [Invariant-Driven Architecture](docs/INVARIANT_DRIVEN_ARCHITECTURE.md) - Deriving the minimum architecture from truths that must survive concurrency and failure
- [Formal Methods and Property-Based Testing](docs/FORMAL_METHODS_AND_PROPERTY_TESTING.md) - Choosing and applying generated, stateful, concurrency, and formal verification techniques
- [Delivery Assurance Gaps and Extension Plan](docs/DELIVERY_ASSURANCE_GAPS.md) - Extending sound design into safe delivery, operation, and production learning
- [Engineering Planning and Estimation](docs/ENGINEERING_PLANNING_AND_ESTIMATION.md) - Discovering complete work and creating evidence-based forecasts
- [Engineering Execution Management](docs/ENGINEERING_EXECUTION_MANAGEMENT.md) - Delivering client outcomes on time while controlling quality, scope, dependencies, and variance
- [Human-Centered Systems and Execution](docs/HUMAN_CENTERED_SYSTEMS_AND_EXECUTION.md) - Protecting dignity, agency, health, and sustainable capacity inside delivery systems
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
    from src.application.ports import ILogger

class MyService:
    def __init__(self, logger: ILogger): ...
```

## License

MIT License
