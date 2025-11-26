# Context Map - Library Management System

## Overview

This document describes the bounded contexts in our library system and how they relate to each other. Understanding these relationships is crucial for maintaining clean boundaries and managing dependencies.

## What is a Context Map?

A Context Map is a DDD strategic pattern that visually documents:
1. The bounded contexts in a system
2. The relationships between them
3. How they communicate and integrate

## Bounded Contexts

### 1. Catalog Context (Supporting)
**Purpose:** Manages the library's book catalog - bibliographic records.

**Key Concepts:**
- `CatalogBook` - A bibliographic record (title, author, ISBN)
- `CatalogBookId` - Unique identifier shared with other contexts
- `Title`, `Author`, `ISBN` - Value objects

**Responsibilities:**
- Adding books to the catalog
- Managing book metadata
- Removing books from the catalog

**Does NOT know about:**
- Whether a book is borrowed
- Who has borrowed it
- Due dates or loans

---

### 2. Patron Context (Supporting)
**Purpose:** Manages library members (patrons).

**Key Concepts:**
- `Patron` - A library member
- `PatronId` - Unique identifier shared with other contexts
- `MembershipTier` - Determines borrowing privileges
- `EmailAddress` - Contact information (from Shared Kernel)

**Responsibilities:**
- Member registration
- Managing membership tiers
- Suspending/reinstating members

**Does NOT know about:**
- Specific loans or borrowed books
- Due dates

---

### 3. Lending Context (Core Domain)
**Purpose:** The heart of the library - managing book loans.

**Key Concepts:**
- `Loan` - A book being borrowed by a patron
- `LoanableBook` - Lending's view of a book (availability focused)
- `DueDate` - When the book must be returned
- `BorrowerInfo` - Lending's view of a patron (ACL translation)
- `BookReference` - Lending's view of catalog data (ACL translation)

**Responsibilities:**
- Creating and managing loans
- Tracking due dates
- Handling returns
- Managing overdue items

**Dependencies:**
- References `CatalogBookId` from Catalog
- References `PatronId` from Patron
- Uses ACL to translate upstream data

---

### 4. Notification Context (Generic Subdomain)
**Purpose:** Handles all outbound communications.

**Key Concepts:**
- Email notifications
- Templates
- Delivery tracking

**Responsibilities:**
- Sending email notifications
- Managing templates
- Logging delivery status

---

## Context Relationships

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌──────────────┐         ┌──────────────┐                         │
│  │   Catalog    │         │    Patron    │                         │
│  │   Context    │         │   Context    │                         │
│  │              │         │              │                         │
│  │ (Upstream)   │         │ (Upstream)   │                         │
│  └──────┬───────┘         └──────┬───────┘                         │
│         │                        │                                  │
│         │ Published              │ Customer-                        │
│         │ Language               │ Supplier                         │
│         │ (Events)               │                                  │
│         ▼                        ▼                                  │
│  ┌──────────────────────────────────────────────┐                  │
│  │                                              │                  │
│  │              Lending Context                 │                  │
│  │              (Core Domain)                   │                  │
│  │                                              │                  │
│  │  ┌─────────────────────────────────────┐   │                  │
│  │  │     Anti-Corruption Layer (ACL)     │   │                  │
│  │  │  ┌─────────────┐ ┌─────────────┐   │   │                  │
│  │  │  │ CatalogACL  │ │ PatronACL   │   │   │                  │
│  │  │  └─────────────┘ └─────────────┘   │   │                  │
│  │  └─────────────────────────────────────┘   │                  │
│  │                                              │                  │
│  └──────────────────┬───────────────────────────┘                  │
│                     │                                               │
│                     │ Published Language                            │
│                     │ (Domain Events)                               │
│                     ▼                                               │
│  ┌──────────────────────────────────────────────┐                  │
│  │           Notification Context               │                  │
│  │           (Generic Subdomain)                │                  │
│  │                                              │                  │
│  │   Subscribes to:                             │                  │
│  │   - BookBorrowed                             │                  │
│  │   - BookOverdue                              │                  │
│  │   - BookReturned                             │                  │
│  └──────────────────────────────────────────────┘                  │
│                                                                     │
│  ┌──────────────────────────────────────────────┐                  │
│  │              Shared Kernel                   │                  │
│  │                                              │                  │
│  │   - AggregateRoot                            │                  │
│  │   - DomainEvent                              │                  │
│  │   - EmailAddress                             │                  │
│  └──────────────────────────────────────────────┘                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Relationship Types Explained

### 1. Published Language (Catalog → Lending)
**Pattern:** Open Host Service with Published Language

The Catalog context publishes events (`BookAddedToCatalog`, `BookRemovedFromCatalog`) that other contexts can subscribe to. The event schema is the "published language" - a contract that Catalog commits to maintaining.

```python
# Catalog publishes this event
@dataclass(frozen=True)
class BookAddedToCatalog(DomainEvent):
    book_id: str
    title: str
    author: str

# Lending subscribes and creates its own LoanableBook
```

### 2. Customer-Supplier (Patron → Lending)
**Pattern:** Customer-Supplier

Lending (downstream/customer) depends on Patron (upstream/supplier) for borrower information. The Patron context agrees to provide what Lending needs.

The ACL translates Patron's model to Lending's:
```python
# Patron's model
class Patron:
    name: PatronName
    membership_tier: MembershipTier

# Lending's view (via ACL)
@dataclass
class BorrowerInfo:
    name: str
    borrowing_limit: int
    loan_duration_days: int
```

### 3. Anti-Corruption Layer (Lending)
**Pattern:** ACL

Lending uses an Anti-Corruption Layer to protect itself from changes in upstream contexts. If Catalog or Patron change their models, only the ACL implementation needs updating.

```python
# ACL Interface (in domain)
class PatronACL(Protocol):
    async def get_borrower_info(self, patron_id: str) -> Optional[BorrowerInfo]:
        ...

# ACL Implementation (in infrastructure)
class PatronACLAdapter:
    def __init__(self, patron_repository: PatronRepository):
        self.patron_repo = patron_repository

    async def get_borrower_info(self, patron_id: str) -> Optional[BorrowerInfo]:
        patron = await self.patron_repo.get_by_id(patron_id)
        if not patron:
            return None
        # Translate Patron's model to Lending's BorrowerInfo
        return BorrowerInfo(
            patron_id=patron.id.value,
            email=patron.email.value,
            name=patron.name.full_name,
            can_borrow=patron.can_borrow(current_loans),
            borrowing_limit=patron.membership_tier.borrowing_limit,
            loan_duration_days=patron.membership_tier.loan_duration_days,
        )
```

### 4. Shared Kernel
**Pattern:** Shared Kernel

Some types are shared across all contexts by agreement. Changes to the shared kernel require coordination between all teams.

Shared types:
- `AggregateRoot` - Base class for all aggregates
- `DomainEvent` - Base class for all events
- `EmailAddress` - Used by Patron and Notification

## Event Flow Example: Borrowing a Book

```
1. API receives borrow request
   └─→ BorrowBook use case (Lending context)

2. Lending calls PatronACL.get_borrower_info(patron_id)
   └─→ ACL fetches from Patron context
   └─→ ACL translates to BorrowerInfo

3. Lending calls CatalogACL.get_book_reference(book_id)
   └─→ ACL fetches from Catalog context
   └─→ ACL translates to BookReference

4. Lending creates Loan aggregate
   └─→ Loan.create() raises BookBorrowed event

5. Unit of Work commits transaction
   └─→ Dispatches BookBorrowed event to message broker

6. Notification context receives BookBorrowed
   └─→ Sends confirmation email to patron
```

## Benefits of This Design

1. **Isolation:** Each context can evolve independently
2. **Clear ownership:** Each team owns their context
3. **Explicit dependencies:** ACL makes dependencies visible
4. **Flexible integration:** Events enable loose coupling
5. **Focused models:** Each context has its optimized model

## Guidelines for Future Development

1. **New features in Lending?** Keep them within the Lending context
2. **Need Patron data in Lending?** Add to PatronACL, not direct access
3. **New context needed?** Define relationships in this map first
4. **Changing shared kernel?** Coordinate with all context owners
