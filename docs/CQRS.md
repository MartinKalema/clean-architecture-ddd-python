# CQRS Architecture Guide

## Overview

Command Query Responsibility Segregation (CQRS) separates read and write operations into distinct models. This project implements a hybrid CQRS approach using PostgreSQL for writes and Elasticsearch for search operations.

## Current Architecture

### Implemented: CDC with Debezium + Kafka + Elasticsearch

```
┌─────────────────────────────────────────────────────────────────┐
│                        WRITE SIDE                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │   Command   │────▶│  Aggregate  │────▶│ PostgreSQL  │       │
│  │   Handler   │     │  (Domain)   │     │  (Write)    │       │
│  └─────────────┘     └─────────────┘     └──────┬──────┘       │
│                                                  │               │
└──────────────────────────────────────────────────┼───────────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │    Debezium     │
                                          │ (CDC Connector) │
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
│                                          ┌───────▼───────┐       │
│                                          │   ES Sync     │       │
│                                          │   Consumer    │       │
│                                          └───────┬───────┘       │
│                                                  │                │
│  ┌─────────────┐                        ┌───────▼───────┐       │
│  │   Query     │◀───────────────────────│ Elasticsearch │       │
│  │   Handler   │                        │   (Search)    │       │
│  └──────┬──────┘                        └───────────────┘       │
│         │                                                        │
│         │ (Point Lookups)                                        │
│         │                                                        │
│  ┌──────▼──────┐                                                │
│  │ PostgreSQL  │                                                │
│  │ (Reads)     │                                                │
│  └─────────────┘                                                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Hybrid Query Strategy

Query repositories use a hybrid approach:
- **Point lookups** (by ID) → PostgreSQL for strong consistency
- **Search/filter operations** → Elasticsearch for fast full-text search

```python
class BookQueryRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        elasticsearch_client: ElasticsearchClient,
    ):
        self._session_factory = session_factory
        self._es_client = elasticsearch_client

    async def find_by_id(self, book_id: str) -> Optional[BookReadModel]:
        """Point lookup - uses PostgreSQL for consistency."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(BookModel).where(BookModel.id == book_id)
            )
            return self._to_read_model(result.scalar_one_or_none())

    async def find_all(
        self,
        title_contains: Optional[str] = None,
        author_contains: Optional[str] = None,
        only_available: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BookReadModel]:
        """Search - uses Elasticsearch for full-text search."""
        query = self._build_es_query(title_contains, author_contains, only_available)
        result = self._es_client.search(index="books", query=query, size=limit, from_=offset)
        return [self._to_read_model_from_es(hit) for hit in result["hits"]]
```

### CDC Pipeline Components

| Component | Image | Purpose |
|-----------|-------|---------|
| Zookeeper | `confluentinc/cp-zookeeper:7.5.0` | Kafka coordination |
| Kafka | `confluentinc/cp-kafka:7.5.0` | Message streaming |
| Debezium | `debezium/connect:2.4` | CDC connector |
| Elasticsearch | `elasticsearch:8.11.0` | Search engine |
| ES Sync | Custom Python | Kafka → ES sync |

### Configuration

CDC topic-to-index mapping is stored in etcd:

```python
"cdc": {
    "topic_to_index": {
        "library.public.books": "books",
        "library.public.patrons": "patrons",
        "library.public.loans": "loans",
    },
},
```

### Elasticsearch Indices

Each entity has a dedicated index with optimized mappings:

**Books Index:**
- Full-text search on `title` and `author`
- Autocomplete support
- Filter by `is_borrowed`

**Patrons Index:**
- Full-text search on `full_name` and `email`
- Filter by `membership_tier` and `is_suspended`

**Loans Index:**
- Filter by `patron_id`, `catalog_book_id`, `status`
- `is_overdue` computed field

---

## Domain Events

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

### Event Flow (Domain Events via RabbitMQ)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Command   │────▶│  Aggregate  │────▶│   Outbox    │────▶│  RabbitMQ   │
│   Handler   │     │  (Domain)   │     │   Table     │     │  (Broker)   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                                                            ┌──────▼──────┐
                                                            │   Event     │
                                                            │  Handlers   │
                                                            └─────────────┘
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

---

## Starting the CDC Stack

```bash
# Start all services including CDC pipeline
docker-compose --profile cdc up -d

# The following happens automatically:
# 1. Elasticsearch starts and becomes healthy
# 2. elasticsearch-init creates indices
# 3. Debezium starts and becomes healthy
# 4. debezium-init registers the PostgreSQL connector
# 5. es-sync starts consuming CDC events
```

### Verifying the Pipeline

```bash
# Check Debezium connector status
curl http://localhost:8083/connectors/library-connector/status | jq

# Check Elasticsearch indices
curl http://localhost:9200/_cat/indices?v

# Test search
curl "http://localhost:8000/books?title=Clean" | jq
```

---

## Alternative Approaches

### Approach 1: Event Sourcing + Kafka

Store events as the source of truth. Rebuild read models by replaying events.

**Pros:**
- Complete audit trail
- Time-travel debugging
- Multiple read models from same events

**Cons:**
- Complex to implement
- Event versioning challenges
- Eventual consistency

### Approach 2: Simple Read Replica

PostgreSQL streaming replication to a read replica.

**Pros:**
- Simplest to implement
- Native PostgreSQL feature
- No additional infrastructure

**Cons:**
- Same schema for read and write
- Cannot denormalize for read optimization
- Single database technology

---

## Comparison Matrix

| Feature | Event Sourcing | CDC + Kafka (Current) | Read Replica |
|---------|----------------|----------------------|--------------|
| **Complexity** | High | Medium | Low |
| **Audit Trail** | Complete | Partial | None |
| **Schema Flexibility** | High | Medium | Low |
| **Latency** | Higher | Medium | Lowest |
| **Full-text Search** | Requires ES | Built-in | Requires setup |
| **Code Changes** | Significant | Moderate | Minimal |
| **Multiple Read DBs** | Yes | Yes | No |

---

## Implementation Checklist

### CDC + Kafka + Elasticsearch (Completed)

- [x] Add Kafka and Zookeeper to docker-compose
- [x] Add Debezium Connect service
- [x] Configure PostgreSQL for logical replication (`wal_level=logical`)
- [x] Create Debezium connector configuration
- [x] Create Elasticsearch index mappings
- [x] Implement Kafka consumer for ES sync (`ElasticsearchSyncConsumer`)
- [x] Create Elasticsearch client wrapper
- [x] Update query repositories to use hybrid approach
- [x] Add init containers for automatic setup
- [x] Move CDC config to etcd
- [x] Add health checks for all CDC services
