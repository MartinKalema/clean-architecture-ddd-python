# Design to Requirements

## Purpose

Design to requirements is the discipline of establishing what a system must
accomplish before selecting how it will accomplish it.

The governing order is:

```text
Real-world outcome
    -> validated requirement
    -> test or measurement that will prove it
    -> design
    -> test results and production evidence
```

This prevents teams from completing a design and then interpreting the
requirements until the design appears compliant. It also prevents precise but
unnecessary requirements from becoming expensive architecture.

This guide defines a repeatable method that engineers can use for product,
software, infrastructure, security, and operational design.

## Core Principle

> Requirements define the obligations. Design satisfies them.

This principle has an important qualification:

> A requirement must be validated before it is treated as an obligation.

A precise, testable requirement can still describe the wrong problem. Before
design begins, the team must understand its source, evidence, engineering
intent, and consequence of removal.

## Verification and Validation

These questions are different:

- **Validation:** Are we defining the right problem and requirement?
- **Verification:** Did the implemented design satisfy the validated
  requirement?

Example:

> Catalog and Lending shall contain matching availability fields within five
> seconds.

This is verifiable, but validation should reject it if the business never
needed two availability fields. Verification cannot rescue an unnecessary
requirement.

## Requirement Hierarchy

Do not mix these levels:

| Level | Question | Library example |
|---|---|---|
| Outcome | What must the user or business accomplish? | An eligible patron borrows an available book |
| Real-world constraint | What condition exists independently of our design? | One physical copy cannot be held by two patrons simultaneously |
| System requirement | What must the system guarantee or provide? | At most one outstanding loan may exist for a book |
| Verification criterion | What observation proves compliance? | Concurrent checkout attempts produce exactly one committed loan |
| Design decision | How will the system satisfy it? | A partial unique PostgreSQL index |
| Implementation task | What code or configuration must change? | Add the index and translate its conflict |

A design decision must not be promoted into a requirement merely because it
already exists.

## Requirement Classification

Every requirement must be classified because different categories need
different evidence and enforcement.

| Category | Meaning | Typical evidence or enforcement |
|---|---|---|
| Business truth | A condition fundamental to a valid business outcome | Domain model, transaction, database constraint |
| Functional behavior | Something the system must do | Acceptance test |
| Business policy | A changeable business rule | Policy object, examples, approval record |
| Service-level objective (SLO) | A measurable target for reliability or performance | Production metric and alert |
| Security requirement | A threat or control that must be addressed | Threat model, control test, audit evidence |
| Legal or regulatory constraint | An externally imposed obligation | Cited regulation and compliance interpretation |
| External contract | A protocol or partner obligation | Versioned contract and compatibility test |
| Operability requirement | A property required to run or recover the system | Runbook exercise, backup restore, failure test |
| Assumption | Something currently believed but not guaranteed | Explicit validation plan and expiry condition |
| Design constraint | A justified restriction on implementation choices | Decision record with tradeoff evidence |

An assumption is not a requirement. It becomes one only after validation.

## Requirement Quality Standard

A requirement is ready for design when it is:

- **Necessary:** removing it causes an identified unacceptable outcome.
- **Intentional:** its engineering purpose and use scenario are understood.
- **Solution-neutral:** it states the obligation without prematurely selecting
  an implementation, unless an external constraint genuinely mandates one.
- **Specific:** scope, conditions, thresholds, units, and timing are explicit.
- **Unambiguous:** reasonable readers reach the same interpretation.
- **Singular:** it does not hide several independently testable obligations in
  one sentence.
- **Feasible:** the team has evidence that it can be satisfied within accepted
  cost and risk.
- **Verifiable:** a test, analysis, inspection, demonstration, or production
  measurement can prove it.
- **Traceable:** engineers can find where it came from, which part of the
  design satisfies it, and which test or measurement proves it.
- **Bounded:** it avoids undefined absolutes such as “always fast” or “never
  fails.”

## The Design-to-Requirements Workflow

### 1. Describe the outcome and scenario

Write the real-world situation without naming a framework or component.

```text
Given an eligible patron and a book with no outstanding loan,
when the patron borrows the book,
the system records one loan with terms determined by Lending policy.
```

Ask what happens before, during, and after the outcome. Include exceptional and
concurrent scenarios, not only the happy path.

### 2. Establish source, evidence, and removal consequence

For each proposed requirement, record:

- Where did it come from?
- What evidence supports it?
- What failure does it prevent?
- What happens if it is removed?
- Is it a truth, policy, SLO, external constraint, or assumption?

A named decision owner may help clarify or approve a policy, but authority is
not evidence. Physics, law, measured behavior, an external contract, or a
business invariant may be the actual source.

### 3. Extract the engineering intent

Do not design against literal wording until the use scenario is understood.

Weak interpretation:

> “Handle 1,000 requests per second” means add Kafka.

Engineering intent:

> The checkout path must sustain 1,000 requests per second for ten minutes
> while preserving checkout correctness and a stated latency percentile.

The intent identifies what must survive. It does not prescribe the mechanism.

### 4. Classify and resolve conflicts

Classify each requirement using the preceding table. Then identify conflicts:

- consistency versus availability;
- latency versus durability;
- retention versus privacy;
- independence versus atomicity;
- simplicity versus configurability;
- delivery speed versus migration safety.

Do not allow different engineers to silently resolve the same conflict in
different directions.

### 5. Make the requirement precise

Use this structure:

```text
Under <conditions>,
the <system or capability>
shall <observable behavior>
within/while <threshold or constraint>,
as verified by <method>.
```

Example:

```text
Under concurrent checkout attempts for the same catalog book,
Lending shall commit at most one loan whose returned_at is null,
as verified by a migrated-PostgreSQL concurrency test.
```

### 6. Define verification before design

Select the evidence that will prove the requirement:

| Verification method | Use when |
|---|---|
| Automated test | Behavior can be executed deterministically |
| Property or model test | Many state combinations or sequences matter |
| Database constraint inspection | Persistence must reject invalid state |
| Static analysis | Dependency, type, or security rules can be checked without execution |
| Performance experiment | Percentiles, throughput, or resource limits matter |
| Failure exercise | Recovery, degradation, retry, or failover is required |
| Inspection | Structure or configuration must match a standard |
| Production measurement | The requirement is an SLO or emergent system property |

“We will test it later” means the requirement is not ready.

### 7. Design from the obligations

For each design element, state which requirement it satisfies. Prefer the
smallest mechanism that produces the required evidence.

```text
Requirement: at most one outstanding loan per book
Design: partial unique index
Evidence: concurrent database test
```

Avoid adding mechanisms for hypothetical future requirements. Record the
measured trigger that would justify adding them later.

### 8. Verify in both directions

Perform two traceability checks:

```text
Requirement -> design element -> verification evidence
Design element -> requirement or accepted engineering constraint
```

The first prevents missing behavior. The second exposes unnecessary
architecture.

### 9. Revalidate when design reveals new information

Engineering is iterative. A design may reveal that a requirement is infeasible,
contradictory, more expensive than its value, or based on a false assumption.
Return to requirement validation rather than hiding the discovery in code.

### 10. Control requirement changes

When a requirement changes:

1. update its source, intent, and classification;
2. identify affected invariants and design decisions;
3. update verification criteria before implementation;
4. change the design and code;
5. retain evidence that the new requirement is satisfied; and
6. remove design elements that no longer have a justification.

## Requirement Record Template

```markdown
### REQ-<id>: <short name>

Outcome:
Scenario:
Requirement:
Classification:
Source:
Supporting evidence:
Failure prevented:
Consequence if removed:
Assumptions:
Conflicts/tradeoffs:
Verification method:
Acceptance threshold:
Related invariants:
Related design decisions:
Decision owner, if organizationally necessary:
Status: proposed | validated | implemented | verified | retired
```

## Traceability Matrix

Maintain this for material system requirements:

| Requirement | Classification | Design mechanism | Verification | Evidence location | Status |
|---|---|---|---|---|---|
| REQ-LEND-001: one outstanding loan per book | Business truth | Partial unique index | Concurrent PostgreSQL test | `tests/integration/test_loan_constraints.py` | Verified |
| REQ-LEND-002: command retry does not duplicate a loan | Functional/reliability | Transactional command receipt | Replay test | `tests/integration/test_use_cases.py` | Verified |
| REQ-NOTIFY-001: email failure does not invalidate a loan | Availability boundary | Post-commit notification consumer | Handler-failure test | `tests/application/test_event_handlers.py` | Verified |

## Review Checklist

Before design approval:

- Is the real-world outcome clear?
- Is the requirement source evidence rather than authority alone?
- Is the removal consequence concrete?
- Is the requirement classified correctly?
- Is it solution-neutral?
- Are scope, conditions, thresholds, units, and timing explicit?
- Can verification be written now?
- Are conflicts with other requirements resolved?
- Are assumptions explicit and time-bounded?
- Does every proposed component trace to a requirement?

Before release approval:

- Does every validated requirement trace to an implemented design element?
- Does every material design element still have a justification?
- Has verification run in the production-relevant environment?
- Are SLOs measured in production rather than inferred from tests?
- Are failure and recovery requirements exercised?
- Have obsolete requirements and components been removed?

## Common Failure Modes

### Designing first and checking afterward

The team becomes emotionally and financially attached to the design, then
interprets ambiguous requirements in its favor.

### Treating a technology choice as a requirement

“Use Kafka” is normally a design decision. The requirement might instead be
durable replay for multiple independently scaled consumers.

### Making a bad requirement precise

Precision improves verification, not validity. Validate intent and necessity
first.

### Testing only the happy path

Requirements involving uniqueness, capacity, retry, or consistency must name
concurrency and failure conditions.

### Using unbounded language

“Always available,” “real time,” and “infinitely scalable” are not actionable
without a defined scope and threshold.

### Losing backward traceability

Components accumulate after the requirements that justified them disappear.
Regularly ask what constraint requires each one.

## Applied Example: Borrowing

### Outcome

An eligible patron borrows a book that is not currently on loan.

### Validated requirements

```text
REQ-LEND-001
At most one outstanding loan may exist for a catalog book.

REQ-LEND-002
The patron must be eligible and below the Lending capacity limit at commit.

REQ-LEND-003
Replaying the same accepted command must return the original loan without
creating another loan.

REQ-LEND-004
Notification failure must not roll back or invalidate an accepted loan.
```

### Derived design

- Lending owns circulation and availability.
- One Lending transaction performs checkout admission and loan creation.
- A partial unique index proves book exclusivity.
- A patron admission fence serializes capacity decisions.
- A command receipt proves HTTP retry identity.
- `LoanCreated` drives optional notification after commit.

### Rejected design constraint

> Catalog and Lending must commit circulation state independently.

It had no external, organizational, regulatory, scaling, or business evidence.
Removing it eliminated the reservation saga and its compensation, fencing,
worker, reaper, and polling state without weakening a validated requirement.

## Related Guides

- [Engineering Design System](ENGINEERING_DESIGN_SYSTEM.md)
- [Invariant-Driven Architecture](INVARIANT_DRIVEN_ARCHITECTURE.md)
- [Strategic DDD Guide](STRATEGIC_DDD_GUIDE.md)
- [Sagas and Consistency](SAGAS_AND_CONSISTENCY.md)
