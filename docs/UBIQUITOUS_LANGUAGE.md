# Ubiquitous Language Glossary

## Library Domain

This glossary defines the shared vocabulary used across the Library system. All team members (developers, domain experts, stakeholders) should use these terms consistently.

---

## Core Concepts

### Book
A physical or digital item in the library's collection that can be borrowed by patrons.

| Context | Meaning | Key Attributes |
|---------|---------|----------------|
| **Catalog** | Bibliographic record describing a work | title, author, ISBN, publisher, subjects |
| **Lending** | A loanable item that tracks availability | catalogId, isAvailable, condition |
| **Acquisition** | An item to be purchased | ISBN, price, vendor, budgetCode |

**Usage:**
- ✅ "Add a book to the catalog"
- ✅ "This book is available for borrowing"
- ❌ "The book is overdue" (use "loan" instead)

---

### Patron
A registered library user who can borrow materials.

**Synonyms (DO NOT USE):** member, borrower, customer, user

**Attributes:**
- `patronId` - Unique identifier
- `membershipTier` - STANDARD, PREMIUM, RESEARCHER
- `borrowingLimit` - Maximum concurrent loans allowed
- `status` - ACTIVE, SUSPENDED, EXPIRED

**Usage:**
- ✅ "The patron borrowed three books"
- ✅ "Patron privileges are suspended"
- ❌ "The user checked out books" (use "patron" and "borrowed")

---

### Loan
An active borrowing transaction where a patron has possession of a book.

**Not to be confused with:** Borrow (verb), Checkout (avoid this term)

**Lifecycle:**
```
Created → Active → [Overdue] → Returned
                 → [Renewed]
```

**Attributes:**
- `loanId` - Unique identifier
- `patronId` - Who borrowed
- `bookId` - What was borrowed
- `borrowedAt` - When the loan started
- `dueDate` - When the book must be returned
- `status` - ACTIVE, OVERDUE, RETURNED

**Usage:**
- ✅ "Create a loan for this patron"
- ✅ "The loan is overdue"
- ✅ "Renew the loan"
- ❌ "Checkout the book" (use "create a loan" or "borrow")

---

### Hold
A reservation request for a book that is currently unavailable.

**Synonyms (DO NOT USE):** reservation, request, queue

**Lifecycle:**
```
Placed → Waiting → Ready for Pickup → Fulfilled
                                   → Expired
                → Cancelled
```

**Attributes:**
- `holdId` - Unique identifier
- `patronId` - Who placed the hold
- `bookId` - What book is requested
- `placedAt` - When the hold was placed
- `position` - Place in the hold queue
- `expiresAt` - When the hold expires if not picked up

**Usage:**
- ✅ "Place a hold on this book"
- ✅ "The hold is ready for pickup"
- ✅ "Cancel the hold"
- ❌ "Reserve the book" (use "place a hold")

---

### Fine
A monetary penalty for late return of borrowed materials.

**Attributes:**
- `fineId` - Unique identifier
- `loanId` - Which loan incurred the fine
- `patronId` - Who owes the fine
- `amount` - Money owed
- `status` - OUTSTANDING, PAID, WAIVED

**Business Rules:**
- Fine accrues daily after due date
- Rate depends on material type (book, DVD, etc.)
- Maximum fine capped per item
- Patron suspended when total fines exceed threshold

**Usage:**
- ✅ "Issue a fine for the overdue loan"
- ✅ "The fine has been paid"
- ✅ "Waive the fine"
- ❌ "Charge a fee" (use "issue a fine")

---

## Actions (Verbs)

### Borrow
The act of a patron taking a book from the library with the intention of returning it.

**Creates:** Loan
**Preconditions:**
- Book is available
- Patron is active
- Patron has not exceeded borrowing limit
- Patron has no excessive fines

**Usage:**
- ✅ "The patron borrowed the book"
- ❌ "The patron checked out the book"

---

### Return
The act of a patron bringing back a borrowed book.

**Affects:** Loan (marks as returned)
**May Trigger:** Fine (if overdue)

**Usage:**
- ✅ "Return the book"
- ✅ "The book was returned late"
- ❌ "Check in the book"

---

### Renew
Extending the due date of an active loan.

**Preconditions:**
- Loan is active (not already returned)
- No holds exist for this book
- Renewal limit not exceeded

**Usage:**
- ✅ "Renew the loan"
- ✅ "The loan cannot be renewed because there are holds"
- ❌ "Extend the checkout"

---

### Suspend
Temporarily revoking a patron's borrowing privileges.

**Reasons:**
- Excessive fines
- Overdue items past threshold
- Policy violation

**Usage:**
- ✅ "Suspend the patron's borrowing privileges"
- ✅ "The patron is suspended due to unpaid fines"
- ❌ "Block the user"

---

## Domain Events

Events represent facts that have occurred in the domain. They are named in past tense.

| Event | Description | Key Data |
|-------|-------------|----------|
| `BookAddedToCatalog` | A new book was added to the library collection | bookId, title, author, isbn |
| `BookRemovedFromCatalog` | A book was removed from the collection | bookId, reason |
| `BookBorrowed` | A patron borrowed a book | loanId, bookId, patronId, dueDate |
| `BookReturned` | A borrowed book was returned | loanId, returnedAt, wasOverdue |
| `LoanBecameOverdue` | A loan passed its due date | loanId, daysOverdue |
| `LoanRenewed` | A loan's due date was extended | loanId, newDueDate, renewalCount |
| `HoldPlaced` | A patron requested a hold | holdId, bookId, patronId |
| `HoldReadyForPickup` | A held book became available | holdId, expiresAt |
| `HoldExpired` | A hold was not picked up in time | holdId |
| `HoldCancelled` | A patron cancelled their hold | holdId, reason |
| `FineIssued` | A fine was created for an overdue loan | fineId, loanId, amount |
| `FinePaid` | A fine was paid | fineId, paymentMethod |
| `FineWaived` | A fine was forgiven | fineId, reason, waivedBy |
| `PatronRegistered` | A new patron joined the library | patronId, membershipTier |
| `PatronSuspended` | A patron's privileges were suspended | patronId, reason |
| `PatronReinstated` | A suspended patron was reactivated | patronId |

---

## Value Objects

Immutable objects defined by their attributes, not identity.

### BookId
Unique identifier for a book in the catalog.
- Format: UUID
- Example: `550e8400-e29b-41d4-a716-446655440000`

### ISBN
International Standard Book Number.
- Format: 10 or 13 digits
- Example: `978-0-13-468599-1`

### Title
The name of a book.
- Constraints: Non-empty, max 200 characters

### Author
The creator of a book.
- Constraints: Non-empty, max 100 characters

### Money
Represents a monetary amount.
- Attributes: `amount` (decimal), `currency` (ISO code)
- Example: `Money(10.50, "USD")`

### LoanPeriod
The duration a book can be borrowed.
- Attributes: `days` (integer)
- Standard: 14 days, Researcher: 30 days

### EmailAddress
A valid email address for notifications.
- Constraints: Valid email format

---

## Aggregates

Clusters of entities and value objects with consistency boundaries.

### Book Aggregate (Catalog Context)
```
Book (Aggregate Root)
├── BookId (identifier)
├── Title
├── Author
├── ISBN (optional)
├── Publisher
├── PublicationYear
└── Subjects[]
```
**Invariants:**
- Must have title and author
- ISBN must be valid format if provided

### Loan Aggregate (Lending Context)
```
Loan (Aggregate Root)
├── LoanId (identifier)
├── PatronId (reference)
├── BookId (reference)
├── BorrowedAt
├── DueDate
├── ReturnedAt (optional)
├── RenewalCount
└── Status
```
**Invariants:**
- Cannot renew if holds exist
- Cannot renew more than 3 times
- DueDate must be after BorrowedAt

### Patron Aggregate (Patron Context)
```
Patron (Aggregate Root)
├── PatronId (identifier)
├── Name
├── Email
├── MembershipTier
├── BorrowingLimit
├── Status
└── ContactInfo
    ├── Phone
    └── Address
```
**Invariants:**
- BorrowingLimit determined by MembershipTier
- Cannot borrow if Status is SUSPENDED

### Fine Aggregate (Fines Context)
```
Fine (Aggregate Root)
├── FineId (identifier)
├── LoanId (reference)
├── PatronId (reference)
├── Amount (Money)
├── IssuedAt
├── Status
└── Payments[]
    ├── PaymentId
    ├── Amount
    └── PaidAt
```
**Invariants:**
- Total payments cannot exceed fine amount
- Status is PAID when payments equal amount

---

## Bounded Context Glossary

Terms may have different meanings in different contexts:

| Term | Catalog Context | Lending Context | Fines Context |
|------|-----------------|-----------------|---------------|
| **Book** | Bibliographic metadata | Loanable item with availability | N/A (uses LoanId) |
| **Available** | In the collection | Not currently on loan | N/A |
| **Status** | Publication status | Loan status (active/returned) | Fine status (outstanding/paid) |
| **Period** | Publication period | Loan duration | N/A |

---

## Anti-Corruption Layer Translations

When integrating with external systems, translate their terms to our ubiquitous language:

### Payment Gateway (Stripe)
| Stripe Term | Our Term |
|-------------|----------|
| Customer | Patron |
| PaymentIntent | Payment |
| Amount (cents) | Money |
| Charge | Payment |

### Email Service (SendGrid)
| SendGrid Term | Our Term |
|---------------|----------|
| Recipient | Patron (email) |
| Template | NotificationTemplate |
| Personalization | NotificationContext |

### Identity Provider (Auth0)
| Auth0 Term | Our Term |
|------------|----------|
| User | Patron |
| user_id | patronId (external) |
| email_verified | isEmailVerified |

---

## Naming Conventions

### Code
```python
# Aggregates: PascalCase noun
class Book:
class Loan:
class Patron:

# Value Objects: PascalCase noun
class BookId:
class Money:
class EmailAddress:

# Domain Events: PascalCase past-tense verb phrase
class BookBorrowed:
class LoanBecameOverdue:
class FineIssued:

# Repositories: PascalCase with Repository suffix
class BookRepository:
class LoanRepository:

# Domain Services: PascalCase describing action
class LoanEligibilityChecker:
class FineCalculator:
```

### Database
```sql
-- Tables: snake_case plural
books
loans
patrons
fines

-- Columns: snake_case
book_id
borrowed_at
due_date
patron_id
```

### API Endpoints
```
# Resources: kebab-case plural
GET  /books
POST /books
GET  /books/{id}

# Actions: verb as sub-resource
POST /books/{id}/borrow
POST /loans/{id}/renew
POST /loans/{id}/return
```

---

## Review Checklist

When reviewing code or documentation, verify:

- [ ] Terms match this glossary
- [ ] No synonyms used (e.g., "user" instead of "patron")
- [ ] Events are past tense
- [ ] Aggregates have clear boundaries
- [ ] Context is clear when term is ambiguous
- [ ] External system terms are translated at boundary
