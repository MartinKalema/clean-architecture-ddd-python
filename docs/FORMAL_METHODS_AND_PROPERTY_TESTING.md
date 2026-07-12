# Formal Methods and Property-Based Testing

## Purpose

Most tests describe examples that engineers already thought about. They are
necessary, but concurrent and stateful systems can behave in more ways than a
team can list manually.

This guide explains how to test the rules that must always hold across many
inputs, operation sequences, and event orderings. It covers:

- example-based tests;
- property-based tests;
- stateful and model-based tests;
- real database concurrency tests;
- formal specifications and model checking; and
- how to decide which technique is appropriate for this library system.

Property-based testing and formal methods are related, but they are not the
same thing. Property-based tests execute implementation code with generated
examples. Formal methods use mathematics to describe and analyze a system,
usually at a simpler and more abstract level than the production code.

## The Problem They Solve

Consider a loan with these operations:

```text
create
extend
mark overdue
return
```

A few operations produce many possible sequences:

```text
create -> extend -> return
create -> return -> extend
create -> mark overdue -> return
create -> extend -> extend -> return -> return
```

Now add:

- different dates and durations;
- invalid input;
- two patrons;
- multiple books;
- simultaneous requests;
- retries before and after commit;
- process crashes;
- delayed and duplicated messages; and
- patron suspension or tier changes during checkout.

The number of combinations grows quickly. Example tests cover the cases the
engineer selected. Property-based testing generates many more cases. Model
checking explores every behavior in a deliberately bounded abstract model.

The goal is not to generate more tests for its own sake. The goal is to find a
short sequence that breaks a rule the system promised never to break.

## Terms Used in This Guide

- An **example test** checks one input or scenario chosen by an engineer.
- A **property** is a statement that should remain true for every valid input
  or operation sequence in a defined range.
- A **generator** creates test inputs or chooses the next test operation.
- **Shrinking** reduces a generated failure to a smaller example that is easier
  to understand and reproduce.
- A **state machine** describes the current state, the operations allowed from
  that state, and the rules that must hold after each operation.
- A **reference model** is a deliberately simple implementation of expected
  behavior. Tests compare the real implementation with it.
- A **formal specification** is a mathematical description of a system's state
  and allowed changes.
- A **model checker** explores the states and operation orderings allowed by a
  formal specification.
- A **safety property** says that something bad never happens. “A book never
  has two outstanding loans” is a safety property.
- A **liveness property** says that something good eventually happens. “Every
  accepted notification is eventually processed or quarantined” is a liveness
  property.
- An **error trace** is the sequence of steps that led to a failed property.
- **State explosion** happens when a model contains so many combinations that
  exhaustive exploration becomes too expensive.

## The Verification Ladder

These techniques complement one another. Higher levels do not make the lower
levels unnecessary.

| Level | What it checks | Library example |
|---|---|---|
| Example test | One selected scenario | Returning an active loan changes its status to returned |
| Parameterized test | A selected scenario with several listed values | Active, overdue, and lost loans all occupy the book's checkout slot |
| Property-based test | A general rule across generated values | Every positive duration produces a due date after the borrow date |
| Stateful property test | A rule across generated operation sequences | No sequence of extend, overdue, and return creates an impossible Loan state |
| Model-based test | Real behavior compared with a simpler model | Command receipts and created loans agree after generated retries |
| Concurrency integration test | Real transaction and database behavior | Twenty simultaneous borrows produce at most one outstanding loan for a book |
| Formal model checking | Every behavior in a bounded abstract design | All allowed checkout interleavings preserve book exclusivity and patron capacity |
| Theorem proving | A mathematical proof over a formal definition | Reserved for algorithms whose risk justifies the much higher cost |

Most application teams need the first six levels. Formal model checking becomes
valuable when independent processes, nontrivial retries, message ordering, or
rare concurrency failures make the design difficult to reason about manually.

## Example-Based Testing

An example test tells a clear business story:

```python
def test_returning_an_active_loan_completes_it():
    loan = make_active_loan()

    changed = loan.return_book(returned_at)

    assert changed is True
    assert loan.status is LoanStatus.RETURNED
    assert loan.returned_at == returned_at
```

Its strengths are readability and precise intent. When it fails, the scenario
is usually obvious.

Its limitation is selection bias. It checks only the path and values the author
chose. The author may never consider returning at the exact borrow timestamp,
extending repeatedly, or attempting an extension after a return.

Keep example tests for important business stories even after adding generated
tests. They serve as executable documentation.

## Property-Based Testing

Property-based testing reverses the usual emphasis:

```text
Example test:
Given this input, expect this output.

Property test:
For every generated input in this valid range, this rule must hold.
```

For Python, Hypothesis is a commonly used property-based testing library. A
Hypothesis strategy describes the values to generate. If a generated example
fails, Hypothesis attempts to shrink it to a smaller failing example.

### Example: loan duration

The requirement is:

> Every accepted loan duration is positive, and the resulting due date is later
> than the borrowing time.

An illustrative property test would be:

```python
from datetime import datetime, timezone

from hypothesis import given, strategies as st


@given(days=st.integers(min_value=1, max_value=3650))
def test_positive_duration_always_moves_due_date_forward(days: int):
    borrowed_at = datetime(2026, 7, 12, tzinfo=timezone.utc)

    loan = Loan.create(
        patron_id="patron-1",
        patron_email="patron@example.com",
        catalog_book_id="book-1",
        book_title="Domain Design",
        loan_duration_days=days,
        borrowed_at=borrowed_at,
    )

    assert loan.due_date.value > borrowed_at
```

This does not prove the property for every integer. It tests many values chosen
by the tool, with emphasis on useful edge cases. The range is part of the test's
claim. Values outside it are not covered.

### Example: return time

We can express two related properties:

```text
If returned_at is before borrowed_at, the return must be rejected.

If returned_at is equal to or after borrowed_at, the return may complete the
loan without creating an impossible state.
```

A useful generator should produce values on both sides of the boundary,
including equality. Generating only ordinary dates would miss the boundary
where most date bugs live.

### Good properties for `Loan`

After construction or every successful transition:

- `due_date` is later than `borrowed_at`;
- `returned_at` is never earlier than `borrowed_at`;
- `status == returned` exactly when `returned_at` is present;
- returning the same loan twice emits at most one completion event;
- extending a loan moves its due date forward;
- a returned, overdue, or otherwise ineligible loan rejects operations that
  require an active loan; and
- every emitted event describes the aggregate state that produced it.

These are stronger than checking a few expected field values. They describe
the shape of every valid loan.

## How Shrinking Helps

Suppose a generated test finds this failing sequence:

```text
create with 37-day duration
extend by 41 days
extend by 9 days
return
return again
extend by 23 days
```

The true failure may require only:

```text
create
return
extend by 1 day
```

A shrinker tries to remove operations and reduce values while preserving the
failure. A short counterexample is easier to debug, turn into a permanent
regression test, and explain during review.

Shrinking depends on deterministic tests. If the same sequence sometimes
passes and sometimes fails because of uncontrolled time, networking, or random
state, the tool cannot reliably minimize it.

## Stateful Property Testing

A normal property test generates values for one test function. A stateful test
generates a sequence of operations. It is useful when the result of the next
operation depends on what happened earlier.

For `Loan`, the state machine might provide these rules:

```text
CreateLoan
ExtendLoan(days, current_time)
MarkOverdue(current_time)
ReturnLoan(returned_at)
```

After every rule, it checks the loan invariants.

Illustrative Hypothesis structure:

```python
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule


class LoanStateMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.loan = make_active_loan()

    @rule(days=st.integers(min_value=-10, max_value=30))
    def extend(self, days: int):
        try:
            self.loan.extend(days, current_time=NOW)
        except DomainException:
            pass

    @rule(offset_days=st.integers(min_value=-2, max_value=60))
    def return_loan(self, offset_days: int):
        returned_at = self.loan.borrowed_at + timedelta(days=offset_days)
        try:
            self.loan.return_book(returned_at)
        except DomainException:
            pass

    @invariant()
    def returned_state_and_timestamp_agree(self):
        assert (self.loan.status is LoanStatus.RETURNED) == (
            self.loan.returned_at is not None
        )

    @invariant()
    def dates_remain_possible(self):
        assert self.loan.due_date.value > self.loan.borrowed_at
        if self.loan.returned_at is not None:
            assert self.loan.returned_at >= self.loan.borrowed_at
```

This is an example of the testing structure, not code currently installed in
this repository. If the project adopts it, Hypothesis must be added as a test
dependency and the exact expected behavior for rejected operations must be
specified.

### Do not hide failures with `except`

The example catches domain exceptions because some generated operations are
intentionally invalid. A production test must still distinguish:

- an expected business rejection;
- an unexpected domain exception;
- an infrastructure or programming failure.

Catching every exception and continuing would make the test meaningless.

## Model-Based Testing

Stateful testing becomes model-based when the test maintains a simple reference
model and compares it with the real implementation.

For idempotent checkout, the reference model could be:

```python
class BorrowModel:
    outstanding_by_book: dict[str, str]
    response_by_key: dict[str, BorrowBookResult]
```

Generated operations might include:

```text
borrow(book, patron, key)
retry(book, patron, same_key)
reuse_key_with_different_book(key)
return(loan)
```

After each operation, compare the implementation with the simple model:

```text
The same key and request facts return the original loan.
A key reused with different facts is rejected.
A book has at most one outstanding loan.
A returned loan releases the book for a later checkout.
```

The reference model must be simpler than the implementation. Copying the
production algorithm into the test risks reproducing the same bug in both
places.

## Concurrency Tests Are a Separate Requirement

Property-based tests are not automatically concurrency tests. Generating many
sequential calls does not reproduce two transactions that make decisions from
the same database snapshot.

The checkout invariant is:

> For every book, at most one loan may have `returned_at IS NULL`.

A real PostgreSQL test should start several borrow attempts together and then
query the committed state:

```text
Arrange:
  one book
  several eligible patrons

Act:
  release 20 borrow requests at the same time

Assert:
  at most one request commits an outstanding loan
  the database contains at most one outstanding loan for the book
  rejected requests receive the expected conflict
```

This test verifies behavior that an in-memory repository cannot prove:

- transaction isolation;
- advisory lock behavior;
- partial unique index behavior;
- database error translation; and
- what becomes visible after commit.

Generated values can strengthen the concurrency test by varying the number of
requests, books, patrons, and retry keys. The database must remain real.

## Why the Database Constraint Matters

This application check is insufficient by itself:

```python
if await loans.get_active_loan_for_book(book_id) is None:
    await loans.add(new_loan)
```

Two transactions can interleave:

```text
Request A reads: no loan
Request B reads: no loan
Request A inserts a loan
Request B inserts a loan
```

The partial unique index provides the final enforcement point:

```sql
CREATE UNIQUE INDEX ix_loans_outstanding_book_unique
ON loans (catalog_book_id)
WHERE returned_at IS NULL;
```

The property test states the rule. The concurrency integration test challenges
the real implementation. The database constraint prevents the invalid commit.
All three serve different purposes.

## What Formal Methods Add

Testing asks the implementation to handle selected or generated executions.
Formal specification asks us to define the design precisely enough that a tool
can analyze its possible behaviors.

A formal model normally contains:

- a small set of state variables;
- the allowed starting states;
- the actions that may change state;
- which steps are atomic;
- safety properties;
- liveness properties when required; and
- assumptions about failures, fairness, and external systems.

The model deliberately omits details that do not affect the property. A checkout
model may represent a patron as an ID and a capacity number. It does not need to
represent the patron's name, HTTP JSON, SQLAlchemy, or email template.

## Safety and Liveness

### Safety: bad things never happen

Library examples:

- one book never has two outstanding loans;
- a patron never exceeds the capacity enforced by the checkout policy;
- a returned loan never becomes active again;
- one idempotency key never identifies two different successful outcomes; and
- a delayed event never changes a newer workflow.

Safety violations have a finite bad prefix: a sequence reaches a state that is
already invalid. A model checker can show that sequence as an error trace.

### Liveness: good things eventually happen

Library examples:

- a committed notification obligation is eventually processed or quarantined;
- a projection eventually catches up after a temporary outage; and
- a claimed workflow is eventually completed, released, or made visible for
  recovery.

Liveness requires assumptions. A notification cannot eventually process if the
worker is allowed to remain stopped forever. The model must state what is
assumed about retries, scheduling, and recovery.

Do not describe a liveness promise as “eventually” without a business deadline
or an operational signal. Otherwise the system can be wrong forever while
technically still claiming it may recover later.

## Modeling Checkout

An abstract checkout model needs to represent only the facts relevant to the
rules:

```text
State:
  loans
  returned loans
  patron capacity usage
  command receipts

Actions:
  begin borrow
  check patron capacity
  insert loan
  record command result
  return loan
  retry command
```

The important modeling decision is which actions are atomic.

If “check availability and insert loan” is modeled as one atomic action, the
model cannot reveal a race between the check and insert. To study that race, the
model must split them:

```text
A checks book
B checks book
A inserts
B inserts
```

Without database enforcement, that trace can violate book exclusivity. With an
atomic unique constraint at insert, one insert is rejected and the invariant
holds.

The model can apply the same reasoning to patron capacity:

```text
A counts patron loans
B counts patron loans
A approves
B approves
A inserts
B inserts
```

If both counts can occur outside the shared admission fence, the patron can
exceed the limit. The current design serializes the capacity decision for one
patron so that the count and insert belong to one ordered admission process.

## Simplified TLA+ Shape

TLA+ is a language for specifying systems as states and actions. TLC is a model
checker that can explore a finite model of the specification.

The following is intentionally a shape, not a complete copy-and-run
specification:

```tla
VARIABLES outstandingLoans, returnedLoans, receipts, patronUsage

Init ==
  /\ outstandingLoans = {}
  /\ returnedLoans = {}
  /\ receipts = [key \in Keys |-> NoLoan]
  /\ patronUsage = [patron \in Patrons |-> 0]

Borrow(patron, book, key, loan) ==
  /\ receipts[key] = NoLoan
  /\ BookIsAvailable(book)
  /\ patronUsage[patron] < MaxLoans[patron]
  /\ outstandingLoans' = outstandingLoans \cup {loan}
  /\ receipts' = [receipts EXCEPT ![key] = loan]
  /\ patronUsage' = [patronUsage EXCEPT ![patron] = @ + 1]
  /\ UNCHANGED returnedLoans

Return(patron, loan) ==
  /\ loan \in outstandingLoans
  /\ outstandingLoans' = outstandingLoans \ {loan}
  /\ returnedLoans' = returnedLoans \cup {loan}
  /\ patronUsage' = [patronUsage EXCEPT ![patron] = @ - 1]
  /\ UNCHANGED receipts

BookExclusive ==
  \A book \in Books:
    Cardinality({loan \in outstandingLoans: LoanBook[loan] = book}) <= 1

CapacityRespected ==
  \A patron \in Patrons:
    patronUsage[patron] <= MaxLoans[patron]
```

A real specification must define `BookIsAvailable`, the loan-to-book and
loan-to-patron relationships, type constraints, retry behavior, atomic steps,
and the complete `Next` relation. The simplified example shows the purpose:
state the allowed changes and ask the model checker whether every reachable
state satisfies the invariants.

## Model Checking the Former Saga

The removed Catalog/Lending saga is a better formal-methods example than the
current single-transaction checkout because it had more independent state and
message orderings.

Its state included:

```text
Catalog:
  available | reserved | borrowed

Lending:
  no loan | active | returned | cancelled

Messages:
  book reserved
  loan created
  borrow confirmed
  reservation released
  loan completed
```

The model would allow messages to be delayed, duplicated, and delivered after
newer work. It would explore traces such as:

```text
reserve book for patron A
create loan for patron A
reservation for A expires
reserve book for patron B
deliver the delayed confirmation for patron A
deliver the delayed return for patron A
```

Relevant safety properties would be:

- patron A's delayed event never changes patron B's reservation;
- Catalog never confirms a loan that does not exactly match its reservation;
- one book never has two outstanding Lending loans; and
- a completed old loan never releases a newer checkout.

Relevant liveness properties would be:

- every reservation eventually becomes a confirmed loan or is released; and
- every accepted return eventually makes the book available for a later
  checkout.

Fencing tokens and exact workflow identities were necessary to preserve those
properties after the architecture introduced independent commits. The better
solution for the current requirements was to remove the duplicated circulation
state and the saga. Formal reasoning is useful not only for adding coordination;
it can reveal that moving the consistency boundary removes the difficult state
space entirely.

## What a Passing Model Does and Does Not Prove

A passing model proves only the claim encoded by that model under its stated
bounds and assumptions.

It does not automatically prove:

- that the Python code matches the model;
- that SQL transaction behavior matches the modeled atomic steps;
- that the model includes every relevant failure;
- that the requirements themselves are correct;
- that larger bounds contain no new problem; or
- that performance, security, and operability requirements are satisfied.

The gap between specification and implementation is called the refinement gap.
Reduce it by:

- keeping model actions close to named application operations;
- documenting which database statement provides each atomic step;
- deriving implementation tests from model error traces and invariants;
- reviewing the model and code together when the workflow changes; and
- running real integration and concurrency tests in addition to model checking.

## Choosing the Right Technique

Use the lowest-cost technique that gives sufficient confidence for the risk.

| Situation | Recommended starting point |
|---|---|
| Pure value validation | Example and property-based tests |
| Aggregate with several transitions | Example tests plus stateful property tests |
| Idempotent application workflow | Model-based sequence tests plus integration tests |
| Database uniqueness or capacity rule | Real migrated-database concurrency tests |
| Cache or search projection | State/sequence tests for freshness and fallback, plus operational lag tests |
| Cross-service workflow with retries and compensation | Formal model plus implementation replay and failure tests |
| Consensus, leader election, leases, or distributed locks | Formal specification and model checking strongly recommended |
| Money, safety, privacy, or irreversible data | Independent review and stronger formal/property techniques proportional to impact |

Formal modeling is probably unnecessary for the current book-exclusivity rule
alone. PostgreSQL provides a direct constraint, and a real concurrency test can
exercise it. Formal modeling becomes more valuable if checkout once again spans
independent databases, includes payment or scarce external inventory, or gains
complex retry and compensation rules.

## Deriving Properties From Requirements

Do not begin with a testing tool. Begin with the validated requirement.

```text
Requirement
  -> rule that must hold
  -> state and operations that can break it
  -> testing or modeling technique
  -> enforcement mechanism
  -> evidence
```

Example:

```text
Requirement:
  One book cannot be checked out twice.

Property:
  For every book, outstanding loan count is at most one.

Risky operations:
  simultaneous borrow, retry after timeout, return racing with borrow.

Technique:
  generated sequential model tests plus real PostgreSQL concurrency tests.

Enforcement:
  partial unique index where returned_at is null.

Evidence:
  migrated-database test and production constraint monitoring.
```

## A Repeatable Property-Test Workflow

1. Write the requirement in observable language.
2. State the property without referring to the implementation.
3. Identify the smallest state needed to evaluate the property.
4. List the operations that can change that state.
5. Define valid and invalid generated inputs, including boundary values.
6. Decide whether the test needs sequences, concurrency, or a reference model.
7. Run the property after every generated step, not only at the end.
8. Preserve the smallest discovered failure as a readable regression example.
9. Confirm that the production enforcement mechanism matches the tested rule.
10. Record the property and evidence in the requirement traceability matrix.

## A Repeatable Formal-Model Workflow

1. Select one high-risk workflow or algorithm. Do not model the entire
   application.
2. Write its safety and liveness properties in plain language first.
3. Choose only the state variables relevant to those properties.
4. Define the initial state and allowed actions.
5. Make atomicity explicit. Split steps when another process can interleave.
6. Add failure behavior, duplication, delay, retry, and stale work where they
   affect the property.
7. Use small finite sets for the first model.
8. Run the model checker and inspect every error trace.
9. Fix the design, not merely the trace.
10. Translate the corrected design into database constraints, application
    rules, and implementation tests.
11. Store the model beside the design documentation and run it in CI when the
    workflow risk justifies the cost.
12. Update the model whenever requirements, atomicity, or failure assumptions
    change.

## Common Mistakes

### Writing a property that repeats the implementation

If both the test and production code calculate the answer using the same
algorithm, they may contain the same mistake. Prefer independent rules and
simple reference models.

### Generating mostly invalid data

If nearly every generated operation is rejected before reaching meaningful
state, the test explores little useful behavior. Generate valid paths often and
add targeted invalid boundaries deliberately.

### Catching every exception

Broad exception handling can convert programming failures into apparent
success. Classify expected domain rejection separately from unexpected errors.

### Mocking the property away

An in-memory repository cannot verify PostgreSQL isolation or uniqueness. Use
real infrastructure when the property depends on that infrastructure.

### Assuming random means exhaustive

Property-based testing explores many generated cases, not every possible case.
Record generator ranges and avoid claims broader than the tested domain.

### Modeling the implementation line by line

A formal model that includes HTTP, ORM, logging, and serialization details will
become too large and obscure the design question. Model only the state and
actions relevant to the chosen properties.

### Hiding atomicity

Combining a read, decision, and write into one model action can make a race
impossible in the model even when it is possible in production.

### Ignoring liveness assumptions

“Eventually processed” is false if the worker may remain stopped forever.
State the scheduling, retry, and recovery assumptions explicitly.

### Treating the tool as proof that the requirement is correct

A model checker can prove that a model satisfies a property. It cannot decide
whether the business needed that property. Requirement validation still comes
first.

## Recommended Adoption for This Repository

### Phase 1: domain properties

Add Hypothesis as a test dependency and create generated tests for:

- positive loan duration;
- return-date boundaries;
- extension boundaries;
- agreement between status and `returned_at`;
- event emission after repeated transitions; and
- normalization and validation value objects.

Suggested location:

```text
tests/domain/test_loan_properties.py
```

### Phase 2: stateful loan testing

Create a `RuleBasedStateMachine` that generates extend, overdue, and return
sequences. Check the Loan invariants after every operation and preserve small
failures as ordinary domain tests.

Suggested location:

```text
tests/domain/test_loan_state_machine.py
```

### Phase 3: generated application workflows

Create a small reference model for books, patrons, loans, returns, and
idempotency receipts. Generate borrow, retry, key-reuse, and return sequences.
Compare the application result with the reference model.

Suggested location:

```text
tests/application/test_borrow_model.py
```

### Phase 4: stronger database concurrency

Parameterize real PostgreSQL tests over request counts, patrons, books, and
capacity boundaries. Keep explicit synchronization so requests genuinely
overlap. Assert committed database state, not only HTTP responses.

Suggested location:

```text
tests/integration/test_borrow_concurrency_properties.py
```

### Phase 5: formal model only when justified

Do not introduce TLA+ merely to claim formal-methods usage. Add a model when a
workflow has independently committed steps, difficult retry ordering, leases,
distributed locks, compensation, money movement, or another state space whose
failure impact justifies maintaining the specification.

A future model could live at:

```text
specifications/borrowing/README.md
specifications/borrowing/Borrowing.tla
specifications/borrowing/Borrowing.cfg
```

Its README should state the requirements, modeled assumptions, checked bounds,
properties, commands, and relationship to implementation tests.

## Review Template

```markdown
### Property or model review

Validated requirement:
Property in plain language:
Safety or liveness:
State included:
State deliberately omitted:
Operations/actions:
Atomic steps:
Concurrency and failure assumptions:
Generated input ranges or model bounds:
Reference model, if any:
Production enforcement mechanism:
Evidence produced:
Known gaps:
Change that requires this test/model to be updated:
```

## Review Checklist

- Can a reader understand the property without reading the implementation?
- Does the property trace to a validated requirement?
- Are boundary values and meaningful operation sequences generated?
- Does the test check the rule after every relevant step?
- Are expected business rejections separated from unexpected failures?
- Does the test use real infrastructure when the property depends on it?
- Are concurrency and atomicity represented honestly?
- Are generator ranges, model bounds, and assumptions documented?
- Is the reference model simpler and independent from the production code?
- Does every formal error trace become a design correction and implementation
  test where appropriate?
- Is the maintenance cost justified by the impact and complexity of the
  workflow?

## Further Reading

- [Hypothesis documentation](https://hypothesis.readthedocs.io/en/latest/)
- [Hypothesis stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html)
- [Learn TLA+ conceptual overview](https://www.learntla.com/intro/conceptual-overview.html)
- [Learn TLA+ safety and liveness](https://www.learntla.com/core/temporal-logic.html)
- [Leslie Lamport's TLA+ resources](https://lamport.azurewebsites.net/tla/tla.html)

## Related Project Guides

- [Engineering Design System](ENGINEERING_DESIGN_SYSTEM.md)
- [Design to Requirements](DESIGN_TO_REQUIREMENTS.md)
- [Invariant-Driven Architecture](INVARIANT_DRIVEN_ARCHITECTURE.md)
- [Sagas and Consistency](SAGAS_AND_CONSISTENCY.md)
