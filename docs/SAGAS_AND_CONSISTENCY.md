# Sagas, Compensation, and Apologies — A Simple Guide

This guide explains, in simple English, the ideas behind how this system
handles work that spans more than one part of the application. Every idea
here is implemented in this codebase, so each section points to the real
code.

---

## 1. The easy case: one transaction

When all the work happens in one database transaction, failure is easy.
If anything goes wrong, the database throws everything away. Nobody ever
sees the half-finished work. This is called a **rollback**.

```text
BEGIN → change things → problem? → ROLLBACK (as if nothing happened)
                      → all good? → COMMIT
```

In this codebase, one use case = one transaction. For example,
`CreateLoanHandler` opens one unit of work, creates the loan, and commits.
If it fails, nothing was saved.

**Rule of thumb:** inside one transaction, you get safety for free.

---

## 2. The hard case: work that spans transactions

"Borrow a book" needs two different parts of the system:

1. The **Catalog** must mark the book as taken.
2. **Lending** must create a loan.

These are different bounded contexts with different transactions. There is
no magic "big transaction" that covers both. So we do it in steps, and
each step commits on its own:

```text
Step 1: Catalog reserves the book        → COMMITTED
Step 2: Lending creates the loan         → COMMITTED
Step 3: Catalog confirms the borrow      → COMMITTED
```

A chain of steps like this is called a **saga**. The steps talk to each
other through **domain events** (messages like "a book was reserved"),
delivered through the outbox → Debezium → Kafka pipeline.

**The catch:** if step 2 fails, step 1 has *already committed*. You cannot
roll it back. The world already saw it.

---

## 3. Compensation: undoing something you cannot undo

Since we cannot roll back a committed step, we do the next best thing:
we run a **new action that reverses the old one**. This is called a
**compensation**.

Think of a bank statement. The bank never erases a payment. It adds a
*refund*. The history stays honest: payment, then refund.

In our borrow saga:

| Step that committed | Its compensation |
| --- | --- |
| Book was reserved | Release the reservation |
| Loan was created | Cancel the loan |
| Confirmation email sent | (cannot unsend — send a correction) |

Real example in code: if Lending's final patron check rejects the borrow,
`CreateLoanOnBookReservedHandler` releases that exact reservation. The
book becomes available again. If a tentative loan already exists when a
reservation expires, `CatalogBookReleased` cancels that exact loan. See
`src/application/event_handlers/create_loan_on_book_reserved.py`.

Two important rules for compensations:

- **They must be safe to repeat.** Messages can arrive twice, so running
  a compensation twice must not break anything.
- **There is nothing below them.** If a compensation fails, you cannot
  compensate the compensation. Our code retries it (see section 7), and
  the reservation reaper (section 5) is the last safety net.

---

## 4. The semantic lock: the RESERVED state

There is a gap between "book reserved" and "loan confirmed". During this
gap, is the book borrowed or not? The honest answer is: **not yet — it's
in between**.

A plain true/false flag (`is_borrowed`) cannot say "in between". So the
book has three states instead:

```text
AVAILABLE ── reserve() ──► RESERVED ── confirm_borrow() ──► BORROWED
                              │                                │
                          release()                      return_book()
                              ▼                                ▼
                          AVAILABLE                        AVAILABLE
```

`RESERVED` is called a **semantic lock**. It is a lock because while a
book is reserved, nobody else can start borrowing it. It is *semantic*
because the rule lives in our domain code (the `Book` state machine), not
in the database.

You have seen this pattern in real life: a credit card "hold", a hotel
booking that says "pending", or an online shop that keeps an item in your
cart "for 4 minutes". All of these are semantic locks.

See `src/domain/catalog/entities/catalog_book.py`.

---

## 5. Locks can leak: the reaper

What if the saga dies in the middle? The book stays RESERVED forever —
nobody can borrow it, but there is no loan either. The lock has "leaked".

The fix is an **expiry**: a small worker (the **reservation reaper**)
checks regularly for reservations older than a time limit (the TTL) and
releases them.

- Handler: `src/application/command_handlers/release_expired_reservations.py`
- Worker: `scripts/run_reservation_reaper.py`
- Settings: `catalog.reservation_ttl_seconds` (default 300s) in etcd

**Important:** the TTL must be much longer than the time it normally
takes events to travel. Each reservation carries a UUID, owner, and
book-local generation fence. If the reaper releases a reservation after
Lending created its tentative loan, `CatalogBookReleased` cancels only that
loan. If the delayed `LoanCreated` arrives later, Catalog rejects it and
Lending again cancels the same loan idempotently. A stale message can never
confirm or release a newer patron's reservation.

---

## 6. The pivot: order your steps by risk

Some actions can be compensated (release a reservation). Some cannot
(unsend an email). So a saga should be arranged like this:

1. **First**: the steps most likely to fail (so you fail before doing
   anything that needs undoing).
2. **Middle**: the **pivot** — the point of no return. Once past it, the
   saga will finish, no matter what.
3. **After the pivot**: only steps that can be retried until they work.
   No compensation needed — just keep trying.

In this saga, loan creation is still tentative and can be compensated with
`LoanCancelled`. The pivot is **Catalog confirming the exact loan** and
publishing `CatalogBookBorrowed`. The confirmation email subscribes to that
definitive fact—not to `LoanCreated`—so a cancelled borrow never emails
anyone.

---

## 7. Promises must be kept: retries and the dead-letter queue

Everything after the pivot is a **promise**. The exact loan and Catalog book
agree, so the confirmation email must eventually be sent. A temporary problem
(the email service is down for a minute) must not break that promise.

So message handling works like this (see `kafka_client.py`):

1. Try to handle the message.
2. Failed transiently? Wait and **retry with bounded backoff until it
   succeeds**. State-reconciliation events are promises; a brief database
   outage cannot turn a return into a permanent split.
3. A structurally malformed event cannot become valid through retry. Park
   only that poison message on a **dead-letter queue** (a Kafka topic ending
   in `.dlq`) for inspection and replay.
4. Commit the source offset only after successful handling or durable poison
   parking.

Because messages can be delivered more than once, **every handler must be
idempotent** — running it twice must give the same result as once. For
example, if the loan already exists, the handler says "already done" and
moves on instead of failing.

---

## 8. Eligibility: check before and after the lock

Taking a reservation and then discovering the patron doesn't exist is
wasteful: we lock the book, fail, and compensate — three transactions for
a "no".

It is cheaper to **check first**: before reserving, the borrow endpoint uses a
strongly consistent PostgreSQL patron lookup. Unknown or suspended patron?
Reject immediately with a clear error. No lock taken, nothing to undo.

Patron state can still change after that transaction commits. When Lending
consumes `CatalogBookReserved`, it performs a final lookup by the persisted
patron ID and requires the canonical email and eligibility to still match.
A permanent rejection releases the exact reservation; an infrastructure
failure is retried without pretending the borrow was rejected.

See the pre-flight check in
`src/application/command_handlers/borrow_book.py`.

---

## 9. Apologies: the third tool

Big systems (Amazon is the famous example) add one more tool above
rollback and compensation: the **apology**.

Amazon does not reserve inventory when you add an item to your cart. If
two people buy the last one, Amazon *apologizes* to one of them — an
email, a refund, maybe a voucher. Why? Because for millions of items with
deep stock, holding locks costs more (slower site, lost sales) than the
occasional apology costs.

The choice between locking and apologizing is **economics**, not
ideology:

| Situation | Best tool |
| --- | --- |
| Plenty of identical items, conflicts rare | Sell optimistically, apologize on conflict |
| One-of-a-kind item, conflicts matter | Semantic lock (what this system does) |

A library book is one-of-a-kind — two patrons cannot both take it home —
so we lock. Exact identities, fencing, idempotent handlers, and cancellation
handle the expected failure modes automatically. An "apology path" remains
for genuinely unrecoverable cases parked in the dead-letter queue; a mature
system would alarm on and reconcile those incidents.

The three tools, side by side:

```text
rollback      →  inside one transaction   →  free, automatic
compensation  →  across transactions      →  designed undo actions
apology       →  across the business      →  humans + goodwill
```

---

## 10. When to bring in a workflow engine

Everything above is hand-built in this repository, and at this size that
is the right choice — you can read every moving part.

Tools like **Temporal** (a descendant of Amazon's own workflow system)
exist to do this plumbing for you: they persist the saga's progress, run
retries, hold durable timers ("wait 14 days, then send a reminder"), and
survive crashes mid-flow. The moment to adopt one is when you are writing
your *second or third* saga, or when your flows need long waits and human
steps — that is when hand-built plumbing stops teaching and starts
costing.

---

## 11. Scaling the pipeline: the one line at the post office

Think of Kafka as a post office, and a **partition** as one line of
people. Right now, every topic in this system has exactly **one line**,
and the event worker is **one clerk** serving that line.

The clerk works carefully: take one envelope, fully handle it (create
the loan, confirm the book, try the email), and only then take the next
one. This is called **serial** processing.

```text
events waiting:  [E5] [E4] [E3] [E2] → clerk → done: [E1]
                                one at a time
```

### Why one careful clerk is a good thing

Order matters. For one book, the story must play out in sequence:
*reserved*, then *borrowed*, then *returned*. If a fast clerk handled
"returned" before a slow clerk finished "borrowed", the book's story
would come out scrambled.

One line + one clerk makes order automatic. Nothing can overtake
anything. That simplicity is why the system starts this way.

### Why it becomes a ceiling

The math is unforgiving: if handling one envelope takes 50 milliseconds,
one clerk can do at most ~20 per second. **It does not matter how many
API servers you add** — they only make envelopes arrive *faster*. The
line grows, and the "consumer lag" number the worker logs is literally
the length of that line.

A load test made this visible: borrows poured in from 8 API servers, one
clerk processed them one by one, and hundreds of books sat waiting in
RESERVED. Worse, if the line gets longer than the reservation TTL (section
5), the reaper starts compensating reservations that were otherwise valid.
Fencing keeps both contexts consistent, but queue slowness now causes
legitimate borrows to be cancelled instead of merely delayed.

### The fix: more lines, with one trick

The obvious fix is more lines (partitions) and more clerks (worker
instances) — one clerk per line, working in parallel. But doesn't that
scramble the order we just said we need?

Here is the trick: **order only matters inside one aggregate stream**. The
Catalog story for book A must stay in sequence, but it does not care what is
happening to book B. The Lending story for a loan has its own stream. So the
rule is:

> All envelopes from the same aggregate always go into the same line.

Kafka does this with the message **key**. The Debezium setup already
stamps every event with its aggregate ID (book ID for Catalog events, loan ID
for Lending events) as its key,
and Kafka routes by key: same key → same line, always. So:

```text
line 1:  book A reserved → book A borrowed         → clerk 1
line 2:  book B reserved → book B released         → clerk 2
line 3:  loan C created  → loan C completed        → clerk 3
```

Each aggregate's story stays in order. Different aggregates proceed in
parallel. Cross-context delivery order is deliberately *not* assumed: exact
reservation/loan identities, generation fences, and idempotent handlers make
late or duplicate messages safe.

We lose only one thing: the order *between* different books ("did A's
borrow happen before B's?"). Nothing in this system depends on that, so
it costs nothing.

### How this system does it

This is implemented here — a load test found the ceiling, so the ceiling
was removed:

- **Four lines per topic.** The Debezium connectors declare the shape of
  the topics they produce to (`topic.creation.default.partitions: 4` in
  `deploy/debezium/register-*.json`) — the component that owns the
  topics declares what they need, in the same reviewed config file that
  defines the connector.
- **Two clerks per worker.** The `event-worker` and `es-sync` services
  run 2 replicas each (`deploy.replicas`). They join the same consumer
  group and Kafka spreads the lines across them automatically — no code
  changes were needed, because the consumer was already group-based.
- **Aggregate ordering survives.** Debezium keys every message by aggregate
  ID. Cross-aggregate choreography relies on correlation and fencing, not a
  global order Kafka does not provide.

### Tuning it

- **Partitions are the ceiling on clerks**: with 4 partitions, at most 4
  workers per topic can do useful work. Choose partition count above the
  worker count you expect to ever need (partitions are cheap; changing
  them later on a busy topic momentarily blurs key ordering — do it when
  lag is zero).
- **Workers are the dial you actually turn**: scale replicas up or down
  freely; Kafka rebalances the lines within seconds.
- **Consumer lag is the meter**: the worker logs it every minute. Lag
  that grows during normal traffic means add workers; lag near the
  reservation TTL (section 5) means add them urgently, because a slow
  queue starts making the reaper cancel healthy reservations.

---

## Quick glossary

| Term | Plain meaning |
| --- | --- |
| Saga | A multi-step job where every step commits on its own |
| Compensation | A new action that undoes a committed step |
| Semantic lock | An "in between" state (RESERVED) that holds a resource for a saga |
| TTL / reaper | A time limit + cleaner that frees leaked locks |
| Pivot | The step after which the saga cannot be cancelled, only finished |
| Idempotent | Safe to run twice; the second run changes nothing |
| Dead-letter queue | A parking lot for messages that keep failing |
| Choreography | Steps react to each other's events; no boss |
| Orchestration | One component (a process manager) directs the steps |
| Apology | Fixing a rare conflict with human/business action instead of locks |
| Partition | One "line" inside a Kafka topic; order is guaranteed only within a line |
| Message key | Decides which line a message joins; same key → same line, always |
| Consumer lag | How many messages are waiting in line — the pipeline's staleness meter |
