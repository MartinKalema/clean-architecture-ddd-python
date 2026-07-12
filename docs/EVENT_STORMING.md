# Event Storming Artifacts

## Library Domain Model

This document contains the Event Storming artifacts and domain model diagrams for the Library system.

---

## Table of Contents

1. [Event Storming Legend](#event-storming-legend)
2. [Big Picture Event Storming](#big-picture-event-storming)
3. [Process Level: Borrowing Flow](#process-level-borrowing-flow)
4. [Process Level: Return Flow](#process-level-return-flow)
5. [Process Level: Hold Flow](#process-level-hold-flow)
6. [Aggregate Diagrams](#aggregate-diagrams)
7. [Domain Model Diagram](#domain-model-diagram)
8. [Context Map Diagram](#context-map-diagram)

---

## Event Storming Legend

```
┌─────────────────────────────────────────────────────────────────┐
│                    EVENT STORMING COLORS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐                                               │
│  │   ORANGE     │  DOMAIN EVENT                                 │
│  │              │  Something that happened (past tense)         │
│  │ BookBorrowed │  "BookBorrowed", "FineIssued"                │
│  └──────────────┘                                               │
│                                                                  │
│  ┌──────────────┐                                               │
│  │    BLUE      │  COMMAND                                      │
│  │              │  Action that triggers event (imperative)      │
│  │ Borrow Book  │  "Borrow Book", "Return Book"                │
│  └──────────────┘                                               │
│                                                                  │
│  ┌──────────────┐                                               │
│  │   YELLOW     │  AGGREGATE                                    │
│  │              │  Entity cluster that processes command        │
│  │    Loan      │  "Book", "Loan", "Patron"                    │
│  └──────────────┘                                               │
│                                                                  │
│  ┌──────────────┐                                               │
│  │   PURPLE     │  POLICY / PROCESS MANAGER                     │
│  │              │  "When X happens, do Y"                       │
│  │  When overdue│  Reactive business logic                      │
│  │  issue fine  │                                               │
│  └──────────────┘                                               │
│                                                                  │
│  ┌──────────────┐                                               │
│  │    PINK      │  EXTERNAL SYSTEM                              │
│  │              │  Outside the domain boundary                  │
│  │   Stripe     │  "Payment Gateway", "Email Service"          │
│  └──────────────┘                                               │
│                                                                  │
│  ┌──────────────┐                                               │
│  │   GREEN      │  READ MODEL / QUERY                           │
│  │              │  Data needed to make decisions                │
│  │ Patron       │  "Available Books", "Patron Status"          │
│  │ Profile      │                                               │
│  └──────────────┘                                               │
│                                                                  │
│  ┌──────────────┐                                               │
│  │    RED       │  HOT SPOT / PROBLEM                           │
│  │              │  Needs clarification or has conflict          │
│  │      ?       │  Questions, disagreements                     │
│  └──────────────┘                                               │
│                                                                  │
│       ○          ACTOR                                          │
│      /|\         Person or system initiating action             │
│      / \         "Patron", "Librarian", "System"               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Big Picture Event Storming

### Timeline of Domain Events

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              LIBRARY DOMAIN - BIG PICTURE                                │
│                                                                                          │
│  TIME ──────────────────────────────────────────────────────────────────────────────▶   │
│                                                                                          │
│  ┌─────────────┐                                                                        │
│  │ ACQUISITION │                                                                        │
│  └─────────────┘                                                                        │
│        │                                                                                │
│        ▼                                                                                │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐                                         │
│  │   Book    │   │   Book    │   │   Book    │                                         │
│  │ Ordered   │──▶│ Received  │──▶│  Added    │                                         │
│  │           │   │           │   │to Catalog │                                         │
│  └───────────┘   └───────────┘   └─────┬─────┘                                         │
│                                        │                                                │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  ┌─────────────┐                       │                                                │
│  │   PATRON    │                       │                                                │
│  └─────────────┘                       │                                                │
│        │                               │                                                │
│        ▼                               │                                                │
│  ┌───────────┐   ┌───────────┐        │                                                │
│  │  Patron   │   │  Patron   │        │                                                │
│  │Registered │──▶│ Verified  │        │                                                │
│  │           │   │           │        │                                                │
│  └─────┬─────┘   └───────────┘        │                                                │
│        │                               │                                                │
│  ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  ┌─────┴───────┐                       │                                                │
│  │   LENDING   │◀──────────────────────┘                                                │
│  └─────────────┘                                                                        │
│        │                                                                                │
│        ▼                                                                                │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐        │
│  │   Book    │   │   Loan    │   │   Loan    │   │   Loan    │   │   Book    │        │
│  │ Borrowed  │──▶│  Active   │──▶│  Became   │──▶│  Renewed  │──▶│ Returned  │        │
│  │           │   │           │   │  Overdue  │   │    OR     │   │           │        │
│  └───────────┘   └───────────┘   └─────┬─────┘   └───────────┘   └─────┬─────┘        │
│                                        │                               │                │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─  │
│  ┌─────────────┐                       │                               │                │
│  │    FINES    │◀──────────────────────┴───────────────────────────────┘                │
│  └─────────────┘                                                                        │
│        │                                                                                │
│        ▼                                                                                │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐                         │
│  │   Fine    │   │  Patron   │   │   Fine    │   │  Patron   │                         │
│  │  Issued   │──▶│ Suspended │──▶│   Paid    │──▶│Reinstated │                         │
│  │           │   │           │   │           │   │           │                         │
│  └───────────┘   └───────────┘   └───────────┘   └───────────┘                         │
│                                                                                          │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  ┌─────────────┐                                                                        │
│  │    HOLDS    │                                                                        │
│  └─────────────┘                                                                        │
│        │                                                                                │
│        ▼                                                                                │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐                         │
│  │   Hold    │   │   Hold    │   │   Hold    │   │   Hold    │                         │
│  │  Placed   │──▶│Ready for  │──▶│ Fulfilled │   │  Expired  │                         │
│  │           │   │  Pickup   │   │    OR     │   │    OR     │                         │
│  └───────────┘   └───────────┘   └───────────┘   └───────────┘                         │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Process Level: Borrowing Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              BORROW BOOK PROCESS                                         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│     ○                                                                                    │
│    /|\   Patron                                                                         │
│    / \                                                                                   │
│     │                                                                                    │
│     │ wants to borrow                                                                   │
│     ▼                                                                                    │
│  ┌──────────────┐                                                                       │
│  │              │                                                                       │
│  │ Borrow Book  │ ◀─────── COMMAND                                                     │
│  │              │                                                                       │
│  └──────┬───────┘                                                                       │
│         │                                                                               │
│         │ needs                                                                         │
│         ▼                                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                              │
│  │   Patron     │    │    Book      │    │   Patron     │                              │
│  │   Status     │    │ Availability │    │   Loans      │ ◀─── READ MODELS            │
│  │  (active?)   │    │ (in stock?)  │    │   (< max?)   │                              │
│  └──────────────┘    └──────────────┘    └──────────────┘                              │
│         │                   │                   │                                       │
│         └───────────────────┴───────────────────┘                                       │
│                             │                                                           │
│                             ▼                                                           │
│                    ┌──────────────┐                                                     │
│                    │              │                                                     │
│                    │     Loan     │ ◀─────── AGGREGATE                                 │
│                    │              │                                                     │
│                    └──────┬───────┘                                                     │
│                           │                                                             │
│                           │ produces                                                    │
│                           ▼                                                             │
│                    ┌──────────────┐                                                     │
│                    │              │                                                     │
│                    │BookBorrowed  │ ◀─────── DOMAIN EVENT                              │
│                    │              │                                                     │
│                    └──────┬───────┘                                                     │
│                           │                                                             │
│              ┌────────────┼────────────┐                                               │
│              │            │            │                                               │
│              ▼            ▼            ▼                                               │
│       ┌────────────┐ ┌────────────┐ ┌────────────┐                                     │
│       │  Update    │ │   Send     │ │  Fulfill   │                                     │
│       │   Book     │ │   Email    │ │   Hold     │ ◀─── POLICIES                       │
│       │Availability│ │Notification│ │ (if any)   │                                     │
│       └────────────┘ └─────┬──────┘ └────────────┘                                     │
│                            │                                                            │
│                            ▼                                                            │
│                     ┌────────────┐                                                      │
│                     │  SendGrid  │ ◀─────── EXTERNAL SYSTEM                            │
│                     │            │                                                      │
│                     └────────────┘                                                      │
│                                                                                          │
│  BUSINESS RULES:                                                                        │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  • Patron must be ACTIVE (not suspended)                                                │
│  • Book must be AVAILABLE                                                               │
│  • Patron current loans < borrowing limit                                               │
│  • Loan period: 14 days (standard), 30 days (researcher)                               │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Process Level: Return Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              RETURN BOOK PROCESS                                         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│     ○                                                                                    │
│    /|\   Patron                                                                         │
│    / \                                                                                   │
│     │                                                                                    │
│     │ returns book                                                                      │
│     ▼                                                                                    │
│  ┌──────────────┐                                                                       │
│  │              │                                                                       │
│  │ Return Book  │ ◀─────── COMMAND                                                     │
│  │              │                                                                       │
│  └──────┬───────┘                                                                       │
│         │                                                                               │
│         │ needs                                                                         │
│         ▼                                                                               │
│  ┌──────────────┐    ┌──────────────┐                                                  │
│  │    Loan      │    │   Current    │                                                  │
│  │   Details    │    │    Date      │ ◀─────── READ MODELS                             │
│  │              │    │              │                                                  │
│  └──────────────┘    └──────────────┘                                                  │
│         │                   │                                                           │
│         └─────────┬─────────┘                                                           │
│                   │                                                                     │
│                   ▼                                                                     │
│          ┌──────────────┐                                                               │
│          │              │                                                               │
│          │     Loan     │ ◀─────── AGGREGATE                                           │
│          │              │                                                               │
│          └──────┬───────┘                                                               │
│                 │                                                                       │
│                 │ produces                                                              │
│                 ▼                                                                       │
│          ┌──────────────┐                                                               │
│          │              │                                                               │
│          │BookReturned  │ ◀─────── DOMAIN EVENT                                        │
│          │{wasOverdue}  │                                                               │
│          └──────┬───────┘                                                               │
│                 │                                                                       │
│     ┌───────────┴───────────┐                                                          │
│     │                       │                                                          │
│     ▼                       ▼                                                          │
│  ┌──────────────┐    ┌─────────────────────────┐                                       │
│  │   Update     │    │    When wasOverdue      │                                       │
│  │    Book      │    │    ─────────────────    │                                       │
│  │ Availability │    │                         │ ◀─── POLICY                           │
│  └──────────────┘    │  ┌──────────────────┐  │                                       │
│         │            │  │  Calculate Fine   │  │                                       │
│         │            │  │                   │  │                                       │
│         ▼            │  └────────┬──────────┘  │                                       │
│  ┌──────────────┐    │           │             │                                       │
│  │   Notify     │    │           ▼             │                                       │
│  │ Next Patron  │    │  ┌──────────────────┐  │                                       │
│  │  in Hold Q   │    │  │       Fine       │  │ ◀─── AGGREGATE                        │
│  └──────────────┘    │  │                   │  │                                       │
│                      │  └────────┬──────────┘  │                                       │
│                      │           │             │                                       │
│                      │           ▼             │                                       │
│                      │  ┌──────────────────┐  │                                       │
│                      │  │   FineIssued     │  │ ◀─── EVENT                            │
│                      │  │                   │  │                                       │
│                      │  └──────────────────┘  │                                       │
│                      └─────────────────────────┘                                       │
│                                                                                          │
│  BUSINESS RULES:                                                                        │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  • Fine = $0.25/day overdue (books), $1.00/day (DVDs)                                  │
│  • Maximum fine capped at item replacement cost                                         │
│  • If total fines > $25, suspend patron                                                │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Process Level: Hold Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                               HOLD BOOK PROCESS                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  PLACE HOLD                                                                              │
│  ──────────                                                                              │
│     ○                                                                                    │
│    /|\   Patron                                                                         │
│    / \                                                                                   │
│     │                                                                                    │
│     ▼                                                                                    │
│  ┌────────────┐     ┌────────────┐     ┌────────────┐                                   │
│  │   Place    │────▶│    Hold    │────▶│   Hold     │                                   │
│  │   Hold     │     │            │     │  Placed    │                                   │
│  └────────────┘     └────────────┘     └────────────┘                                   │
│    COMMAND           AGGREGATE           EVENT                                          │
│                                                                                          │
│                                                                                          │
│  WHEN BOOK RETURNED (Policy)                                                            │
│  ────────────────────────────                                                           │
│                                                                                          │
│  ┌────────────┐                                                                         │
│  │   Book     │                                                                         │
│  │ Returned   │                                                                         │
│  └─────┬──────┘                                                                         │
│        │                                                                                │
│        ▼                                                                                │
│  ┌──────────────────────────┐                                                           │
│  │   Check Hold Queue       │                                                           │
│  │   ──────────────────     │                                                           │
│  │   Is there a hold        │                                                           │
│  │   for this book?         │                                                           │
│  └────────────┬─────────────┘                                                           │
│               │                                                                         │
│       ┌───────┴───────┐                                                                 │
│       │               │                                                                 │
│      YES              NO                                                                │
│       │               │                                                                 │
│       ▼               ▼                                                                 │
│  ┌──────────┐   ┌──────────┐                                                            │
│  │  Notify  │   │  Mark    │                                                            │
│  │  Patron  │   │Available │                                                            │
│  └────┬─────┘   └──────────┘                                                            │
│       │                                                                                 │
│       ▼                                                                                 │
│  ┌──────────────┐                                                                       │
│  │ HoldReady    │                                                                       │
│  │ ForPickup    │                                                                       │
│  └──────────────┘                                                                       │
│       EVENT                                                                             │
│                                                                                          │
│                                                                                          │
│  HOLD EXPIRATION (Scheduled Policy)                                                     │
│  ──────────────────────────────────                                                     │
│                                                                                          │
│  ┌────────────┐     ┌────────────┐     ┌────────────┐                                   │
│  │  Daily     │────▶│   Check    │────▶│   Hold     │                                   │
│  │  Scheduler │     │   Expiry   │     │  Expired   │                                   │
│  └────────────┘     └────────────┘     └────────────┘                                   │
│                                              │                                          │
│                                              ▼                                          │
│                                       ┌────────────┐                                    │
│                                       │   Notify   │                                    │
│                                       │   Next in  │                                    │
│                                       │   Queue    │                                    │
│                                       └────────────┘                                    │
│                                                                                          │
│  BUSINESS RULES:                                                                        │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  • Hold pickup window: 7 days                                                           │
│  • Maximum holds per patron: 10                                                         │
│  • Hold queue: FIFO (first come, first served)                                         │
│  • Patron notified via email when hold is ready                                        │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Aggregate Diagrams

### Book Aggregate (Catalog Context)

```
┌─────────────────────────────────────────────────────────────────┐
│                    BOOK AGGREGATE                                │
│                   (Catalog Context)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 Book (Aggregate Root)                    │    │
│  ├─────────────────────────────────────────────────────────┤    │
│  │  - id: BookId                                           │    │
│  │  - title: Title                                         │    │
│  │  - author: Author                                       │    │
│  │  - isbn: ISBN (optional)                                │    │
│  │  - publisher: String                                    │    │
│  │  - publicationYear: Int                                 │    │
│  │  - subjects: List<Subject>                              │    │
│  │  - description: String                                  │    │
│  │  - version: Int                                         │    │
│  ├─────────────────────────────────────────────────────────┤    │
│  │  + addToCatalog()                                       │    │
│  │  + updateDetails(...)                                   │    │
│  │  + removeFromCatalog(reason)                            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│           ┌───────────────┼───────────────┐                     │
│           │               │               │                     │
│           ▼               ▼               ▼                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   BookId    │  │    Title    │  │   Author    │              │
│  │   (Value)   │  │   (Value)   │  │   (Value)   │              │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤              │
│  │ value: UUID │  │ value: Str  │  │ value: Str  │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│                                                                  │
│  INVARIANTS:                                                     │
│  • Title cannot be empty                                         │
│  • Author cannot be empty                                        │
│  • ISBN must be valid format (10 or 13 digits) if provided      │
│                                                                  │
│  EVENTS PRODUCED:                                                │
│  • BookAddedToCatalog                                            │
│  • BookDetailsUpdated                                            │
│  • BookRemovedFromCatalog                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Loan Aggregate (Lending Context)

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOAN AGGREGATE                                │
│                   (Lending Context)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 Loan (Aggregate Root)                    │    │
│  ├─────────────────────────────────────────────────────────┤    │
│  │  - id: LoanId                                           │    │
│  │  - bookId: BookId (reference)                           │    │
│  │  - patronId: PatronId (reference)                       │    │
│  │  - borrowedAt: DateTime                                 │    │
│  │  - dueDate: DateTime                                    │    │
│  │  - returnedAt: DateTime (optional)                      │    │
│  │  - renewalCount: Int                                    │    │
│  │  - status: LoanStatus                                   │    │
│  │  - version: Int                                         │    │
│  ├─────────────────────────────────────────────────────────┤    │
│  │  + create(bookId, patronId, loanPeriod)                 │    │
│  │  + renew(): Result                                      │    │
│  │  + markOverdue()                                        │    │
│  │  + return(): DaysOverdue                                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│           ┌───────────────┼───────────────┐                     │
│           │               │               │                     │
│           ▼               ▼               ▼                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   LoanId    │  │ LoanPeriod  │  │ LoanStatus  │              │
│  │   (Value)   │  │   (Value)   │  │   (Enum)    │              │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤              │
│  │ value: UUID │  │ days: Int   │  │ ACTIVE      │              │
│  └─────────────┘  └─────────────┘  │ OVERDUE     │              │
│                                    │ RETURNED    │              │
│                                    └─────────────┘              │
│                                                                  │
│  INVARIANTS:                                                     │
│  • Cannot renew if status is RETURNED                            │
│  • Cannot renew more than 3 times                                │
│  • Cannot renew if holds exist for this book                     │
│  • DueDate must be after BorrowedAt                              │
│                                                                  │
│  EVENTS PRODUCED:                                                │
│  • BookBorrowed                                                  │
│  • LoanRenewed                                                   │
│  • LoanBecameOverdue                                             │
│  • BookReturned                                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Patron Aggregate (Patron Context)

```
┌─────────────────────────────────────────────────────────────────┐
│                   PATRON AGGREGATE                               │
│                   (Patron Context)                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                Patron (Aggregate Root)                   │    │
│  ├─────────────────────────────────────────────────────────┤    │
│  │  - id: PatronId                                         │    │
│  │  - name: Name                                           │    │
│  │  - email: EmailAddress                                  │    │
│  │  - membershipTier: MembershipTier                       │    │
│  │  - status: PatronStatus                                 │    │
│  │  - contactInfo: ContactInfo                             │    │
│  │  - registeredAt: DateTime                               │    │
│  │  - version: Int                                         │    │
│  ├─────────────────────────────────────────────────────────┤    │
│  │  + register(name, email, tier)                          │    │
│  │  + suspend(reason)                                      │    │
│  │  + reinstate()                                          │    │
│  │  + upgradeTier(newTier)                                 │    │
│  │  + getBorrowingLimit(): Int                             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│           ┌───────────────┼───────────────┐                     │
│           │               │               │                     │
│           ▼               ▼               ▼                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │MembershipTier │EmailAddress │  │PatronStatus │              │
│  │   (Enum)    │  │   (Value)   │  │   (Enum)    │              │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤              │
│  │ STANDARD    │  │ value: Str  │  │ ACTIVE      │              │
│  │ PREMIUM     │  │             │  │ SUSPENDED   │              │
│  │ RESEARCHER  │  │ validate()  │  │ EXPIRED     │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│                                                                  │
│  BORROWING LIMITS BY TIER:                                       │
│  • STANDARD: 5 books, 14-day loan                                │
│  • PREMIUM: 10 books, 21-day loan                                │
│  • RESEARCHER: 20 books, 30-day loan                             │
│                                                                  │
│  EVENTS PRODUCED:                                                │
│  • PatronRegistered                                              │
│  • PatronSuspended                                               │
│  • PatronReinstated                                              │
│  • MembershipTierChanged                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Domain Model Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              LIBRARY DOMAIN MODEL                                        │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                              CATALOG CONTEXT                                     │    │
│  │  ┌──────────────────┐                                                           │    │
│  │  │      Book        │                                                           │    │
│  │  │  «aggregate»     │                                                           │    │
│  │  ├──────────────────┤                                                           │    │
│  │  │ id: BookId       │                                                           │    │
│  │  │ title: Title     │                                                           │    │
│  │  │ author: Author   │                                                           │    │
│  │  │ isbn: ISBN       │                                                           │    │
│  │  └──────────────────┘                                                           │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
│                    │                                                                     │
│                    │ BookAddedToCatalog                                                 │
│                    ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                              LENDING CONTEXT                                     │    │
│  │                                                                                  │    │
│  │                              ┌──────────────────┐                              │    │
│  │                              │      Loan        │                              │    │
│  │                              │  «aggregate»     │                              │    │
│  │                              ├──────────────────┤                              │    │
│  │                              │ id: LoanId       │                              │    │
│  │                              │ bookId           │                              │    │
│  │                              │ reservationId    │                              │    │
│  │                              │ patronId         │                              │    │
│  │                              │ borrowedAt       │                              │    │
│  │                              │ dueDate          │                              │    │
│  │                              │ status           │                              │    │
│  │                              └──────────────────┘                              │    │
│  │                                      │                                        │    │
│  │                                      ▼                                        │    │
│  │  ┌──────────────────┐                  │                                        │    │
│  │  │      Hold        │                  │                                        │    │
│  │  │  «aggregate»     │                  │ BookBorrowed                           │    │
│  │  ├──────────────────┤                  │ BookReturned                           │    │
│  │  │ id: HoldId       │                  │ LoanBecameOverdue                      │    │
│  │  │ patronId         │                  ▼                                        │    │
│  │  │ bookId           │                                                           │    │
│  │  │ status           │                                                           │    │
│  │  └──────────────────┘                                                           │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
│                    │                                                                     │
│                    │ LoanBecameOverdue                                                  │
│                    ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                               FINES CONTEXT                                      │    │
│  │                                                                                  │    │
│  │  ┌──────────────────┐         ┌──────────────────┐                              │    │
│  │  │      Fine        │         │    Payment       │                              │    │
│  │  │  «aggregate»     │────────▶│    «entity»      │                              │    │
│  │  ├──────────────────┤  0..*   ├──────────────────┤                              │    │
│  │  │ id: FineId       │         │ id: PaymentId    │                              │    │
│  │  │ loanId           │         │ amount: Money    │                              │    │
│  │  │ patronId         │         │ paidAt           │                              │    │
│  │  │ amount: Money    │         │ method           │                              │    │
│  │  │ status           │         └──────────────────┘                              │    │
│  │  └──────────────────┘                                                           │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                              PATRON CONTEXT                                      │    │
│  │  ┌──────────────────┐                                                           │    │
│  │  │     Patron       │                                                           │    │
│  │  │  «aggregate»     │                                                           │    │
│  │  ├──────────────────┤                                                           │    │
│  │  │ id: PatronId     │                                                           │    │
│  │  │ name             │                                                           │    │
│  │  │ email            │                                                           │    │
│  │  │ membershipTier   │                                                           │    │
│  │  │ status           │                                                           │    │
│  │  │ borrowingLimit   │                                                           │    │
│  │  └──────────────────┘                                                           │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Context Map Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              CONTEXT MAP                                                 │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│                         ┌─────────────────────┐                                         │
│                         │    SHARED KERNEL    │                                         │
│                         │  ─────────────────  │                                         │
│                         │  • AggregateRoot    │                                         │
│                         │  • DomainEvent      │                                         │
│                         │  • Money            │                                         │
│                         │  • EmailAddress     │                                         │
│                         └──────────┬──────────┘                                         │
│                                    │                                                    │
│          ┌─────────────────────────┼─────────────────────────┐                         │
│          │                         │                         │                         │
│          ▼                         ▼                         ▼                         │
│  ┌───────────────┐        ┌───────────────┐        ┌───────────────┐                   │
│  │   CATALOG     │        │    PATRON     │        │   LENDING     │                   │
│  │   CONTEXT     │        │   CONTEXT     │        │   CONTEXT     │                   │
│  │               │        │               │        │               │                   │
│  │ Team: 3 devs  │        │ Team: 2 devs  │        │ Team: 5 devs  │                   │
│  │               │        │               │        │  (CORE)       │                   │
│  └───────┬───────┘        └───────┬───────┘        └───────┬───────┘                   │
│          │                        │                        │                           │
│          │                        │                        │                           │
│          │    Published           │   Customer             │                           │
│          │    Language            │   Supplier             │                           │
│          │         │              │      │                 │                           │
│          │         ▼              ▼      │                 │                           │
│          │    ┌─────────────────────┐    │                 │                           │
│          └───▶│      LENDING        │◀───┘                 │                           │
│               │      CONTEXT        │                      │                           │
│               │                     │                      │                           │
│               │  Subscribes to:     │                      │                           │
│               │  • BookAddedToCatalog                      │                           │
│               │                     │                      │                           │
│               │  Queries:           │                      │                           │
│               │  • PatronBorrowProfile                     │                           │
│               └──────────┬──────────┘                      │                           │
│                          │                                 │                           │
│                          │ Customer-Supplier               │                           │
│                          │ (Events)                        │                           │
│                          │                                 │                           │
│                          ▼                                 │                           │
│               ┌─────────────────────┐                      │                           │
│               │      FINES          │                      │                           │
│               │      CONTEXT        │                      │                           │
│               │                     │                      │                           │
│               │  Subscribes to:     │                      │                           │
│               │  • LoanBecameOverdue│                      │                           │
│               │  • BookReturned     │                      │                           │
│               └──────────┬──────────┘                      │                           │
│                          │                                 │                           │
│                          │ ACL                             │                           │
│                          │                                 │                           │
│                          ▼                                 │                           │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                           EXTERNAL SYSTEMS                                       │   │
│  │                                                                                  │   │
│  │   ┌────────────┐      ┌────────────┐      ┌────────────┐      ┌────────────┐    │   │
│  │   │  Payment   │      │   Email    │      │  Identity  │      │   Search   │    │   │
│  │   │  Gateway   │      │  Service   │      │  Provider  │      │   Engine   │    │   │
│  │   │  (Stripe)  │      │ (SendGrid) │      │  (Auth0)   │      │(Elasticsearch)  │   │
│  │   └────────────┘      └────────────┘      └────────────┘      └────────────┘    │   │
│  │                                                                                  │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
│  LEGEND:                                                                                │
│  ────────────────────────────────────────────────────────────────────────────────────   │
│                                                                                          │
│  ─────▶  Published Language (documented events/API)                                     │
│  ─ ─ ─▶  Customer-Supplier (downstream depends on upstream)                             │
│  ══════▶  ACL (translation layer to external system)                                    │
│  [SK]    Shared Kernel (shared code ownership)                                          │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary: Key Artifacts Checklist

| Artifact | Purpose | Created |
|----------|---------|---------|
| Domain Events List | All events in the system | ✅ |
| Event Timeline | Temporal flow of events | ✅ |
| Process Flows | Command → Aggregate → Event | ✅ |
| Aggregate Diagrams | Internal structure + invariants | ✅ |
| Domain Model | Relationships between aggregates | ✅ |
| Context Map | Bounded context relationships | ✅ |
| Ubiquitous Language | Glossary of terms | ✅ (separate doc) |

---

## How to Use These Artifacts

1. **Onboarding**: New team members read through to understand the domain
2. **Design Sessions**: Reference during feature planning
3. **Code Reviews**: Verify implementation matches model
4. **Refactoring**: Identify where boundaries should change
5. **Communication**: Share with stakeholders to validate understanding
