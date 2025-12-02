# Clean Architecture & DDD in Python

A production-grade implementation of **Clean Architecture**, **Domain-Driven Design (DDD)**, and **CQRS** principles in Python. This project demonstrates enterprise patterns for building scalable, maintainable, and resilient backend applications.

## Architecture Overview

The project follows strict layered architecture with dependency inversion:

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
│    (Repositories, Message Brokers, Email, Circuit Breakers)  │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

1. **Domain Layer** (`src/domain/`)
   - Enterprise business rules
   - Entities (`Book`, `Loan`, `Patron`)
   - Value Objects (`BookId`, `Title`, `Author`, `EmailAddress`)
   - Domain Events (`BookBorrowed`, `BookReturned`)
   - Repository interfaces (contracts)
   - Bounded Contexts with Anti-Corruption Layers
   - **Pure Python** - no external dependencies

2. **Application Layer** (`src/application/`)
   - CQRS handlers separated by responsibility:
     - **Command Handlers**: Write operations (`AddBook`, `BorrowBook`, `ReturnBook`)
     - **Query Handlers**: Read operations (`ListBooks`, `GetBook`)
     - **Event Handlers**: Async reactions to domain events
   - DTOs for input/output

3. **Infrastructure Layer** (`src/infrastructure/`)
   - Repository implementations (SQLAlchemy)
   - External service adapters (RabbitMQ, SendGrid)
   - Resilience patterns (Circuit Breaker)
   - Transactional Outbox for reliable event delivery
   - Configuration management

4. **Presentation Layer** (`src/presentation/`)
   - FastAPI REST endpoints
   - CLI commands (Click)
   - Background workers (Outbox processor, Event consumer)
   - Request/response models

## Key Features

### Core Patterns
- **CQRS**: Command Query Responsibility Segregation
  - Commands (write) and Queries (read) handled separately
  - Optimized read models for query performance
- **Async-First**: Built with `asyncio`, async SQLAlchemy, and `aio-pika`
- **Dependency Injection**: `dependency-injector` for IoC container
- **Unit of Work**: Transactional consistency across aggregates
- **Repository Pattern**: Abstract data access behind interfaces
- **Domain-Driven Design**: Bounded Contexts, Aggregates, Value Objects, Domain Events

### Resilience Patterns
- **Circuit Breaker**: Prevents cascading failures to external services (RabbitMQ, SendGrid)
  - States: CLOSED → OPEN → HALF_OPEN
  - Configurable thresholds via `settings.yaml`
  - Registry for monitoring all circuit breakers

- **Transactional Outbox**: Guarantees event delivery
  - Events stored in same transaction as aggregate changes
  - Background processor dispatches to message broker
  - At-least-once delivery semantics

### Event-Driven Architecture
- **Domain Events**: Published when significant state changes occur
- **RabbitMQ Integration**: Async event dispatching
- **Event Handlers**: Process events for notifications, analytics, etc.

### Infrastructure
- **PgBouncer**: Connection pooling for PostgreSQL (10k+ concurrent users)
- **Health Endpoints**: `/health` and `/health/ready` for orchestration
- **YAML Configuration**: Environment-aware settings with env var overrides

## Directory Structure

```
src/
├── domain/                      # Domain Layer (Pure Python)
│   ├── catalog/                 # Catalog Bounded Context
│   │   ├── entities/            # Book aggregate
│   │   ├── value_objects/       # BookId, Title, Author, ISBN
│   │   ├── events/              # BookBorrowed, BookReturned
│   │   └── interfaces/          # Repository contracts
│   ├── lending/                 # Lending Bounded Context
│   │   ├── entities/            # Loan aggregate
│   │   ├── acl/                 # Anti-Corruption Layer
│   │   └── ...
│   ├── patron/                  # Patron Bounded Context
│   │   ├── entities/            # Patron aggregate
│   │   └── ...
│   └── shared_kernel/           # Cross-context concerns
│       ├── aggregate_root.py    # Base class for aggregates
│       ├── domain_event.py      # Base class for events
│       └── interfaces.py        # Logger, EmailService protocols
├── application/                 # Application Layer (CQRS)
│   ├── command_handlers/        # Write operations (sync)
│   │   ├── add_book.py
│   │   ├── borrow_book.py
│   │   └── return_book.py
│   ├── query_handlers/          # Read operations (sync)
│   │   ├── list_books.py
│   │   └── get_book.py
│   └── event_handlers/          # Async reactions to events
│       └── book_handlers.py
├── infrastructure/              # Infrastructure Layer
│   ├── adapters/
│   │   ├── repositories/        # SQLAlchemy implementations
│   │   ├── messaging/           # RabbitMQ dispatcher
│   │   ├── email/               # SendGrid service
│   │   ├── resilience/          # Circuit breaker
│   │   ├── outbox/              # Transactional outbox
│   │   └── logger/              # Logging implementations
│   ├── configurations/          # YAML settings
│   └── external/                # External service clients
├── presentation/                # Presentation Layer
│   ├── api/                     # FastAPI routes
│   │   ├── routes/              # Endpoint handlers
│   │   └── models/              # Request/response schemas
│   ├── cli/                     # Click commands
│   └── workers/                 # Background processors
└── container.py                 # Dependency Injection container

tests/
├── domain/                      # Entity & value object tests
├── unit/                        # Isolated unit tests
├── infrastructure/              # Adapter tests
├── integration/                 # Repository & handler tests
├── e2e/                         # API & CLI tests
└── load/                        # Locust performance tests
```

## Getting Started

### Prerequisites
- Python 3.10+
- Docker & Docker Compose (for full stack)

### Installation

```bash
# Clone and setup
git clone <repository-url>
cd clean-architecture-ddd-python

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

### Running the Application

#### API Server
```bash
uvicorn src.presentation.api.main:app --reload
```
API docs: http://127.0.0.1:8000/docs

#### CLI
```bash
# Add a book
python -m src.presentation.cli.main add "Clean Architecture" "Robert C. Martin"

# List all books
python -m src.presentation.cli.main list

# Borrow a book
python -m src.presentation.cli.main borrow <book_id> user@example.com

# Return a book
python -m src.presentation.cli.main return <book_id>
```

#### Full Stack (Docker)
```bash
docker-compose up -d
```

## Testing

```bash
# All tests
pytest

# By category
pytest tests/domain          # Domain logic
pytest tests/unit            # Unit tests
pytest tests/infrastructure  # Circuit breaker, adapters
pytest tests/integration     # Repository, use cases
pytest tests/e2e             # API, CLI

# With coverage
pytest --cov=src --cov-report=html
```

### Load Testing
```bash
# Start API server, then:
locust -f tests/load/locustfile.py

# Open http://localhost:8089
```

## Configuration

Settings are managed via `src/infrastructure/configurations/settings.yaml`:

```yaml
database:
  url: "sqlite+aiosqlite:///./library.db"

rabbitmq:
  host: localhost
  exchange: library_events

circuit_breakers:
  rabbitmq:
    failure_threshold: 5
    success_threshold: 2
    timeout: 30.0
  sendgrid:
    failure_threshold: 3
    success_threshold: 2
    timeout: 60.0
```

Override with environment variables:
```bash
export DATABASE_URL="postgresql+asyncpg://..."
export RABBITMQ_HOST="rabbitmq.prod"
export CIRCUIT_BREAKER_RABBITMQ_FAILURE_THRESHOLD=10
```

## Code Style

### TYPE_CHECKING Pattern
For type-hint-only imports, we use `TYPE_CHECKING` to avoid runtime overhead:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.catalog import UnitOfWork

class MyUseCase:
    def __init__(self, uow: UnitOfWork): ...
```

**Note**: FastAPI routes cannot use this pattern as FastAPI needs runtime type evaluation for request body detection.

## License

MIT License
