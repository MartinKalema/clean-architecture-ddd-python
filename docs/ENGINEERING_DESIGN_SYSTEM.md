# Engineering Design System

## Purpose

This document combines design to requirements, invariant-driven architecture,
Domain-Driven Design, Clean Architecture, reliability engineering, and
question-delete-optimize discipline with engineering planning and execution
management into one method that engineering teams and individual engineers can
follow.

The method is intentionally technology-neutral. It does not require
microservices, event-driven architecture, DDD tactical patterns, or a specific
toolchain. It tells a team how to justify whatever it chooses.

## Governing Principle

> Validate the requirement, make it verifiable, derive the truths it implies,
> and design only what is necessary to preserve them.

The complete reasoning chain is:

```text
Understand the result people need
  -> write requirements we can test
  -> identify the rules that must never be broken
  -> decide which model is the source of truth for each fact
  -> choose the simplest design that satisfies those rules
  -> discover and sequence the complete delivery work
  -> execute while controlling time, quality, scope, and dependencies
  -> prove it works with tests and production measurements
  -> use what we learn to improve or simplify it
```

Each step prevents a different kind of failure:

- If the team has not agreed on the result people need, it can build a system
  correctly and still solve the wrong problem.
- If a requirement is vague, different engineers can read it differently and
  build incompatible behavior.
- If the team has not written down the rules that must never be broken,
  simultaneous requests, retries, and failures can leave invalid data behind.
- If two models are both allowed to change the same fact, their values can
  disagree and the team will not know which value is correct.
- If the team never asks whether a simpler design could satisfy the same
  requirements, unnecessary services, queues, workers, and processes will
  accumulate.
- If the complete work, dependencies, and decisions are not exposed before a
  deadline is accepted, the schedule is a date attached to an assumption.
- If execution is not actively controlled, unresolved decisions, capacity
  collisions, scope growth, and late transitions can defeat a good design.
- If the team does not verify the result, it has confidence based on opinion
  instead of evidence.
- If the team does not measure the system in production, it knows only that the
  design worked under test conditions—not that it works for real users and
  real failures.

## How the Disciplines Fit Together

| Discipline | Primary question | Contribution |
|---|---|---|
| Design to requirements | What must the system do, and how will we prove it? | Requirements that are necessary, clear, and testable |
| Invariant-driven architecture | Which rules must still hold when requests overlap or components fail? | A written model of valid state and the mechanisms that protect it |
| DDD | What does each business term mean, and which model is the source of truth? | Clear model boundaries and relationships between them |
| Clean Architecture | Which business rules should not depend on a database, framework, or delivery method? | Dependencies that point toward business policy, with replaceable external adapters |
| [Engineering planning and estimation](ENGINEERING_PLANNING_AND_ESTIMATION.md) | What must be understood, decided, built, verified, operated, and learned for the outcome to succeed? | Complete deliverables, dependencies, uncertainty, and a decision-useful forecast |
| [Execution management](ENGINEERING_EXECUTION_MANAGEMENT.md) | How will the promised outcome reach its deadline without sacrificing mandatory quality? | Backward scheduling, capacity control, evidence-based milestones, variance response, and early communication |
| [Delivery assurance](DELIVERY_ASSURANCE_GAPS.md) | What must happen beyond sound design for the change to reach users safely and remain supportable? | Risk-based release, migration, operational, security, data, and learning controls |
| SRE | How reliable must the service be, and how will we know? | Measurable reliability targets, monitoring, capacity planning, and recovery evidence |
| [Formal methods and property-based testing](FORMAL_METHODS_AND_PROPERTY_TESTING.md) | Which important combinations and event sequences are too numerous for a few example tests? | Systematic exploration of states and sequences that engineers may overlook |
| Question-delete-optimize discipline | What real constraint requires this component? | Removal of requirements and components that have no valid justification |

None of these methods is itself a business truth. They are different tools for
finding the business truths, representing them in a design, protecting them in
code, and proving that the finished system behaves correctly.

## Terms Used in This Guide

- A **requirement** states something the system must do or a limit it must
  respect.
- An **invariant** is a rule that valid system state must never break. For
  example, one book cannot have two outstanding loans.
- A **policy** is a business rule that the business may intentionally change,
  such as how many books a premium patron may borrow.
- A **service-level objective (SLO)** is a measurable reliability or performance
  target, such as 99.9% successful requests over 30 days.
- A **mutable fact** is simply a value that can change, such as a patron's
  suspension status or a loan's return date.
- The **authoritative model** is the one model allowed to decide and change a
  mutable fact. It is the source other models must trust.
- A **consistency promise** says when a fact must become true. It may need to be
  true in the committing transaction, before the response returns, or after a
  defined delay.
- A **derived view** is a copy built from authoritative data for reading,
  caching, or searching. It can be rebuilt and must not silently become the
  source of truth.
- An **architecture justification** explains which validated requirement a
  component satisfies, why a simpler design is insufficient, and how the team
  will verify the decision.
- A **quality bar** is the minimum acceptable result for one component of the
  complete outcome. Mandatory quality bars cannot be silently lowered to
  preserve a date.
- A **deadline** is the latest acceptable completion time imposed by a real
  business, contractual, regulatory, market, or coordination need.
- A **forecast** is the current predicted completion range based on evidence,
  assumptions, dependencies, and observed execution. It should change when the
  evidence changes.
- A **transition** is a moment when work, ownership, state, or authority moves,
  such as design to implementation, code to review, or one schema to another.
  Transitions usually carry more risk than steady work.

## The Seven-Stage Design Workflow

Each stage has required questions, documents, and an exit gate. An exit gate is
a decision about whether the team understands the current stage well enough to
move to the next one. The amount of
documentation should be proportional to risk. A small change may answer each
stage in one page or pull request; a critical distributed workflow may require
separate reviews and formal models.

## Stage 1: Frame the Outcome

### Questions

- Who needs something to change, and what do they need?
- What real-world scenario causes the need?
- What can we observe when the outcome succeeds?
- What is explicitly out of scope?
- What would make the outcome harmful or invalid?

### Artifact: outcome brief

```markdown
Outcome:
Primary scenario:
Exceptional scenarios:
Success observation:
Non-goals:
Known external constraints:
```

### Gate 1: problem accepted

The team agrees on the problem without relying on a proposed architecture for
its definition.

## Stage 2: Validate and Specify Requirements

Use [Design to Requirements](DESIGN_TO_REQUIREMENTS.md).

### Questions

- What is the source and evidence for each requirement?
- What failure appears if it is removed?
- Is it a truth, behavior, policy, SLO, threat control, external contract,
  assumption, or design constraint?
- Is it solution-neutral?
- Can verification be defined before design?
- Which requirements conflict?

### Artifacts

- requirement records;
- verification criteria;
- assumption log;
- initial traceability matrix.

### Gate 2: requirements ready

Material requirements are validated, classified, bounded, and verifiable.
Unknowns are recorded as assumptions with a validation plan rather than hidden
inside the design.

## Stage 3: Build the Correctness Model

Use [Invariant-Driven Architecture](INVARIANT_DRIVEN_ARCHITECTURE.md).

### Questions

- Which invalid states must never commit?
- Which facts may disagree temporarily?
- How long may they disagree?
- Which policies may change without redefining correctness?
- Which commands race?
- What happens under retry, timeout, crash, duplication, reordering, and stale
  work?
- What evidence would prove each invariant?

### Artifact: invariant catalog

| ID | Statement | Type | Scope | Enforcement | Evidence |
|---|---|---|---|---|---|
| INV-LEND-001 | One book has at most one loan with `returned_at IS NULL` | Hard | Lending/database | Transaction and unique index | Concurrent PostgreSQL test |
| INV-LEND-002 | A returned loan cannot become active again | Hard | Loan aggregate | State transition guard | Domain sequence test |
| CONV-NOTIFY-001 | A committed loan is eventually presented to the notification handler | Convergence | Outbox/notification | Durable event delivery | Inbox and lag evidence |

### Gate 3: correctness review

Every material requirement is either represented by an invariant, policy,
SLO, external contract, or explicit acceptance behavior. A rule that must never
be broken must be enforced before the relevant transaction commits. It cannot
depend only on a background process that may run later without a deadline.

## Stage 4: Assign Authority and Bound the Model

Use strategic DDD after the truths are known.

### Questions

- Which model is allowed to change each mutable fact?
- Where is each term unambiguous?
- Which rules must change together?
- Does a proposed boundary split a hard invariant?
- Is a cross-context copy authoritative or derived?
- Is a process/database boundary required, or only a model boundary?

### Artifacts

- authority table;
- bounded-context definitions;
- context map;
- aggregate and transaction boundaries;
- anti-corruption contracts for upstream facts.

Example authority table:

| Fact | Authority | Consumers |
|---|---|---|
| Book title and author | Catalog | Lending snapshot, search |
| Patron tier and suspension | Patron | Lending eligibility adapter |
| Loan existence, due date, and return | Lending | Book availability read model, notification |
| Search document | No business authority | Query handlers |
| Cache entry | No business authority | Query handlers |

### Gate 4: ownership review

Every value that can change has one authoritative model. If a rule must be
enforced in one transaction, the design does not split that rule across
independent transactions unless the business has explicitly accepted a period
of disagreement and its consequences.

## Stage 5: Derive the Minimum Architecture

### Questions

- What is the smallest mechanism that proves each obligation?
- Which database constraint is the final backstop?
- Which state truly requires a separate transaction?
- What constraint requires each service, queue, cache, projection, or worker?
- What happens if each proposed component is deleted?
- What measured trigger would justify deferred complexity?

### Method

For every design element, complete this sentence:

```text
We need <mechanism> because <validated requirement or rule> cannot
be satisfied by <simpler alternative>, as shown by <evidence>.
```

If the sentence cannot be completed, remove or defer the mechanism.

### Artifact: architecture justification table

| Requirement/invariant | Failure to prevent | Minimum mechanism | Why simpler is insufficient | Verification |
|---|---|---|---|---|
| One outstanding loan per book | Two patrons borrow the same book at the same time | Partial unique index | Two requests can both pass a read-before-write availability check | Two concurrent inserts |
| Patron capacity limit | Two requests both see the same remaining capacity and both approve | Lock the patron admission decision, then count and insert in one transaction | Separate counts can both pass before either request inserts its loan | Concurrent capacity test |
| Retry-safe borrow | A client retries after a timeout and creates a second loan | Store the command result in the loan transaction | Memory in one API process is lost when that process restarts | Exact replay test |
| Optional confirmation | An email outage causes an otherwise valid checkout to fail | Send email from a background worker after the loan commits | Sending email inside checkout makes an optional service part of core correctness | Email failure test |

### Apply deletion before optimization

In order:

1. question the requirement;
2. delete unjustified requirements and components;
3. simplify the remaining design;
4. optimize measured bottlenecks;
5. accelerate feedback and delivery;
6. automate stable necessary work.

Before deletion, ask:

> What truth did this component protect, and what protects that truth after it
> is removed?

### Gate 5: architecture review

Every material component traces to a requirement, invariant, SLO, or external
constraint. The team has documented why a simpler alternative is insufficient.

## Stage 6: Implement With Clean Boundaries

Clean Architecture governs dependency direction after the domain and
application boundaries are understood.

### Rules

- Domain code expresses business state and transitions without delivery or
  infrastructure dependencies.
- Application operations coordinate the outcome and own transaction ports.
- Infrastructure adapters implement persistence and external integrations.
- Presentation translates transport input and output.
- The composition root chooses implementations; it does not contain business
  decisions.
- Derived caches and projections never become accidental authorities.

### Implementation sequence

1. executable domain examples and invariant tests;
2. application operation and ports;
3. database constraints and migrations;
4. infrastructure adapters;
5. presentation contract;
6. failure, concurrency, and replay tests;
7. optional optimizations and external effects.

This sequence is guidance, not a prohibition on exploratory spikes. Spike code
must be explicitly disposable and must not silently become the production
architecture.

### Gate 6: implementation review

Dependency rules hold, persistence constraints match the correctness model,
and each requirement has an implementation and verification path.

## Stage 7: Verify, Operate, and Simplify

Use [Formal Methods and Property-Based Testing](FORMAL_METHODS_AND_PROPERTY_TESTING.md)
when important rules can fail across more input combinations, operation
sequences, retries, or concurrent transactions than a practical set of hand-written
example tests can cover. The guide explains the difference between generated
tests, stateful tests, real database concurrency tests, and formal model
checking so that teams can choose evidence proportional to the risk.

### Verification layers

- domain transition and property tests;
- application behavior and idempotency tests;
- migrated-database constraint and concurrency tests;
- contract tests for external boundaries;
- performance tests for SLO assumptions;
- failure and recovery exercises;
- production metrics for emergent properties.

### Operational questions

- Which signals show the user outcome succeeding?
- Which signals show an invariant or convergence deadline at risk?
- What is the authoritative fallback when a projection or cache is unavailable?
- Can state be rebuilt?
- Can an operator explain and safely recover every nonterminal workflow?
- Which assumptions have expired?

### Continuous simplification

At review intervals, run backward traceability:

```text
component -> current requirement -> current evidence
```

Delete components whose requirement disappeared. Reconsider requirements whose
supporting evidence changed. Avoid preserving complexity only because removing
it would make past work feel wasted.

### Gate 7: release and learning review

Verification evidence exists, operational signals cover the promises, recovery
is understood, and follow-up assumptions have validation actions and expiry
conditions.

## The Execution Management Loop

The seven stages establish what should be delivered and the evidence it needs.
They do not manage the daily movement of work through time. Use
[Engineering Planning and Estimation](ENGINEERING_PLANNING_AND_ESTIMATION.md)
to discover and forecast the complete work, then use
[Engineering Execution Management](ENGINEERING_EXECUTION_MANAGEMENT.md) to
control delivery until client or user acceptance.

Execution management runs across the design stages rather than appearing as an
eighth stage after implementation. A decision can block design, a migration
rehearsal can change architecture, and production evidence can send the team
back to requirements.

### Why time must be modeled

Time changes the execution system in five ways:

1. **Fixed events generate work backward.** A release or client-acceptance date
   creates upstream dates for deployment, verification, integration,
   implementation, decisions, and discovery.
2. **State drifts.** Code, data, assumptions, dependencies, backlogs, costs,
   priorities, and human capacity change while the project runs.
3. **Parallel tracks collide.** Different tasks may need the same engineer,
   reviewer, environment, repository area, client decision, or release window.
   A freelancer experiences the same collision between roles.
4. **Transitions concentrate risk.** Handoffs, integration, migrations,
   deployment, and acceptance expose missing information and incompatible
   assumptions.
5. **Some moments carry more consequence.** An early authority decision, a
   migration rehearsal, or the first production transaction can determine the
   value of weeks of surrounding work.

Treating time only as task due dates conceals these effects.

### Standard execution chain

```text
Client or user acceptance at the committed date
  <- production verification
  <- safe release and migration
  <- complete release evidence
  <- integrated required scope
  <- implemented vertical outcomes
  <- blocking decisions
  <- validated requirements and discovery
```

Build the schedule backward from acceptance. For every predecessor, identify
its completion evidence, owner or role, dependency, expected duration,
uncertainty, and latest useful completion time.

### Standard control loop

```text
Observe completed evidence and current state
  -> compare with quality bars, dependencies, and forecast
  -> identify material variance
  -> choose and own an intervention
  -> execute and verify the effect
  -> update the forecast
  -> communicate while useful options remain
```

The loop applies to one person and to a team. A solo engineer may perform every
role, but cannot perform every role at the same time. A team may create more
parallel capacity, but it also creates handoffs, queues, and coordination.

### Deadline integrity

Before accepting a deadline, the engineer or team must validate that the
essential scope and mandatory quality bars fit a credible plan. After accepting
it, the team must protect those bars, control optional scope, monitor leading
indicators, and escalate threats early.

When a committed date is threatened, use this response order:

1. verify the evidence;
2. protect the essential outcome and mandatory quality bars;
3. stop unapproved scope growth;
4. remove the least valuable optional scope;
5. resolve blocking decisions;
6. resequence the controlling dependency chain;
7. reduce work in progress and handoffs;
8. simplify the design where requirements permit;
9. add capacity only where it can become effective in time;
10. change the rollout strategy or use an agreed fallback;
11. reforecast and communicate; and
12. renegotiate before the deadline when no valid plan can preserve the
    original outcome.

Hiding a likely miss or silently lowering a mandatory quality bar is not
deadline integrity.

### Execution evidence

A material project should maintain, in a form proportional to its size:

- the outcome, deadline, and acceptance conditions;
- mandatory and optional scope;
- component quality bars;
- a backward dependency chain;
- decision owners and latest responsible dates;
- a person-by-time or role-by-time capacity view;
- evidence-based milestones and transition gates;
- leading indicators and interventions;
- a current forecast and confidence; and
- a client or stakeholder communication cadence.

## Required Artifacts by Risk

The system should improve reasoning, not create paperwork. Scale artifacts by
risk.

| Change risk | Minimum artifacts |
|---|---|
| Low: local, reversible, no data contract | Outcome, acceptance criteria, focused work list, tests, completion date |
| Medium: persistent state or shared API | Requirement records, invariant changes, decision note, dependency and forecast view, migration/contract tests |
| High: money, privacy, security, availability, cross-service workflow | Full trace matrix, failure model, authority/context review, architecture justification, execution baseline, rollout and recovery plan |
| Critical: consensus, irreversible data, safety or major regulatory exposure | High-risk artifacts plus formal/property model, independent review, staged validation, exercised rollback/recovery, continuous execution control |

## Documentation Language Standard

Engineering documents must reduce the reader's work, not merely reduce the
writer's word count.

- Write complete sentences when explaining reasoning or consequences.
- Define an acronym or specialized term before relying on it.
- Describe the concrete failure instead of using only an abstract label.
- Include an example when a rule could reasonably be interpreted in more than
  one way.
- Prefer “two requests can both pass the check and create invalid data” over
  “write skew” unless the term has already been explained.
- Prefer “two models can disagree and nobody knows which value is correct” over
  “duplicated mutable truth.”
- Use short checklist fragments only after the full idea has been explained
  elsewhere in the same document.

Concise writing is useful only when it remains immediately understandable to
the intended reader.

## Standard Engineering Review Packet

For a material design, reviewers should receive:

1. **Outcome brief** — problem, scenarios, non-goals.
2. **Validated requirements** — source, evidence, classification, thresholds.
3. **Correctness model** — invariants, policies, consistency and failure model.
4. **Authority map** — authoritative models and context relationships.
5. **Architecture justification** — minimum mechanisms and rejected alternatives.
6. **Traceability matrix** — requirement to design to verification.
7. **Planning and forecast record** — complete work, decisions, dependencies,
   capacity, estimate range, deadline, and confidence.
8. **Execution baseline** — quality bars, scope order, backward schedule,
   milestones, transitions, control cadence, and escalation triggers.
9. **Operational plan** — SLOs, metrics, rollout, rollback, recovery.
10. **Open assumptions** — validation action and expiry condition.

## Standard Design Review Agenda

Review in this order to avoid debating implementation before the problem is
accepted:

1. Is the outcome correct and valuable?
2. Are the requirements valid, evidenced, bounded, and verifiable?
3. What must remain true?
4. Which inconsistencies are temporary, and for how long?
5. Which model or bounded context is authoritative for each mutable fact?
6. What can race or fail?
7. What constraint requires each architectural component?
8. Is there a smaller design with the same proof?
9. Does every requirement have verification evidence?
10. Has the complete work been discovered and forecast from evidence?
11. Can the outcome reach its deadline with the mandatory quality bars intact?
12. Are dependencies, decisions, capacity collisions, and risky transitions
    visible through time?
13. Can the system be operated, recovered, and simplified later?

## Decision Outcomes

A review should end with one of these explicit results:

- **Accepted:** obligations and proof are sufficient.
- **Accepted with experiments:** implementation may proceed, but named
  assumptions must be validated before release.
- **Revise requirements:** the problem or obligation is invalid, ambiguous, or
  contradictory.
- **Revise architecture:** the requirements are valid but the design does not
  prove them minimally.
- **Rejected:** cost or risk exceeds the value of the outcome.

“Looks good” is not a decision record.

## End-to-End Example: Borrow a Book

### 1. Outcome

An eligible patron receives one loan for an available book.

### 2. Requirements

- at most one outstanding loan per book;
- patron eligibility and capacity enforced at commit;
- exact retries return the original result;
- successful response contains the committed loan identity and terms;
- notification failure does not invalidate the loan.

### 3. Correctness model

- hard invariant: one `returned_at IS NULL` loan per book;
- hard policy decision: eligibility and capacity checked in the admission
  transaction;
- retry guarantee: one business effect per idempotency key and fingerprint;
- eventual effect: notification may follow the committed loan.

### 4. Authority

- Catalog: book identity and metadata;
- Patron: tier and suspension;
- Lending: circulation, terms, and availability;
- Notification: delivery attempt;
- search/cache: derived, disposable views.

### 5. Minimum architecture

- Catalog and Patron adapters provide upstream facts;
- one Lending transaction performs admission and insert;
- patron fence prevents capacity write skew;
- partial unique index prevents double checkout;
- command receipt shares the loan transaction;
- outbox event drives optional notification.

### 6. Clean implementation

- `Loan` protects lifecycle transitions;
- `BorrowBookHandler` coordinates the use case;
- Lending UoW owns the transaction;
- repository and PostgreSQL adapter enforce persistence;
- FastAPI route translates HTTP;
- container wires dependencies.

### 7. Evidence

- domain transition tests;
- idempotency replay tests;
- migrated-PostgreSQL uniqueness tests;
- synchronous API contract test;
- notification failure-isolation test;
- cache invalidation tests for composed availability reads.

### 8. Execution

- build backward from client acceptance and production verification;
- complete authority and policy decisions before dependent implementation;
- test the highest-risk migration and concurrency assumptions early;
- deliver one complete vertical borrow path before opening optional work;
- reserve explicit review, integration, release, and recovery capacity;
- protect the loan, capacity, retry, migration, and authorization quality bars;
- monitor decision age, blocked work, review queues, milestone evidence, scope
  growth, and forecast movement; and
- communicate any threatened commitment while scope and rollout options remain.

## Adoption Guide

Teams do not need to rewrite everything before using this method.

### For a new capability

Start at Stage 1 and produce only the artifacts justified by its risk.

### For an existing system

Work backward:

1. List the system's components and the facts each component can change.
2. Identify the requirement that is supposed to justify each component.
3. Write down the rules that valid data must never break and the model that is
   authoritative for each changing fact.
4. Find facts stored as authoritative in more than one place and boundaries
   that have no current justification.
5. Add the missing database, concurrency, and failure tests.
6. Simplify one safe part of the system at a time.

### For an incident

Ask:

- Which requirement or invariant was violated?
- Was it missing, misunderstood, or unenforced?
- Which failure assumption was wrong?
- Which evidence should have detected it earlier?
- Does the fix add necessary proof or merely another compensating process?

Update the requirements, invariant catalog, architecture justification, tests, and
operational signals—not only the line of code that failed.

## Compact Checklist

Before building:

- Has the team agreed on the real-world outcome it needs to produce?
- Has the team confirmed that every material requirement is necessary, clear,
  and testable?
- Has the team written down the rules that must never be broken and when each
  result must become visible?
- Is one model the source of truth for every fact that can change?
- Does the team understand what can happen when requests overlap, repeat, time
  out, or fail halfway through?
- Is this the simplest design that satisfies and verifies the requirements?

Before releasing:

- Can every requirement be traced to its design and verification evidence?
- Have the database and external-contract tests run in a production-relevant
  environment?
- Can production measurements show whether the reliability targets are being
  met?
- Has the team exercised important failure and recovery paths?
- Can optional infrastructure fail without corrupting the core business
  result?
- Has the team removed components that no current requirement justifies?

During execution:

- Is progress measured through completed evidence rather than activity or
  percentages?
- Are blocking decisions made before their latest useful dates?
- Does the person-by-time or role-by-time plan expose capacity collisions?
- Are high-risk transitions rehearsed before the deadline depends on them?
- Is optional scope being controlled while mandatory quality remains protected?
- Do leading indicators cause interventions and forecast updates?
- Will the client or stakeholder hear about a material threat while meaningful
  choices still exist?

## Related Guides

- [Design to Requirements](DESIGN_TO_REQUIREMENTS.md)
- [Invariant-Driven Architecture](INVARIANT_DRIVEN_ARCHITECTURE.md)
- [Formal Methods and Property-Based Testing](FORMAL_METHODS_AND_PROPERTY_TESTING.md)
- [Delivery Assurance Gaps and Extension Plan](DELIVERY_ASSURANCE_GAPS.md)
- [Engineering Planning and Estimation](ENGINEERING_PLANNING_AND_ESTIMATION.md)
- [Engineering Execution Management](ENGINEERING_EXECUTION_MANAGEMENT.md)
- [Human-Centered Systems and Execution](HUMAN_CENTERED_SYSTEMS_AND_EXECUTION.md)
- [Strategic DDD Guide](STRATEGIC_DDD_GUIDE.md)
- [Context Map](CONTEXT_MAP.md)
- [Sagas and Consistency](SAGAS_AND_CONSISTENCY.md)
- [Reads versus Searches](READS_VS_SEARCHES.md)
