# Reads vs Searches

All searches are reads, but not all reads are searches. Understanding this distinction is key to designing scalable systems.

## Types of Read Operations

| Type | Example | Optimized By |
|------|---------|--------------|
| **Point lookup** | Get book by ID | Primary key index |
| **Range query** | Books published 2020-2024 | B-tree index |
| **Search** | Books with "architecture" in title | Inverted index |
| **Aggregation** | Count books by author | Column stores, pre-computed |

## The Difference

### Point Lookup (O(1) - instant)

```
GET /books/book-123
→ Direct hash lookup, returns immediately
```

The database knows exactly where the data lives. Like looking up a word in a dictionary when you know the exact spelling.

### Search (O(log n) with proper index, O(n) without)

```
GET /books?title_contains=architecture
→ Must find all matching documents
→ Rank by relevance
→ Return sorted results
```

The database must find all matches, score them, and return sorted results. Like asking "find all words related to 'happy'" - requires understanding meaning, not just location.

## Why Firestore (and Similar Databases) Struggle

```
Firestore Query: "Find books where title contains 'architecture'"

┌─────────────────────────────────────────────────┐
│  Firestore has NO inverted index               │
│                                                 │
│  It must scan documents sequentially:          │
│  Doc 1 → check title → no match                │
│  Doc 2 → check title → no match                │
│  Doc 3 → check title → MATCH                   │
│  ...                                           │
│  Doc 100,000 → check title → no match          │
│                                                 │
│  O(n) complexity - gets worse with more data   │
└─────────────────────────────────────────────────┘
```

**Firestore limitations:**
- No native full-text search
- `where` only supports exact matches, `>=`, `<=`, `array-contains`
- Can't search "contains" or "like" efficiently
- Compound queries require composite indexes (and you hit index limits)
- Read costs scale with result set size

## How Elasticsearch Solves This

Elasticsearch uses an **inverted index** - it pre-processes text and maps terms to documents:

```
Term          → Documents
"domain"      → [doc1, doc5, doc12]
"driven"      → [doc1, doc5]
"design"      → [doc1, doc3, doc8, doc12]
"architecture"→ [doc2, doc7, doc15, doc23]
```

When you search for "architecture":
1. Look up term in index → O(1)
2. Get document IDs → [doc2, doc7, doc15, doc23]
3. Fetch and rank documents → O(k) where k = matches

No scanning required.

## CQRS Pattern: Right Tool for Each Job

```
                    ┌─────────────────┐
                    │   PostgreSQL    │
                    │                 │
Writes ───────────→ │  • Point reads  │ ← Simple reads
                    │  • Range queries│
                    └─────────────────┘
                            │
                         sync
                            ▼
                    ┌─────────────────┐
Searches ─────────→ │  Elasticsearch  │
                    │                 │
                    │  • Full-text    │
                    │  • Fuzzy match  │
                    │  • Aggregations │
                    └─────────────────┘
```

### PostgreSQL Handles

```sql
-- Point lookup (O(1))
SELECT * FROM books WHERE id = 'abc';

-- Range query (O(log n))
SELECT * FROM books WHERE created_at > '2024-01-01';

-- Simple filter (O(log n) with index)
SELECT * FROM books WHERE author_id = 'xyz';
```

### Elasticsearch Handles

```json
// Full-text search
{ "query": { "match": { "title": "software architecture" } } }

// Fuzzy matching (typo tolerance)
{ "query": { "fuzzy": { "title": "architekture" } } }

// Aggregations
{ "aggs": { "by_author": { "terms": { "field": "author" } } } }

// Complex boolean queries
{
  "query": {
    "bool": {
      "must": { "match": { "title": "architecture" } },
      "filter": { "term": { "available": true } },
      "should": { "match": { "description": "patterns" } }
    }
  }
}
```

## Decision Matrix

| Query Type | Use PostgreSQL | Use Elasticsearch |
|------------|----------------|-------------------|
| Get by ID | Yes | No |
| Get by foreign key | Yes | Maybe |
| Date range filter | Yes | Maybe |
| Full-text search | No | Yes |
| Autocomplete | No | Yes |
| Typo tolerance | No | Yes |
| Relevance ranking | No | Yes |
| Faceted search | No | Yes |
| Complex aggregations | Maybe | Yes |

## The Fix for Firestore-Like Databases

```
┌──────────────┐  writes   ┌──────────────┐
│   Firestore  │ ────────→ │ Cloud        │
│   (primary)  │  trigger  │ Function     │
└──────────────┘           └──────┬───────┘
                                  │ index
                                  ▼
┌──────────────┐  search   ┌──────────────┐
│     App      │ ←───────→ │Elasticsearch │
│              │           │  (Algolia)   │
└──────────────┘           └──────────────┘
```

**Common solutions:**
1. **Algolia** - Managed search, easy Firebase integration
2. **Elasticsearch** - Self-hosted, more control
3. **Typesense** - Open-source Algolia alternative
4. **Meilisearch** - Fast, simple to deploy

## Key Takeaway

Simple reads can stay on the write database, but complex searches benefit from a dedicated read model optimized for that access pattern. This is the essence of CQRS - use the right tool for each type of operation.
