# Elasticsearch

Elasticsearch is a distributed, RESTful search and analytics engine built on Apache Lucene. It's designed for horizontal scalability, near real-time search, and high availability.

## Core Concepts

### 1. Documents & Indices

```
Index (like a database)
  └── Documents (like rows, stored as JSON)
        └── Fields (like columns)
```

```json
// Example document in a "books" index
{
  "_index": "books",
  "_id": "book-123",
  "_source": {
    "title": "Domain-Driven Design",
    "author": "Eric Evans",
    "isbn": "978-0321125217",
    "available": true
  }
}
```

### 2. Inverted Index

The key to fast full-text search. Maps terms to document IDs:

```
Term          → Documents
"domain"      → [doc1, doc5, doc12]
"driven"      → [doc1, doc5]
"design"      → [doc1, doc3, doc8, doc12]
```

### 3. Shards & Replicas

```
Index "books" (5 primary shards, 1 replica each)
├── Shard 0 (primary) → Node 1    Replica 0 → Node 2
├── Shard 1 (primary) → Node 2    Replica 1 → Node 3
├── Shard 2 (primary) → Node 3    Replica 2 → Node 1
├── Shard 3 (primary) → Node 1    Replica 3 → Node 3
└── Shard 4 (primary) → Node 2    Replica 4 → Node 1
```

- **Shards**: Horizontal partitioning for parallel processing
- **Replicas**: Redundant copies for fault tolerance and read throughput

## Common Operations

### Indexing (Write)

```bash
PUT /books/_doc/1
{
  "title": "Clean Architecture",
  "author": "Robert Martin"
}
```

### Search (Read)

```bash
GET /books/_search
{
  "query": {
    "match": { "title": "architecture" }
  }
}
```

### Aggregations (Analytics)

```bash
GET /books/_search
{
  "aggs": {
    "by_author": {
      "terms": { "field": "author.keyword" }
    }
  }
}
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Elasticsearch Cluster               │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│  │  Node 1  │   │  Node 2  │   │  Node 3  │        │
│  │ (Master) │   │  (Data)  │   │  (Data)  │        │
│  └──────────┘   └──────────┘   └──────────┘        │
│                                                      │
│  Node Types:                                         │
│  • Master: Cluster management, index metadata        │
│  • Data: Stores shards, handles CRUD, search         │
│  • Coordinating: Routes requests, aggregates results │
│  • Ingest: Pre-processing pipelines                  │
└─────────────────────────────────────────────────────┘
```

## Near Real-Time Search

```
Write Request
     │
     ▼
┌─────────────┐     1 second (default)    ┌─────────────┐
│   Buffer    │ ─────────────────────────→│   Segment   │
│  (in-memory)│        "refresh"          │ (searchable)│
└─────────────┘                           └─────────────┘
     │
     │  30 seconds (default)
     ▼  "flush"
┌─────────────┐
│ Transaction │
│     Log     │ → Disk (durability)
└─────────────┘
```

## Use Cases

| Use Case | Why Elasticsearch |
|----------|-------------------|
| **Full-text search** | Inverted index, relevance scoring |
| **Log analytics** | ELK stack (Elasticsearch, Logstash, Kibana) |
| **Application search** | Autocomplete, faceted search |
| **Metrics/APM** | Time-series data, aggregations |
| **CQRS read model** | Fast queries, denormalized data |

## For Your Library App

Elasticsearch fits well as a **read model** in CQRS:

```
┌─────────────┐    CDC/Events    ┌───────────────┐
│ PostgreSQL  │ ───────────────→ │ Elasticsearch │
│   (Write)   │                  │    (Read)     │
└─────────────┘                  └───────────────┘
                                        │
                                        ▼
                                  Fast searches:
                                  • Book title/author search
                                  • Patron lookup
                                  • Loan history queries
```

**Sync Methods:**
1. **Application-level**: Publish events to Kafka → Consumer writes to ES
2. **Logstash JDBC**: Poll database for changes
3. **Debezium**: CDC from PostgreSQL WAL → Kafka → ES connector
