# Strategic Domain-Driven Design Guide

## For Staff & Distinguished Engineers

This document provides a framework for thinking about **Strategic DDD** - the high-level patterns that help you decompose complex domains into manageable bounded contexts with clear relationships.

---

## Table of Contents

1. [Strategic vs Tactical DDD](#strategic-vs-tactical-ddd)
2. [Understanding the Problem Space](#understanding-the-problem-space)
3. [Identifying Subdomains](#identifying-subdomains)
4. [Defining Bounded Contexts](#defining-bounded-contexts)
5. [Context Mapping](#context-mapping)
6. [Applied Example: Library System](#applied-example-library-system)
7. [Discovery Questions](#discovery-questions)
8. [Anti-Patterns to Avoid](#anti-patterns-to-avoid)

---

## Strategic vs Tactical DDD

### What You Did Well (Tactical DDD)

Tactical DDD focuses on **implementation patterns within a single bounded context**:

| Pattern | Purpose | Your Implementation |
|---------|---------|---------------------|
| Aggregates | Consistency boundaries | `Book` aggregate with borrowing rules |
| Value Objects | Immutable domain concepts | `BookId`, `Title`, `Author`, `ISBN` |
| Entities | Objects with identity | `Book` (identified by `BookId`) |
| Domain Events | Record state changes | `BookBorrowed`, `BookReturned` |
| Repositories | Persistence abstraction | `BookRepository` interface |
| Domain Services | Stateless operations | (Not needed yet in your domain) |

### What Was Missing (Strategic DDD)

Strategic DDD focuses on **how to divide a large domain into bounded contexts**:

| Concept | Purpose | Questions It Answers |
|---------|---------|----------------------|
| Subdomains | Problem space decomposition | What are the different business capabilities? |
| Bounded Contexts | Solution space boundaries | Where do we draw model boundaries? |
| Context Maps | Inter-context relationships | How do contexts communicate and depend on each other? |
| Ubiquitous Language | Shared vocabulary | What terms mean what, and where? |

---

## Understanding the Problem Space

Before writing any code, you must understand the **problem space** - the business domain itself, independent of any software solution.

### Step 1: Event Storming

Event Storming is a collaborative workshop technique. You identify:

```
1. DOMAIN EVENTS (orange) - Things that happen
   "Book was borrowed"
   "Book was returned"
   "Fine was issued"
   "Member registered"
   "Book was added to catalog"

2. COMMANDS (blue) - What triggers events
   "Borrow book"
   "Return book"
   "Register member"
   "Add book"

3. AGGREGATES (yellow) - What processes commands
   Book, Member, Loan, Fine

4. POLICIES (purple) - Reactions to events
   "When book is overdue, issue fine"
   "When fine exceeds $50, suspend member"

5. EXTERNAL SYSTEMS (pink) - Outside integrations
   Payment processor, Email service, ISBN lookup
```

### Step 2: Identify Pivotal Events

Pivotal events are **boundaries where the business process changes significantly**:

```
Library Domain Pivotal Events:
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Book Added to  │────▶│   Book         │────▶│   Book         │
│  Catalog        │     │   Borrowed     │     │   Returned     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
   [CATALOG]              [LENDING]               [LENDING]

Different teams care about different events.
Different rules apply in different contexts.
```

---

## Identifying Subdomains

Subdomains are **areas of the business** - they exist whether or not you build software.

### Types of Subdomains

```
┌─────────────────────────────────────────────────────────────────┐
│                         SUBDOMAINS                               │
├─────────────────┬─────────────────────┬─────────────────────────┤
│     CORE        │     SUPPORTING      │      GENERIC            │
├─────────────────┼─────────────────────┼─────────────────────────┤
│ Competitive     │ Necessary but not   │ Solved problems         │
│ advantage       │ differentiating     │ (buy/use existing)      │
├─────────────────┼─────────────────────┼─────────────────────────┤
│ • Lending       │ • Catalog Mgmt      │ • User Authentication   │
│ • Reservations  │ • Member Mgmt       │ • Payment Processing    │
│ • Recommendations│ • Notifications    │ • Email Delivery        │
│                 │ • Reporting         │ • Search                │
└─────────────────┴─────────────────────┴─────────────────────────┘

INVESTMENT STRATEGY:
- Core: Build custom, best engineers, iterate frequently
- Supporting: Build simple, adequate quality
- Generic: Buy/integrate, don't reinvent
```

### Questions to Identify Subdomains

1. **What would happen if this capability disappeared?**
   - Business stops → Core
   - Business slows → Supporting
   - Inconvenient → Generic

2. **Is this where we compete/differentiate?**
   - Yes → Core
   - No → Supporting or Generic

3. **Would another company in a different industry have the same need?**
   - Yes → Generic (authentication, payments, email)
   - No → Core or Supporting

### Library System Subdomains

```
CORE SUBDOMAINS (Competitive Advantage):
┌─────────────────────────────────────────────────────────────────┐
│ LENDING                                                          │
│ - The primary value proposition of a library                     │
│ - Complex rules: loan periods, renewals, holds, queues           │
│ - This is what makes YOUR library different from others          │
│ - Rules: "Members can borrow 5 books, researchers can borrow 20" │
│ - Rules: "Rare books require approval"                           │
│ - Rules: "Inter-library loans have different periods"            │
└─────────────────────────────────────────────────────────────────┘

SUPPORTING SUBDOMAINS (Necessary Infrastructure):
┌─────────────────────────────────────────────────────────────────┐
│ CATALOG                                                          │
│ - Managing book metadata (title, author, ISBN, copies)           │
│ - Not differentiating - all libraries need this                  │
│ - But specific to libraries (not generic like auth)              │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│ PATRON MANAGEMENT                                                │
│ - Member registration, membership tiers                          │
│ - Borrowing limits based on membership                           │
│ - Contact information, preferences                               │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│ FINES & FEES                                                     │
│ - Calculate overdue fines                                        │
│ - Track payments                                                 │
│ - Suspend borrowing privileges                                   │
└─────────────────────────────────────────────────────────────────┘

GENERIC SUBDOMAINS (Buy/Integrate):
┌─────────────────────────────────────────────────────────────────┐
│ IDENTITY & ACCESS       - Auth0, Okta, Cognito                  │
│ PAYMENTS                - Stripe, PayPal                        │
│ NOTIFICATIONS           - SendGrid, Twilio                      │
│ SEARCH                  - Elasticsearch, Algolia                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Defining Bounded Contexts

A Bounded Context is a **boundary within which a domain model is consistent**. The same word can mean different things in different contexts.

### The "Book" Example

```
┌─────────────────────────────────────────────────────────────────┐
│                    THE WORD "BOOK" MEANS:                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CATALOG CONTEXT           LENDING CONTEXT        ACQUISITION   │
│  ┌─────────────────┐       ┌─────────────────┐   ┌────────────┐ │
│  │ CatalogBook     │       │ LoanableItem    │   │ PurchaseItem│ │
│  │ - title         │       │ - catalogId     │   │ - isbn      │ │
│  │ - author        │       │ - isAvailable   │   │ - price     │ │
│  │ - isbn          │       │ - currentLoan   │   │ - vendor    │ │
│  │ - publisher     │       │ - holdQueue     │   │ - quantity  │ │
│  │ - publicationYr │       │ - condition     │   │ - budget    │ │
│  │ - subjects      │       │                 │   │             │ │
│  │ - description   │       │                 │   │             │ │
│  └─────────────────┘       └─────────────────┘   └────────────┘ │
│                                                                  │
│  Cares about:              Cares about:          Cares about:   │
│  - Metadata                - Availability        - Cost         │
│  - Classification          - Loan status         - Procurement  │
│  - Discoverability         - Hold queue          - Budget       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

DIFFERENT MODELS FOR DIFFERENT PURPOSES
- Don't try to create one "Book" model that serves all contexts
- Each context has its own optimized model
```

### Bounded Context Sizing

```
TOO LARGE (Monolith):
┌─────────────────────────────────────────────────────────────────┐
│                     LIBRARY SYSTEM                               │
│  - Catalog, Lending, Patrons, Fines, Acquisitions, Events...    │
│  - One team owns everything                                      │
│  - Changes require coordination across all concerns              │
│  - Model becomes bloated and inconsistent                        │
└─────────────────────────────────────────────────────────────────┘
PROBLEM: Every change affects everything. "Book" becomes a god object.

TOO SMALL (Nanoservices):
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│ Title  │ │ Author │ │ ISBN   │ │ Loan   │ │ Return │ │ Fine   │
│ Service│ │ Service│ │ Service│ │ Service│ │ Service│ │ Service│
└────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘
PROBLEM: Massive coordination overhead. Simple operations require many calls.

RIGHT SIZE (Team-aligned):
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│    CATALOG      │ │    LENDING      │ │     PATRON      │
│   (Team: 3-5)   │ │   (Team: 5-8)   │ │   (Team: 3-5)   │
│                 │ │                 │ │                 │
│ - Add/Edit books│ │ - Borrow        │ │ - Registration  │
│ - Search        │ │ - Return        │ │ - Membership    │
│ - Categories    │ │ - Renew         │ │ - Preferences   │
│                 │ │ - Holds         │ │                 │
│                 │ │ - Fines         │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
GOAL: One team can own and evolve a context independently.
```

### Heuristics for Bounded Context Boundaries

| Signal | Indicates Boundary |
|--------|-------------------|
| Different stakeholders | Different contexts |
| Different change frequency | Separate contexts |
| Different ubiquitous language | Separate contexts |
| Different data consistency needs | Separate contexts |
| Same deployment unit | Same context |
| Same team ownership | Same context |

---

## Context Mapping

Context Maps show how bounded contexts **relate and communicate**.

### Relationship Patterns

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTEXT MAP PATTERNS                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. SHARED KERNEL                                                │
│     ┌─────────┐                                                  │
│     │ Shared  │◄──── Both teams share ownership                 │
│     │ Code    │      Must coordinate changes                     │
│     └─────────┘      Use sparingly (value objects, events)       │
│      ▲      ▲                                                    │
│   ┌──┴──┐┌──┴──┐                                                │
│   │ Ctx ││ Ctx │                                                │
│   │  A  ││  B  │                                                │
│   └─────┘└─────┘                                                │
│                                                                  │
│  2. CUSTOMER-SUPPLIER (Upstream-Downstream)                      │
│     ┌─────────┐      ┌─────────┐                                │
│     │Upstream │─────▶│Downstream                                │
│     │(Supplier)      │(Customer)│                               │
│     └─────────┘      └─────────┘                                │
│     - Upstream provides API/events                               │
│     - Downstream consumes                                        │
│     - Upstream should consider downstream needs                  │
│                                                                  │
│  3. CONFORMIST                                                   │
│     ┌─────────┐      ┌─────────┐                                │
│     │Upstream │─────▶│Downstream                                │
│     │(Dominant)      │(Conforms)│                               │
│     └─────────┘      └─────────┘                                │
│     - Downstream adopts upstream's model                         │
│     - No translation layer                                       │
│     - Used when upstream won't accommodate                       │
│                                                                  │
│  4. ANTI-CORRUPTION LAYER (ACL)                                  │
│     ┌─────────┐      ┌─────┐      ┌─────────┐                   │
│     │ Legacy  │─────▶│ ACL │─────▶│   New   │                   │
│     │ System  │      └─────┘      │ Context │                   │
│     └─────────┘                   └─────────┘                   │
│     - Translates between models                                  │
│     - Protects new context from legacy pollution                 │
│     - Essential when integrating with external systems           │
│                                                                  │
│  5. OPEN HOST SERVICE + PUBLISHED LANGUAGE                       │
│     ┌─────────┐                                                  │
│     │ Service │──── Documented API/Protocol                     │
│     │   API   │     Versioned, stable contract                  │
│     └─────────┘     Multiple consumers                          │
│          │                                                       │
│     ┌────┴────┐                                                 │
│     ▼    ▼    ▼                                                 │
│   ┌───┐┌───┐┌───┐                                               │
│   │ A ││ B ││ C │  Multiple downstream consumers                │
│   └───┘└───┘└───┘                                               │
│                                                                  │
│  6. SEPARATE WAYS                                                │
│     ┌─────────┐      ┌─────────┐                                │
│     │ Context │      │ Context │   No integration               │
│     │    A    │      │    B    │   Duplicate if needed          │
│     └─────────┘      └─────────┘   Sometimes simplest option    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Integration Strategies

```
SYNCHRONOUS (Request-Response):
┌─────────┐  HTTP/gRPC   ┌─────────┐
│ Lending │─────────────▶│ Catalog │
└─────────┘              └─────────┘
- Simple to understand
- Tight coupling
- Availability dependency

ASYNCHRONOUS (Events):
┌─────────┐              ┌─────────┐
│ Lending │──[Event]────▶│  Fines  │
└─────────┘    Bus       └─────────┘
- Loose coupling
- Better resilience
- Eventually consistent
- Preferred for cross-context communication

DATA REPLICATION:
┌─────────┐              ┌─────────┐
│ Catalog │──[Sync]─────▶│ Lending │
└─────────┘              │ (copy)  │
                         └─────────┘
- Read replica for queries
- Reduces runtime dependencies
- Must handle staleness
```

---

## Applied Example: Library System

### Full Context Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LIBRARY SYSTEM CONTEXT MAP                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                         ┌─────────────────────┐                              │
│                         │    SHARED KERNEL    │                              │
│                         │  ─────────────────  │                              │
│                         │  • AggregateRoot    │                              │
│                         │  • DomainEvent      │                              │
│                         │  • EmailAddress     │                              │
│                         │  • Money            │                              │
│                         └──────────┬──────────┘                              │
│                                    │                                         │
│          ┌─────────────────────────┼─────────────────────────┐              │
│          │                         │                         │              │
│          ▼                         ▼                         ▼              │
│  ┌───────────────┐        ┌───────────────┐        ┌───────────────┐        │
│  │   CATALOG     │        │   LENDING     │        │    PATRON     │        │
│  │   CONTEXT     │        │   CONTEXT     │        │   CONTEXT     │        │
│  │ ───────────── │        │ ───────────── │        │ ───────────── │        │
│  │               │        │               │        │               │        │
│  │ • CatalogBook │        │ • Loan        │        │ • Patron      │        │
│  │ • ISBN        │        │ • LoanableItem│        │ • Membership  │        │
│  │ • Author      │        │ • HoldRequest │        │ • BorrowLimit │        │
│  │ • Category    │        │ • LoanPeriod  │        │ • ContactInfo │        │
│  │               │        │               │        │               │        │
│  │ Events:       │        │ Events:       │        │ Events:       │        │
│  │ • BookAdded   │        │ • BookLoaned  │        │ • PatronReg   │        │
│  │ • BookRemoved │        │ • BookReturned│        │ • TierChanged │        │
│  │               │        │ • BookOverdue │        │ • Suspended   │        │
│  └───────┬───────┘        └───────┬───────┘        └───────┬───────┘        │
│          │                        │                        │                │
│          │    [Published          │                        │                │
│          │     Language]          │                        │                │
│          │                        │                        │                │
│          └────────────────────────┼────────────────────────┘                │
│                                   │                                         │
│                    [Customer-Supplier]                                      │
│                                   │                                         │
│                                   ▼                                         │
│                          ┌───────────────┐                                  │
│                          │    FINES      │                                  │
│                          │   CONTEXT     │                                  │
│                          │ ───────────── │                                  │
│                          │ • Fine        │                                  │
│                          │ • Payment     │                                  │
│                          │ • FinePolicy  │                                  │
│                          │               │                                  │
│                          │ Listens to:   │                                  │
│                          │ • BookOverdue │                                  │
│                          │ • BookReturned│                                  │
│                          └───────┬───────┘                                  │
│                                  │                                          │
│                           [ACL]  │                                          │
│                                  ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      EXTERNAL SYSTEMS                                │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │   Payment    │  │    Email     │  │   Identity   │               │   │
│  │  │   Gateway    │  │   Service    │  │   Provider   │               │   │
│  │  │  (Stripe)    │  │  (SendGrid)  │  │   (Auth0)    │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Detailed Context Relationships

```
CATALOG → LENDING (Published Language)
──────────────────────────────────────
Catalog publishes:
  • BookAddedToCatalog { catalogBookId, title, author, isbn }
  • BookRemovedFromCatalog { catalogBookId }
  • BookDetailsUpdated { catalogBookId, changes }

Lending subscribes and maintains:
  • LoanableItem { catalogBookId, isAvailable, condition }
  • Does NOT care about: description, subjects, publisher
  • Has its OWN availability state (not derived from catalog)

Why? Lending needs to track physical copies. A catalog entry might have
5 copies - Lending tracks each copy's availability independently.


PATRON → LENDING (Customer-Supplier)
────────────────────────────────────
Patron (Upstream) provides:
  • PatronBorrowingProfile { patronId, maxLoans, loanPeriodDays }
  • API: GET /patrons/{id}/borrowing-profile

Lending (Downstream) consumes:
  • Checks patron can borrow before creating loan
  • Caches borrowing profile (with TTL)
  • Has fallback if Patron service unavailable

Why? Lending depends on Patron for authorization decisions, but
Patron shouldn't know about Lending's internals.


LENDING → FINES (Customer-Supplier with Events)
───────────────────────────────────────────────
Lending (Upstream) publishes:
  • BookBecameOverdue { loanId, patronId, daysOverdue }
  • BookReturned { loanId, wasOverdue, daysOverdue }

Fines (Downstream) subscribes:
  • Creates Fine aggregate on BookBecameOverdue
  • Calculates amount based on FinePolicy
  • Closes Fine on BookReturned (with final amount)

Why? Fines is a separate business concern. Fine policies might be
managed by a different team (finance vs. circulation).


FINES → PAYMENT GATEWAY (ACL)
─────────────────────────────
Fines context model:
  • Payment { fineId, amount, patronId, status }

Payment Gateway model (Stripe):
  • PaymentIntent { amount, currency, customer, metadata }

Anti-Corruption Layer translates:
  class PaymentGatewayACL:
      def create_payment(self, fine: Fine) -> Payment:
          stripe_customer = self._get_or_create_stripe_customer(fine.patron_id)
          intent = stripe.PaymentIntent.create(
              amount=fine.amount.cents,
              currency="usd",
              customer=stripe_customer.id,
              metadata={"fine_id": str(fine.id)}
          )
          return Payment(
              fine_id=fine.id,
              external_id=intent.id,
              status=self._map_status(intent.status)
          )

Why? We don't want Stripe's model polluting our domain. The ACL
translates between Stripe's concepts and our Fine/Payment concepts.
```

---

## Discovery Questions

Use these questions during domain discovery sessions with domain experts.

### Understanding the Business

```
CORE DOMAIN DISCOVERY:
1. "What makes your library different from others?"
2. "Where do you spend most of your innovation budget?"
3. "What would hurt most if a competitor did it better?"
4. "What processes have the most complex business rules?"

SUBDOMAIN IDENTIFICATION:
5. "Can you list all the major capabilities of the library?"
6. "Which capabilities could you outsource without losing identity?"
7. "Which capabilities MUST be built custom?"
8. "Which capabilities are legally required vs. differentiating?"

BOUNDED CONTEXT DISCOVERY:
9. "Do different departments use the same terms differently?"
10. "When you say 'book', what attributes matter to you?"
    - Ask catalogers, circulation staff, acquisitions separately
11. "What information do you need vs. what do you NOT care about?"
12. "If you had to split into separate systems, where would you draw lines?"

CONTEXT RELATIONSHIPS:
13. "When X happens, what other departments need to know?"
14. "What information do you need from other departments?"
15. "What would happen if that information was 5 minutes stale?"
16. "Who owns the definition of [term]?"
```

### Technical Discovery

```
DATA OWNERSHIP:
1. "Who is the authoritative source for [entity]?"
2. "If two systems disagree, who wins?"
3. "How fresh does this data need to be?"

CONSISTENCY REQUIREMENTS:
4. "What operations must be atomic (all-or-nothing)?"
5. "Can this be eventually consistent? How eventual?"
6. "What's the cost of temporary inconsistency?"

INTEGRATION PATTERNS:
7. "Do you need immediate response or can it be async?"
8. "What happens if the other system is down?"
9. "How do you handle failures today?"
```

---

## Anti-Patterns to Avoid

### 1. The God Context

```
BAD: Everything in one context
┌─────────────────────────────────────────────────────────────────┐
│                       LIBRARY CONTEXT                            │
│  Book, Author, Publisher, Member, Loan, Return, Fine, Payment,  │
│  Hold, Reservation, Event, Room, Equipment, Staff, Schedule...  │
└─────────────────────────────────────────────────────────────────┘

PROBLEMS:
- One team can't own all of this
- Changes require understanding everything
- "Book" model has 50 fields for different purposes
- Testing requires setting up entire system
```

### 2. Anemic Contexts

```
BAD: Contexts without behavior
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Book CRUD   │     │ Member CRUD │     │ Loan CRUD   │
│ Service     │     │ Service     │     │ Service     │
└─────────────┘     └─────────────┘     └─────────────┘
        │                  │                   │
        └──────────────────┼───────────────────┘
                           ▼
                  ┌─────────────────┐
                  │  Business Logic │
                  │    Service      │
                  │  (ALL rules)    │
                  └─────────────────┘

PROBLEMS:
- Business logic centralized outside contexts
- Contexts are just data buckets
- No encapsulation of invariants
```

### 3. Distributed Monolith

```
BAD: Contexts with synchronous dependencies
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│ Catalog │────▶│ Lending │────▶│ Patron  │────▶│ Payment │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
                     │
                     └─────────────────────────────▶ ALL MUST BE UP

PROBLEMS:
- Worse than monolith (network failures)
- Can't deploy independently
- Latency compounds
```

### 4. Premature Decomposition

```
BAD: Splitting before understanding
Day 1: "Let's make microservices!"

┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│ Title  │ │ Author │ │ Loan   │ │ Return │ │ Member │
└────────┘ └────────┘ └────────┘ └────────┘ └────────┘

6 months later: "Wait, Title and Author should be together..."
                "Loan and Return are actually one workflow..."

BETTER: Start with modular monolith, split when boundaries are clear
```

### 5. Shared Database

```
BAD: Multiple contexts sharing tables
┌─────────────┐     ┌─────────────┐
│   Lending   │     │   Catalog   │
│   Context   │     │   Context   │
└──────┬──────┘     └──────┬──────┘
       │                   │
       └─────────┬─────────┘
                 ▼
         ┌─────────────┐
         │   BOOKS     │
         │   TABLE     │
         │ (shared)    │
         └─────────────┘

PROBLEMS:
- No clear ownership
- Schema changes affect both
- Can't evolve independently
- Coupling at data level
```

---

## Summary: The Strategic DDD Process

```
┌─────────────────────────────────────────────────────────────────┐
│                    STRATEGIC DDD PROCESS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. UNDERSTAND THE DOMAIN                                        │
│     └── Event Storming, talk to domain experts                  │
│                                                                  │
│  2. IDENTIFY SUBDOMAINS                                          │
│     └── Core, Supporting, Generic                               │
│     └── Where do you compete?                                   │
│                                                                  │
│  3. DEFINE BOUNDED CONTEXTS                                      │
│     └── Where does language change meaning?                     │
│     └── What can one team own?                                  │
│     └── What changes together?                                  │
│                                                                  │
│  4. MAP CONTEXT RELATIONSHIPS                                    │
│     └── Who depends on whom?                                    │
│     └── How do they communicate?                                │
│     └── What patterns apply?                                    │
│                                                                  │
│  5. IMPLEMENT WITH TACTICAL DDD                                  │
│     └── Aggregates, Value Objects, Events                       │
│     └── Apply WITHIN each bounded context                       │
│                                                                  │
│  6. ITERATE                                                      │
│     └── Boundaries will evolve                                  │
│     └── Refactor as understanding grows                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Further Reading

- **"Domain-Driven Design" by Eric Evans** - The original book
- **"Implementing Domain-Driven Design" by Vaughn Vernon** - Practical implementation
- **"Domain-Driven Design Distilled" by Vaughn Vernon** - Quick overview
- **"Learning Domain-Driven Design" by Vlad Khononov** - Modern take
- **"Team Topologies" by Skelton & Pais** - Aligning teams to contexts
