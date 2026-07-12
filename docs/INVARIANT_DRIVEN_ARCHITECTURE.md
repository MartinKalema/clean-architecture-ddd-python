# Invariant-Driven Architecture

## Purpose

This guide explains how to derive architecture from business correctness rather
than from a list of patterns or technologies. The central question is:

> What must always remain true?

A senior engineer asks this before choosing aggregates, services, databases,
caches, queues, or deployment boundaries. The answer becomes a set of proof
obligations. Architecture is then the smallest set of consistency boundaries and
failure-handling mechanisms that can satisfy those obligations.

Use [Design to Requirements](DESIGN_TO_REQUIREMENTS.md) to validate and specify
the obligations before deriving invariants. Use the
[Engineering Design System](ENGINEERING_DESIGN_SYSTEM.md) for the complete team
workflow from outcome discovery through operational evidence.

This repository intentionally implements more infrastructure than the minimum
library system requires. That is useful for learning, provided we can separate:

- what the business requires;
- what is required only after a deployment boundary is introduced; and
- what exists to practise a distributed-systems technique.

## Start With Truth, Not a Predetermined Solution

Solution-first design sounds like this:

> We will use DDD, CQRS, Kafka, Redis, Elasticsearch, and sagas. How should the
> library fit into them?

That list intentionally contains different kinds of things:

- DDD is a domain-modeling and design approach.
- CQRS and sagas are architectural patterns.
- Kafka, Redis, and Elasticsearch are technologies.

The mistake is not that all of them are technologies. The mistake is committing
to any approach, pattern, or technology before establishing the problem it must
solve and the truth it must preserve.

Invariant-first design reverses the question:

> A patron must never exceed the borrowing limit. A copy must never have two
> outstanding loans. What is the smallest design that can prove those facts
> under retries and concurrency?

The difference matters because every new component creates additional failure
modes. A queue introduces duplicate, delayed, reordered, and poison messages. A
cache introduces stale data and invalidation failures. A separate database
removes atomic transactions across boundaries. A search projection introduces
lag and rebuild problems.

An architecture component is justified only when its benefit exceeds the new
proof obligations it creates.

### Question requirements by evidence, not authority

A requirement is not valid merely because an important person, team, or
department requested it. Conversely, a valid constraint does not always have a
single human owner. It may come from physics, legislation, an external contract,
measured production behavior, a security threat model, or an agreed business
invariant.

For every proposed requirement or architectural constraint, ask:

1. What is its source?
2. What evidence supports it?
3. What failure does it prevent?
4. What happens if it is removed?
5. Is it a business truth, changeable policy, service-level objective, external
   constraint, or implementation assumption?
6. Can it be tested or measured?

An identifiable decision owner can still be useful when an organization needs
someone to clarify or approve a policy change. That is governance metadata, not
evidence that the requirement is correct.

This is also distinct from **model authority**. Saying “Lending owns loan
availability” identifies the one model allowed to change that fact. It does not
mean a particular person makes the fact true.

### Relationship to the question-delete-optimize discipline

The engineering sequence often summarized as “question requirements, delete,
simplify, accelerate, then automate” is compatible with this method. Its central
warning is correct: do not optimize or automate a component that should not
exist.

Invariant-driven architecture adds a safety test before deletion:

> What truth was this component protecting, and what will protect that truth
> after it is removed?

The combined sequence is:

1. State the required business outcome and truths.
2. Challenge each requirement using its source, evidence, and removal
   consequence.
3. Delete requirements, boundaries, parts, and processes with no valid proof
   obligation.
4. Replace remaining complexity with the smallest mechanism that proves the
   required truth under concurrency and failure.
5. Simplify and optimize what remains.
6. Accelerate feedback and delivery.
7. Automate only the stable, necessary process.

For this library, the old Catalog/Lending saga existed only because we had
assumed the two models required separate circulation commits. No independent
deployment, database, regulatory, or organizational constraint supported that
assumption. Deleting it removed the reservation workflow, compensation,
fencing generation, worker, and reaper. The unique outstanding-loan constraint,
patron admission fence, and idempotency receipt remained because each protects
a named hard invariant or retry guarantee.

## Not Every Requirement Is an Invariant

The word "always" must be used precisely.

| Category | Meaning | Library example | Enforcement |
|---|---|---|---|
| Hard invariant | Invalid state must never commit | One outstanding loan per book | Aggregate guard, transaction, database constraint |
| Convergence invariant | Temporary disagreement is allowed, but it must repair | A committed loan eventually appears in the search projection | Durable event, idempotent handler, retry, rebuild |
| Business policy | A rule that may change by product decision | Premium patrons may borrow ten books | Domain policy and tests |
| Service-level objective | A measurable reliability or latency target | 99% of searches complete within 200 ms | Capacity, monitoring, alerting |
| Derived-view expectation | A rebuildable view should reflect its source within a known delay | Elasticsearch reflects committed loans within 30 seconds | CDC lag gate, replay, rebuild |

This classification prevents two common mistakes:

1. Using eventual consistency for a hard invariant that must be checked
   atomically.
2. Building synchronous distributed coordination for a derived view that may
   safely lag.

In a distributed system, two independently committed records cannot be
guaranteed to agree at every instant without coordination. If the business
really requires immediate agreement, put the relevant state inside one
consistency boundary or pay explicitly for distributed consensus. A saga
provides eventual convergence; it does not create an atomic transaction across
services.

## The Senior Engineer's Breakdown Process

### 1. Describe business outcomes

Start with user-visible outcomes, without mentioning frameworks:

- register a patron;
- add a book;
- borrow a book;
- extend a loan;
- return a loan;
- find books and patron loans; and
- notify a patron after a successful borrow.

### 2. Write invariants as testable statements

Good invariant statements are specific enough to disprove:

- A book has at most one loan whose `returned_at` is `NULL`.
- A suspended patron cannot create a loan.
- A patron's outstanding-loan count never exceeds the tier limit.
- A returned loan cannot become active again.
- Repeating the same command does not repeat its business effect.
- A return can complete only the exact loan named by the command.
- Catalog never stores a second mutable copy of Lending availability.

"The data should be consistent" is not useful. It does not say which data,
which consistency model, who owns the truth, or how quickly disagreement must
be repaired.

### 3. Assign one authority for each fact

Every mutable fact needs one owner.

| Fact | Authority |
|---|---|
| Book title, author, and catalog identity | Catalog |
| Patron identity, tier, and suspension | Patron |
| Loan existence, due date, extension, and return | Lending |
| Notification delivery attempt | Notification |
| Search document | No authority; rebuildable projection |
| Redis entry | No authority; disposable optimization |

If two contexts both believe they are authoritative for the same mutable fact,
the architecture has created a conflict-resolution problem. Copies are allowed,
but one copy must be explicitly derived from the authoritative source.

### 4. Find the smallest consistency boundary

For each hard invariant, ask:

- Which rows or aggregates participate?
- Can one process and one database transaction enforce it?
- Which concurrent commands can race?
- What database constraint proves the invariant even if application code is
  wrong?
- What must be locked to prevent write skew?

State that must change atomically should normally be colocated. Do not split it
across bounded contexts merely because the nouns are different. A bounded
context is a model boundary; it is not automatically a service, process, or
database boundary.

### 5. Enumerate failures before adding asynchronous work

For every step, ask what happens if the process:

- receives the request twice;
- times out after committing;
- crashes immediately before or after commit;
- publishes an event twice;
- publishes events out of order;
- receives an event after a newer workflow has started;
- loses Redis, Kafka, Elasticsearch, or email connectivity; or
- is stopped halfway through startup or shutdown.

If the proposed architecture has no answer, it has not preserved the invariant.

### 6. Choose the consistency promise

Make the promise explicit:

- **Immediate:** true when the transaction commits.
- **Read-after-command:** true before the successful command response returns.
- **Eventual with bound:** repaired within a stated duration under normal
  operation.
- **Best effort:** may be lost without violating the core business outcome.

This decision determines whether the solution needs a transaction, cache fence,
durable outbox, retrying worker, reaper, or merely logging.

### 7. Add the minimum mechanism that closes the failure

Use the cheapest mechanism that proves the required property:

| Problem | Minimum mechanism |
|---|---|
| Invalid value inside one aggregate | Domain guard |
| Duplicate or impossible database state | Unique/check constraint |
| Concurrent changes to the same decision | Transaction and row lock or compare-and-swap |
| Timed-out command may be retried | Idempotency receipt in the same transaction |
| Side effect must survive a process crash | Transactional outbox |
| Separate transactions must converge | Saga with durable retries and compensation |
| Delayed message can target newer work | Workflow identity and fencing token |
| Projection may lag | Lag measurement and authoritative fallback |
| Cache may be stale | TTL, invalidation, or version/generation fence |

### 8. Define evidence and detection

An invariant needs both prevention and evidence:

- executable domain tests;
- database constraints tested on migrated PostgreSQL;
- concurrency tests;
- idempotency and replay tests;
- lag, retry, quarantine, and reconciliation metrics; and
- alerts for a convergence deadline being missed.

"The handler should eventually run" is hope. A durable record, measurable lag,
and an alert are evidence.

## Worked Example: The Minimum Library Architecture

Assume the initial product requirements are:

- patrons can borrow and return books;
- eligibility and borrowing limits are enforced immediately;
- a book cannot be lent twice;
- command retries must not duplicate effects;
- basic title/author search is sufficient; and
- email confirmation is useful but not part of the borrow transaction.

The minimum architecture is a modular monolith:

```text
Client
  |
  v
HTTP API
  |
  v
Application operations
  |
  v
PostgreSQL  ---- optional PostgreSQL outbox worker ----> Email provider
```

Logical Catalog, Patron, and Lending modules can still have separate models and
ports. They do not need separate processes or databases.

### Minimum borrow transaction

A particularly simple model makes Lending authoritative for availability. Book
metadata stays in Catalog, while "available to lend" is derived from whether an
outstanding loan exists. That avoids storing one mutable availability flag in
Catalog and another loan state in Lending.

```text
BEGIN
  claim idempotency key
  lock patron eligibility/capacity decision
  verify patron exists and is not suspended
  count or reserve patron capacity
  insert outstanding loan
    protected by unique outstanding-loan constraint per book
COMMIT
```

The database supplies final proof:

```sql
CREATE UNIQUE INDEX one_outstanding_loan_per_book
ON loans (catalog_book_id)
WHERE returned_at IS NULL;
```

Concurrent requests for the same book cannot both commit. Concurrent requests
for one patron must serialize the capacity decision, for example by locking the
patron's lending-capacity row before counting and inserting.

The return operation is also one transaction:

```text
BEGIN
  load exact loan FOR UPDATE
  require returned_at IS NULL
  set returned_at
COMMIT
```

Availability becomes true because no outstanding loan remains. There is no
second Catalog state to reconcile and therefore no return saga.

### Minimum idempotency

Store the command key, request fingerprint, status, and committed response in
PostgreSQL. Claim and complete the receipt in the same transaction as the
business change. A retry with the same facts returns the first result; a retry
with different facts is rejected.

No Kafka topic is required to make an HTTP command idempotent.

### Minimum search

Start with indexed PostgreSQL queries and `pg_trgm` for partial title/author
matching. Add Elasticsearch only after measured query requirements exceed what
PostgreSQL can provide.

### Minimum notification delivery

Choose the promise:

- If losing an occasional email is acceptable, send it after commit as best
  effort.
- If every confirmation must eventually be attempted, write an email outbox row
  in the loan transaction and let one small PostgreSQL-polling worker deliver it.

Kafka and Debezium become justified only when event volume, replay, independent
consumer scaling, or organizational boundaries require them.

### Minimum configuration

Use validated environment variables or mounted configuration and restart the
process to apply changes. A dedicated etcd cluster is justified only when the
fleet needs centrally coordinated configuration behavior that simpler platform
configuration cannot provide.

## Why This Repository Still Uses More

This project is a learning system, so it deliberately moves beyond the minimum.
Each additional mechanism should be understood as a lesson with a cost.

| Mechanism in this repository | What it teaches | New obligations it creates |
|---|---|---|
| Transactional outbox and Debezium | Commit event facts without dual writes | Connector health, WAL retention, schema contracts |
| Per-handler inbox | Idempotent event consumption | Inbox retention and crash-window semantics |
| Redis generation fencing | Read-after-command cache coherence | Commit/invalidation crash window, recovery, cleanup |
| Elasticsearch CDC projection | Rebuildable read models | Lag gating, reindex catch-up, fallback behavior |
| Separate notification consumer | Isolate optional failure from correctness | Independent health and retry policy |
| Process-specific composition roots | Resource and configuration ownership | More deployment units to supervise |

The advanced version is valuable because it makes these failure modes
executable. It should not be mistaken for the minimum commercial solution to
the library problem.

## When to Evolve the Minimum

Add complexity only after a concrete trigger appears.

| Add | Evidence that justifies it |
|---|---|
| PgBouncer | Replica connection budgets approach PostgreSQL capacity |
| Redis | Measured database/read latency cannot meet the SLO economically |
| Elasticsearch | Required relevance, language, or query features exceed PostgreSQL search |
| Transactional outbox | A committed fact must reliably drive an external side effect |
| Kafka | Multiple independent consumers need durable replay or separate scaling |
| Debezium | CDC/outbox throughput or operational model is preferable to polling |
| Separate service/database | Independent team ownership, deployment, scaling, security, or regulatory boundary |
| Saga | One business outcome must cross independently committed boundaries |
| etcd | The fleet truly needs centralized runtime configuration coordination |
| Circuit breaker | A remote dependency has measured failure modes that timeout/retry budgets cannot contain |

"This may scale someday" is not evidence. Record the threshold, metric, and
decision that will trigger the change.

## Invariant Review Template

Use this table before implementing a capability:

| Question | Answer |
|---|---|
| Business outcome | What is the user trying to complete? |
| Requirement source | Where did the requirement come from? |
| Evidence | What observed fact, contract, threat, or business rule supports it? |
| Removal consequence | Which concrete failure appears if it is deleted? |
| Classification | Business truth, policy, SLO, external constraint, or implementation assumption? |
| Invariant | What invalid state must never commit? |
| Authority | Which context owns the mutable fact? |
| Consistency promise | Immediate, read-after-command, eventual, or best effort? |
| Consistency boundary | Which aggregate/rows and transaction enforce it? |
| Concurrency | Which commands can race and how are they serialized? |
| Database proof | Which unique, foreign-key, or check constraint is the backstop? |
| Retry identity | How is a repeated command or message recognized? |
| Crash points | What if the process dies before/after each commit or publish? |
| Recovery | Who retries or reconciles, and for how long? |
| Detection | What metric or query proves convergence is falling behind? |
| Simplest design | What can be removed while all answers remain valid? |

## Applied Review: Borrowing in the Current Architecture

| Question | Current answer |
|---|---|
| Outcome | Eligible patron borrows one available book |
| Hard invariant | Lending permits one outstanding loan per book and enforces patron capacity before commit |
| Availability authority | An outstanding Lending loan (`returned_at IS NULL`); Catalog stores metadata only |
| Transaction | Borrow creates the authoritative loan synchronously in one Lending transaction |
| Retry identity | HTTP idempotency key and request fingerprint stored with the loan transaction |
| Concurrency proof | Patron admission fence plus a partial unique database index per book |
| Return | The exact Lending loan is marked returned; no Catalog write or reconciliation event exists |
| Optional effects | Loan events drive notification and projections after the business commit |
| Detection | Database constraint violations, projection lag, notification inbox, quarantine, and DLQ records |

The earlier learning design put reservation state in Catalog and loan state in
Lending, then used a saga to make them converge. That was a valid exercise in
distributed coordination, but it was not the minimum architecture for the
business rule. It duplicated one mutable fact and made Kafka workers and a
reservation reaper part of basic correctness. The current model moves the
consistency boundary instead: Lending owns circulation, so the hard invariant
can be proved at one commit.

## Architecture Review Questions

Before approving a design, ask:

1. What must never be false after a successful commit?
2. Which disagreements are allowed temporarily, and for how long?
3. What is the source and evidence for every requirement or constraint?
4. What concrete failure occurs if each architectural component is removed?
5. Which model is the single authority for every mutable fact?
6. Does a hard invariant cross a proposed service boundary? If so, should the
   boundary move?
7. What happens under duplicate requests, concurrent requests, timeouts,
   process crashes, delayed events, and reordered events?
8. Which database constraints prove the application assumptions?
9. Can every derived cache or projection be discarded and rebuilt?
10. What mechanism detects missed convergence rather than merely retrying?
11. Which component could be removed without violating an invariant or SLO?
12. What measured condition would justify adding it back?

The goal is not the fewest components at any cost. The goal is the fewest
components that make the required truths provable under real failure.
