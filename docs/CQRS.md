# CQRS Architecture Guide

## Overview

Command Query Responsibility Segregation (CQRS) separates read and write operations into distinct models. This guide covers the current implementation and advanced patterns for scaling reads independently from writes.

## Current Architecture

### Event Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Command   │────▶│  Aggregate  │────▶│   Outbox    │────▶│  RabbitMQ   │
│   Handler   │     │  (Domain)   │     │   Table     │     │  (Broker)   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                           │                                       │
                           │                                       │
                    ┌──────▼──────┐                         ┌──────▼──────┐
                    │ PostgreSQL  │                         │   Event     │
                    │  (Write)    │                         │  Consumer   │
                    └─────────────┘                         └─────────────┘
```

### Domain Events

Events are emitted when aggregates change state:

**Catalog Context**
- `BookAddedToCatalog` - New book added
- `BookRemovedFromCatalog` - Book removed
- `CatalogBookBorrowed` - Book borrowed (includes borrower email, dates)
- `CatalogBookReturned` - Book returned

**Lending Context**
- `LoanCreated` - New loan created
- `LoanCompleted` - Book returned
- `BookOverdue` - Loan became overdue
- `LoanExtended` - Due date extended

**Patron Context**
- `PatronRegistered` - New patron registered
- `PatronSuspended` - Patron suspended
- `PatronReinstated` - Patron reinstated

### Event Emission

Events are added to aggregates via the `AggregateRoot` base class:

```python
class Loan(AggregateRoot):
    @classmethod
    def create(cls, patron_id: str, book_id: str, ...) -> "Loan":
        loan = cls(...)
        loan.add_event(LoanCreated(
            loan_id=loan.id.value,
            patron_id=patron_id,
            book_id=book_id,
            due_date=loan.due_date.value,
        ))
        return loan
```

### Transactional Outbox Pattern

Events are stored atomically with aggregate changes:

```python
async with uow:
    loan = Loan.create(...)
    await uow.loans.add(loan)
    # Events collected from aggregate
    # Stored in outbox table in same transaction
    await uow.commit()
```

**Outbox Table Schema:**
```sql
CREATE TABLE outbox_messages (
    id VARCHAR PRIMARY KEY,
    event_type VARCHAR NOT NULL,
    event_data TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP,
    is_processed BOOLEAN DEFAULT FALSE,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT
);
```

### Event Handlers

Currently implemented handlers:

| Event | Handler | Action |
|-------|---------|--------|
| `CatalogBookBorrowed` | `BookHandlers` | Sends email notification |
| `CatalogBookReturned` | `BookHandlers` | Logs event |

Pending handlers (events emitted but not consumed):
- `LoanCreated` - Could trigger welcome email
- `LoanCompleted` - Could update analytics
- `PatronRegistered` - Could send welcome email
- `BookOverdue` - Could send reminder email

---

## CQRS Scaling Approaches

### Approach 1: Event Sourcing + Kafka

Store events as the source of truth. Rebuild read models by replaying events.

```
┌─────────────────────────────────────────────────────────────────┐
│                        WRITE SIDE                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │   Command   │────▶│  Aggregate  │────▶│   Event     │       │
│  │   Handler   │     │             │     │   Store     │       │
│  └─────────────┘     └─────────────┘     └──────┬──────┘       │
│                                                  │               │
└──────────────────────────────────────────────────┼───────────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │     Kafka       │
                                          │  (Event Log)    │
                                          └────────┬────────┘
                                                   │
┌──────────────────────────────────────────────────┼───────────────┐
│                        READ SIDE                 │                │
├──────────────────────────────────────────────────┼───────────────┤
│                                                  │                │
│         ┌────────────────────────────────────────┤                │
│         │                    │                   │                │
│  ┌──────▼──────┐     ┌──────▼──────┐    ┌──────▼──────┐         │
│  │  Projector  │     │  Projector  │    │  Projector  │         │
│  │  (Books)    │     │  (Loans)    │    │  (Search)   │         │
│  └──────┬──────┘     └──────┬──────┘    └──────┬──────┘         │
│         │                   │                   │                │
│  ┌──────▼──────┐     ┌──────▼──────┐    ┌──────▼──────┐         │
│  │ PostgreSQL  │     │ PostgreSQL  │    │Elasticsearch│         │
│  │ (Read DB)   │     │ (Read DB)   │    │  (Search)   │         │
│  └─────────────┘     └─────────────┘    └─────────────┘         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Implementation:**

```python
# Event Store
class EventStore:
    async def append(self, stream_id: str, events: List[DomainEvent]) -> None:
        for event in events:
            await self.kafka_producer.send(
                topic=f"domain-events",
                key=stream_id,
                value=event.to_dict(),
            )

    async def load(self, stream_id: str) -> List[DomainEvent]:
        # Replay events to rebuild aggregate
        events = await self.kafka_consumer.get_all(stream_id)
        return [deserialize(e) for e in events]

# Projector (Read Model Builder)
class BookProjector:
    async def handle(self, event: DomainEvent) -> None:
        match event:
            case BookAddedToCatalog():
                await self.read_db.execute(
                    "INSERT INTO books_read (id, title, author, available) VALUES (...)"
                )
            case CatalogBookBorrowed():
                await self.read_db.execute(
                    "UPDATE books_read SET available = false WHERE id = ..."
                )
```

**Pros:**
- Complete audit trail
- Time-travel debugging (replay to any point)
- Multiple read models from same events
- Natural fit for DDD

**Cons:**
- Complex to implement
- Event versioning challenges
- Eventual consistency (read models lag)
- Snapshot management needed for performance

---

### Approach 2: CDC with Debezium + Kafka

Use Change Data Capture to stream database changes to Kafka. Simpler than event sourcing.

```
┌─────────────────────────────────────────────────────────────────┐
│                        WRITE SIDE                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │   Command   │────▶│  Aggregate  │────▶│ PostgreSQL  │       │
│  │   Handler   │     │             │     │  (Write)    │       │
│  └─────────────┘     └─────────────┘     └──────┬──────┘       │
│                                                  │               │
└──────────────────────────────────────────────────┼───────────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │    Debezium     │
                                          │  (CDC Connector)│
                                          └────────┬────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │     Kafka       │
                                          │ (Change Stream) │
                                          └────────┬────────┘
                                                   │
┌──────────────────────────────────────────────────┼───────────────┐
│                        READ SIDE                 │                │
├──────────────────────────────────────────────────┼───────────────┤
│                                                  │                │
│         ┌────────────────────────────────────────┤                │
│         │                    │                   │                │
│  ┌──────▼──────┐     ┌──────▼──────┐    ┌──────▼──────┐         │
│  │  Consumer   │     │  Consumer   │    │  Consumer   │         │
│  │  (Replica)  │     │ (Analytics) │    │  (Search)   │         │
│  └──────┬──────┘     └──────┬──────┘    └──────┬──────┘         │
│         │                   │                   │                │
│  ┌──────▼──────┐     ┌──────▼──────┐    ┌──────▼──────┐         │
│  │ PostgreSQL  │     │ ClickHouse  │    │Elasticsearch│         │
│  │ (Read DB)   │     │ (Analytics) │    │  (Search)   │         │
│  └─────────────┘     └─────────────┘    └─────────────┘         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Docker Compose Addition:**

```yaml
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1

  debezium:
    image: debezium/connect:2.4
    depends_on:
      - kafka
      - postgres
    ports:
      - "8083:8083"
    environment:
      BOOTSTRAP_SERVERS: kafka:29092
      GROUP_ID: 1
      CONFIG_STORAGE_TOPIC: debezium_configs
      OFFSET_STORAGE_TOPIC: debezium_offsets
      STATUS_STORAGE_TOPIC: debezium_statuses

  postgres-read:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: library_read
      POSTGRES_PASSWORD: library_read_secret
      POSTGRES_DB: library_read_db
```

**Debezium Connector Configuration:**

```json
{
  "name": "library-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "library",
    "database.password": "library_secret",
    "database.dbname": "library_db",
    "database.server.name": "library",
    "table.include.list": "public.books,public.loans,public.patrons",
    "plugin.name": "pgoutput",
    "publication.name": "library_publication",
    "slot.name": "library_slot"
  }
}
```

**Kafka Consumer (Python):**

```python
from aiokafka import AIOKafkaConsumer

class CDCConsumer:
    def __init__(self, read_db: AsyncSession):
        self.read_db = read_db
        self.consumer = AIOKafkaConsumer(
            "library.public.books",
            "library.public.loans",
            bootstrap_servers="kafka:29092",
            group_id="read-model-sync",
        )

    async def consume(self):
        async for message in self.consumer:
            change = json.loads(message.value)
            await self.apply_change(message.topic, change)

    async def apply_change(self, topic: str, change: dict):
        operation = change["op"]  # c=create, u=update, d=delete
        after = change.get("after")
        before = change.get("before")

        if "books" in topic:
            await self.sync_book(operation, before, after)
        elif "loans" in topic:
            await self.sync_loan(operation, before, after)

    async def sync_book(self, op: str, before: dict, after: dict):
        if op == "c":
            await self.read_db.execute(
                "INSERT INTO books (id, title, author, is_borrowed) VALUES (:id, :title, :author, :is_borrowed)",
                after
            )
        elif op == "u":
            await self.read_db.execute(
                "UPDATE books SET title=:title, author=:author, is_borrowed=:is_borrowed WHERE id=:id",
                after
            )
        elif op == "d":
            await self.read_db.execute(
                "DELETE FROM books WHERE id=:id",
                {"id": before["id"]}
            )
```

**Pros:**
- Minimal code changes to existing application
- Automatic sync of all table changes
- Supports multiple read databases
- Lower latency than event sourcing
- No event versioning issues

**Cons:**
- Couples read model to write model schema
- Less semantic than domain events
- Requires Debezium infrastructure
- CDC captures rows, not domain intent

---

### Approach 3: Simple Read Replica

PostgreSQL streaming replication to a read replica. Minimal changes.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │   Command   │────▶│  Aggregate  │────▶│ PostgreSQL  │       │
│  │   Handler   │     │             │     │  (Primary)  │       │
│  └─────────────┘     └─────────────┘     └──────┬──────┘       │
│                                                  │               │
│                                          ┌───────┴───────┐       │
│                                          │  WAL Stream   │       │
│                                          └───────┬───────┘       │
│                                                  │               │
│  ┌─────────────┐                        ┌───────▼───────┐       │
│  │   Query     │◀───────────────────────│ PostgreSQL    │       │
│  │   Handler   │                        │  (Replica)    │       │
│  └─────────────┘                        └───────────────┘       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Docker Compose:**

```yaml
services:
  postgres-primary:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: library
      POSTGRES_PASSWORD: library_secret
      POSTGRES_DB: library_db
    command:
      - "postgres"
      - "-c" "wal_level=replica"
      - "-c" "max_wal_senders=3"
      - "-c" "max_replication_slots=3"

  postgres-replica:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: library
      POSTGRES_PASSWORD: library_secret
      POSTGRES_DB: library_db
      POSTGRES_PRIMARY_HOST: postgres-primary
      POSTGRES_REPLICATION_MODE: slave
    depends_on:
      - postgres-primary
```

**Application Configuration:**

```python
class Container:
    write_db = providers.Singleton(
        create_engine,
        url="postgresql+asyncpg://library:secret@postgres-primary:5432/library_db"
    )

    read_db = providers.Singleton(
        create_engine,
        url="postgresql+asyncpg://library:secret@postgres-replica:5432/library_db"
    )

    # Command handlers use write_db
    add_book_handler = providers.Factory(
        AddBookHandler,
        uow=write_uow,
    )

    # Query handlers use read_db
    list_books_handler = providers.Factory(
        ListBooksHandler,
        repository=read_repository,  # Points to replica
    )
```

**Pros:**
- Simplest to implement
- Native PostgreSQL feature
- Synchronous or async replication
- No additional infrastructure

**Cons:**
- Same schema for read and write
- Limited to PostgreSQL replicas
- Cannot denormalize for read optimization
- Single database technology

---

## Comparison Matrix

| Feature | Event Sourcing | CDC + Kafka | Read Replica |
|---------|----------------|-------------|--------------|
| **Complexity** | High | Medium | Low |
| **Audit Trail** | Complete | Partial | None |
| **Schema Flexibility** | High | Medium | Low |
| **Latency** | Higher | Medium | Lowest |
| **Infrastructure** | Event Store + Kafka | Debezium + Kafka | PostgreSQL |
| **Code Changes** | Significant | Moderate | Minimal |
| **Multiple Read DBs** | Yes | Yes | No |
| **Time Travel** | Yes | No | No |

---

## Recommended Migration Path

1. **Start with Read Replica** (current + minimal changes)
   - Separate read queries to replica
   - Test CQRS patterns in application

2. **Add CDC with Kafka** (when needed)
   - Add Elasticsearch for search
   - Add ClickHouse for analytics
   - Keep PostgreSQL for main reads

3. **Consider Event Sourcing** (if required)
   - Only for domains requiring complete audit
   - High regulatory/compliance requirements
   - Complex temporal queries needed

---

## Implementation Checklist

### For CDC + Kafka Approach

- [ ] Add Kafka and Zookeeper to docker-compose
- [ ] Add Debezium Connect service
- [ ] Configure PostgreSQL for logical replication
- [ ] Create Debezium connector configuration
- [ ] Implement Kafka consumers for read models
- [ ] Add read database (PostgreSQL replica or different DB)
- [ ] Update query handlers to use read database
- [ ] Add health checks for Kafka connectivity
- [ ] Configure consumer groups and offsets
- [ ] Add monitoring for replication lag
