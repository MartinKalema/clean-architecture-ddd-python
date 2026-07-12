# Delivery Assurance Gaps and Extension Plan

## Purpose

The [Engineering Design System](ENGINEERING_DESIGN_SYSTEM.md) explains how to
start with a real-world outcome, validate requirements, identify invariants,
assign authority, and choose the minimum architecture that protects the rules.
That process helps a team design the right system and justify its technical
choices.

Design quality is only one part of delivery quality. A technically correct
design can still fail because the team misunderstood the user, deployed an
incompatible database change, omitted an abuse case, could not recover from an
outage, or never checked whether the release improved the intended outcome.

This document explains those gaps and defines how the Engineering Design System
should grow into an end-to-end delivery system. It is an extension plan, not a
replacement for the existing design method.

## Intended Audience

This guide is for engineers, technical leads, product partners, security
reviewers, and operators who need to decide what evidence a change requires
before and after release.

It is useful for:

- designing a new capability;
- reviewing a material code change;
- preparing a release or migration;
- deciding whether a system is ready for production;
- learning from an incident or an unsuccessful product change; and
- improving an existing delivery process without adding the same ceremony to
  every change.

## Current Assessment

The Engineering Design System already covers the hardest architecture questions
well:

- What real outcome does the system need to produce?
- Is each requirement necessary, clear, and verifiable?
- Which rules must never be broken?
- Which model is authoritative for every fact that can change?
- Where must a transaction or other consistency boundary exist?
- What is the minimum architecture that protects the required rules?
- What evidence proves the design under concurrency, retry, and failure?

These questions can produce a technically sound design. They do not, by
themselves, prove that the right change reaches users safely, can be operated by
the team, and continues to provide value after release.

The honest assessment is therefore:

> We have a strong system for arriving at a justified architecture. We do not
> yet have a complete system for delivering, operating, and evolving that
> architecture safely.

## What High-Quality Delivery Means

A high-quality delivery process gives the team credible evidence for five
claims:

1. **Value:** The change addresses a real user or business need.
2. **Correctness:** The system preserves its required behavior and invariants.
3. **Safety:** The transition from the old state to the new state does not
   create unacceptable security, data, compatibility, or operational risk.
4. **Operability:** The team can observe, support, recover, and evolve the
   capability.
5. **Learning:** Production evidence can confirm or challenge the assumptions
   that justified the change.

Passing automated tests supports some of these claims. It does not establish
all of them. A test suite cannot decide whether users needed the feature, prove
that an operator understands an alert, or show that a database rollback can
restore deleted data unless those questions were explicitly included in the
delivery process.

## How to Read the Gap Assessment

Each gap below contains five parts:

- **Purpose:** what the missing discipline contributes;
- **Failure prevented:** the concrete problem it is meant to catch;
- **Required questions:** what the team must understand;
- **Evidence:** the documents, tests, measurements, or exercises that support
  the decision; and
- **Exit condition:** what must be true before the team treats the gap as
  sufficiently addressed.

Not every change needs every artifact. A spelling correction and a migration
of financial records should not follow identical processes. The
[Risk-Based Assurance](#risk-based-assurance) section explains how to apply the
guidance proportionally.

## Gap Summary

| Gap | Question the current system must add | Example evidence |
|---|---|---|
| Product and user validation | Does this outcome solve a real and sufficiently important problem? | User evidence, measurable outcome, usability criteria |
| Security, privacy, and abuse | Who or what could misuse this capability or expose protected data? | Threat model, data classification, abuse tests |
| Change and release safety | Can old and new code, schemas, and messages coexist during rollout? | Compatibility matrix, migration rehearsal, rollback plan |
| Operational readiness | Can the team detect, diagnose, and recover from failure? | SLOs, alerts, runbooks, recovery exercise |
| Delivery-pipeline assurance | Does CI/CD verify the properties and environment conditions that matter? | Risk-mapped checks, reproducible artifact, smoke test |
| Performance, capacity, and cost | Will the system meet its workload and cost obligations? | Capacity model, load evidence, scaling thresholds |
| Data lifecycle | Can data be validated, retained, migrated, restored, and deleted correctly? | Data inventory, retention rules, restore test |
| Ownership and decision rights | Who can make or accept each material decision? | Named decision rights and operational ownership |
| Maintainability and evolution | Can another engineer change or remove this safely? | Decision records, compatibility policy, removal criteria |
| Post-release learning | Did the release produce the intended result under real conditions? | Outcome review, production measurements, follow-up decisions |

## Acceptable Knowledge States

Planning questions will regularly uncover facts that the team does not know.
That is useful. The purpose of planning is not to pretend that uncertainty has
already disappeared. It is to make uncertainty visible and decide what must
happen before the team relies on an assumption.

An engineer, technical lead, or CTO does not need to memorize every operational
number. The organization should, however, be able to give one of five
responsible answers for a material question.

### Known

> “It grows by approximately 4 GB per day under normal load.”

The team has evidence for the answer and can identify its source. The source
might be a production measurement, a verified report, or a reproducible
calculation. The answer should include the conditions under which it remains
valid. “Normal load” still needs a defined workload range.

### Bounded

> “We do not know the exact rate, but load tests show it remains below 8 GB per
> day at twice our expected peak.”

An exact value is unnecessary when the team can prove a safe upper or lower
bound. Bounds are often more useful for architecture than averages because
capacity, retention, and failure decisions depend on whether a limit can be
crossed.

The bound must still state its assumptions: workload, data shape, test
environment, duration, and safety margin.

### Measured

> “The rate is visible in this dashboard, and an alert fires when cleanup
> cannot keep pace.”

The answer may change continuously, so the system measures it instead of
depending on a fixed document. Measurement is responsible only when the team
knows which threshold is unsafe, the alert reaches an owner, and that owner has
a useful response.

A dashboard without a threshold or action leaves the risk visible but
uncontrolled.

### Planned

> “This is currently unknown. Alice will measure event size and peak throughput
> by Friday before we approve the retention design.”

It is acceptable not to know something yet. A responsible unknown has:

- a clearly stated question;
- an owner with the ability to investigate it;
- a concrete method for producing evidence;
- a deadline tied to the decision that needs the answer; and
- a rule that prevents the dependent decision from being approved too early.

The name is not ceremonial ownership. It identifies who must turn the unknown
into evidence so that the rest of the team is not silently assuming it will be
handled.

### Not material

> “The data is bounded by a database constraint and the maximum customer count,
> so further analysis would not change the decision.”

Some questions do not deserve more investigation. The team may already know
that every plausible answer leads to the same safe design. Recording why the
answer is not material prevents both neglected risk and unnecessary analysis.

“Not material” must include the reasoning. It cannot mean that the team does
not want to investigate an inconvenient uncertainty.

### The unacceptable state

The dangerous answer is:

> “We do not know, nobody is measuring it, and the architecture assumes it will
> be fine.”

This is not merely missing knowledge. It is an unowned risk embedded in the
design. The team has made a decision using an assumption while providing no
evidence, bound, measurement, investigation plan, or materiality argument.

### Applying the framework

For every material planning question, record:

| Field | Meaning |
|---|---|
| Question | The fact or uncertainty that could change the decision |
| Knowledge state | Known, bounded, measured, planned, or not material |
| Evidence or reasoning | The source, bound, dashboard, investigation, or materiality argument |
| Conditions | The workload, environment, time period, or assumptions under which the answer holds |
| Decision affected | The design, release, capacity, or risk decision that depends on the answer |
| Owner and deadline | Required for planned work or an operational measurement that needs a response |
| Revisit trigger | The observation or change that makes the answer invalid or material again |

This framework applies beyond capacity planning. It can classify questions
about user demand, security threats, migration duration, recovery time,
dependency limits, cost, compliance, and any other fact that could materially
change the design or release decision.

## Questions Should Turn Unknowns Into Engineering Work

A planning question is valuable only if its answer can affect a decision or
produce necessary work. Asking many questions without classifying the answers
creates a longer meeting, not a stronger plan.

The purpose of a good question is to expose something the current plan depends
on but does not yet understand. The team then converts that unknown into one or
more concrete outputs:

- evidence that resolves the question;
- a design decision;
- an implementation task;
- a verification activity;
- an operational control;
- an accepted and owned risk; or
- a reason that no further work is material.

### From question to work

Use this reasoning chain:

```text
Planning question
  -> why the answer could change the outcome or design
  -> current knowledge state
  -> method for obtaining sufficient evidence
  -> decision enabled by that evidence
  -> engineering and operational work created by the decision
  -> verification and production signal
```

The team should stop the chain when further knowledge would not change a
material decision. Investigation without a decision is waste, just as a
decision without sufficient evidence is speculation.

### Example: outbox growth

Consider the question:

> How quickly does the outbox table grow?

The question matters because the answer can change retention, cleanup,
storage, backup, alerting, and recovery decisions. It may reveal several facts
that the team does not know:

- the expected and peak event rate;
- the average and largest stored event size;
- table and index overhead;
- write-ahead log and replication amplification;
- the required retention period;
- cleanup throughput;
- what happens when cleanup stops; and
- how an operator detects that incoming data is growing faster than it can be
  removed.

A first estimate can use:

```text
Raw daily growth
  = events per second
  × average stored bytes per event
  × 86,400 seconds
```

If the system produces 10 events per second and each stored event averages 2
KB, the raw data alone grows by approximately 1.7 GB per day:

```text
10 × 2 KB × 86,400 ≈ 1.7 GB per day
```

That calculation is not yet a capacity plan. It excludes table overhead,
indexes, write-ahead logging, replication, backups, temporary maintenance
space, and unusual payloads. It also says nothing about whether cleanup can
keep pace.

The original question therefore creates a bounded investigation:

```text
Measure event volume and stored size
  -> calculate raw and amplified growth
  -> define expected and peak workloads
  -> choose a justified retention period
  -> test cleanup throughput and batch behavior
  -> calculate storage and recovery headroom
  -> define unsafe thresholds
  -> add growth and cleanup-lag signals
  -> exercise recovery after cleanup interruption
```

The investigation can produce several kinds of engineering work:

| Finding | Work it creates |
|---|---|
| Cleanup is faster than peak arrival with sufficient margin | Record the measured bound and retain the simple cleanup design |
| Cleanup falls behind during expected peaks | Change batching, indexing, retention, or cleanup capacity and rerun the test |
| Retention has no business or recovery justification | Shorten retention instead of scaling storage |
| Outbox growth can exhaust storage before an operator responds | Add storage and cleanup-lag alerts with actionable thresholds |
| Recovery requires records longer than current retention | Reconcile the recovery requirement with retention and backup design |
| Every plausible volume remains far below an enforced storage bound | Record the question as not material and avoid unnecessary infrastructure |

The question has now produced assumptions, measurements, decisions, tasks,
tests, alerts, and recovery guidance. It no longer exists as a vague concern in
meeting notes.

### Different unknowns produce different work

Not every unknown should become an implementation ticket. First classify what
the team discovered:

| Discovery | Meaning | Appropriate work |
|---|---|---|
| Missing fact | Evidence needed before a decision | Measurement, research, prototype, or experiment |
| Unverified assumption | The plan currently relies on a belief | Validation task with an owner, deadline, and decision gate |
| Material risk | An uncertain event could cause harm | Prevention, mitigation, detection, recovery, transfer, or authorized acceptance |
| External dependency | Success relies on another person, team, vendor, or system | Coordination, contract clarification, fallback, and escalation |
| Open decision | Several acceptable choices remain | Decision owner, options, trade-offs, evidence, and deadline |
| Hard constraint | A limit must be respected | Design enforcement and verification |
| Knowledge that cannot affect the decision | More detail would not change safe action | Record why it is not material and stop investigating |

Calling all of these items “risks” hides the action each one needs. A missing
fact needs evidence. A decision needs authority. A dependency needs
coordination. A constraint needs enforcement. A risk needs treatment or
acceptance.

### Questions can remove work

Good planning questions do not exist only to discover more components. They can
also reveal that proposed work has no valid requirement.

For example:

> What requirement forces borrowing to cross two independently committed
> databases?

If the answer is “none,” the question does not create a more sophisticated
saga. It removes the saga and moves the invariant into one transaction.

Another example is:

> What measured workload requires Elasticsearch rather than PostgreSQL search?

If PostgreSQL satisfies the required relevance, language behavior, latency, and
volume, the responsible result may be to defer Elasticsearch and its indexing,
recovery, monitoring, and consistency work.

This is how planning supports minimum architecture. It discovers necessary
work while also challenging work that no validated constraint requires.

### A question is complete when it reaches a decision

A material planning question is complete when the team can record:

| Field | Required answer |
|---|---|
| Question | What do we need to understand? |
| Importance | Which outcome, invariant, risk, SLO, cost, or release decision could it change? |
| Current state | Known, bounded, measured, planned, or not material |
| Evidence method | How will sufficient evidence be produced? |
| Decision | What will the team choose when the evidence is available? |
| Work created | Which implementation, test, migration, operational, or coordination tasks follow? |
| Owner and deadline | Who moves the question forward, and before which dependent decision? |
| Verification | What proves that the resulting work addressed the original concern? |
| Production feedback | Which signal shows whether the answer remains true after release? |

If the team cannot explain which decision an answer will affect, it should
challenge whether the question is worth pursuing. If a material answer can
change the design but has no owner or decision gate, the plan is incomplete.

### Planning is a map of obligations and uncertainty

A delivery plan is not primarily a list of tasks and dates. It is a structured
account of:

- what outcome must be produced;
- what must remain true;
- what the team knows;
- what the team assumes;
- what remains uncertain;
- how important uncertainty will be reduced;
- which decisions depend on the evidence;
- which work those decisions create; and
- what will prove success before and after release.

Dates become meaningful after this structure exists. Otherwise the schedule is
precision applied to an incomplete understanding of the work.

The detailed method for converting this structure into deliverables,
dependencies, estimates, deadlines, forecasts, and replanning triggers is in
[Engineering Planning and Estimation](ENGINEERING_PLANNING_AND_ESTIMATION.md).

## 1. Product and User Validation

### Purpose

The existing process begins with an outcome, but it needs a stronger method for
proving that the outcome matters to real users. A team can implement every
technical requirement correctly and still solve the wrong problem.

Product validation does not mean that every change requires a large research
project. It means the strength of the evidence should match the cost and
irreversibility of the decision.

### Failure prevented

Without product and user validation, a team may:

- optimize behavior that users do not value;
- interpret an internal stakeholder request as a user requirement;
- solve a symptom while preserving the real problem;
- create a technically correct workflow that users cannot understand; or
- measure deployment completion instead of user success.

In this library system, a synchronous borrow operation can be technically
correct but still provide a poor experience if a patron cannot tell whether the
book was borrowed, when it is due, or what to do after a rejection.

### Required questions

- Who experiences the problem, and in which real-world situation?
- What evidence shows that the problem exists?
- What behavior or condition should improve after the change?
- How will a user know that the operation succeeded or failed?
- Which accessibility and usability requirements apply?
- Which assumptions remain uncertain?
- What result would cause the team to stop, revise, or remove the capability?

### Evidence

Depending on risk, useful evidence includes:

- observations, interviews, support records, or usage data;
- a written outcome and the scenario that produces it;
- usability and accessibility acceptance criteria;
- a measurable success indicator and a current baseline;
- an assumption log with validation dates; and
- a plan for evaluating the result after release.

### Exit condition

The team can explain the user or business problem without describing a proposed
solution, and it has an observable way to decide whether the release improved
that problem.

## 2. Security, Privacy, and Abuse Analysis

### Purpose

Security cannot be treated as a normal invariant that engineers may or may not
discover while modeling the domain. A delivery system needs an explicit track
for authorization, sensitive data, abuse, dependency risk, and incident
response.

Authentication may be intentionally out of scope for a learning exercise. The
engineering process must still make that exclusion visible and prevent it from
being mistaken for production readiness.

### Failure prevented

Without an explicit security and privacy review, a system may:

- allow an unauthorized caller to perform a valid business operation;
- send private information to an attacker-controlled address;
- expose secrets or personal data through logs and error messages;
- retain data longer than the business or law permits;
- trust a compromised dependency or build artifact; or
- detect abuse only after it has caused irreversible damage.

The original direct-loan endpoint in this library demonstrates the difference
between domain correctness and abuse resistance. Even if creating a loan were
a valid domain operation, accepting an arbitrary email address could turn the
notification flow into an email-abuse path.

### Required questions

- Who may perform each operation, and how is that decision enforced?
- What data is sensitive, private, regulated, or security-relevant?
- Where can that data appear: database, events, logs, caches, analytics, email,
  and backups?
- How could a legitimate capability be abused?
- Which trust boundaries does the request cross?
- How are secrets, dependencies, images, and build artifacts protected?
- What must be prevented, detected, rate-limited, quarantined, or audited?
- What is the response when a control fails?

### Evidence

Risk-proportional evidence may include:

- a threat model and trust-boundary diagram;
- data classification and a data-flow review;
- authorization and abuse-case tests;
- dependency, secret, container, and source scanning;
- rate-limit and denial-of-service tests;
- retention and deletion rules;
- an audit-event specification; and
- a security incident and disclosure procedure.

### Exit condition

Material threats, sensitive data flows, and abuse cases are known. Each
unacceptable risk has a preventive or detective control, and any accepted
residual risk has an explicit decision maker.

## 3. Change and Release Safety

### Purpose

Verifying the final architecture is not sufficient. The team must also verify
the transition from the old system to the new system.

During a rolling deployment, old and new application instances may run at the
same time. Existing data may use an older shape. Messages published before the
deployment may arrive afterward. A migration may finish before every process
that depends on the old schema has stopped.

### Failure prevented

Many production incidents happen even though the old version and the new
version each work independently. The failure exists only during the transition.

Examples include:

- new code writes a value that old code cannot read;
- a column is removed while an old worker still uses it;
- a queue contains messages the new consumer does not understand;
- a failed migration cannot be reversed without losing new data;
- two active versions disagree about which model owns a fact; or
- a feature flag enables behavior before its database backfill is complete.

### Required questions

- Which versions can run together during deployment?
- Can each version read data written by the other?
- What is the safe order for schema, application, worker, and configuration
  changes?
- Which destructive changes require a later cleanup release?
- Can the release be disabled without reversing the schema?
- Is rollback safe after the new version writes data?
- When is roll-forward safer than rollback?
- How will the team know that a backfill or migration is complete and correct?

### Evidence

- an old/new compatibility matrix;
- an expand-migrate-contract sequence for schema changes;
- migration tests against production-like data volume and shape;
- a backfill plan with progress, validation, and restart behavior;
- feature-flag or staged-rollout controls;
- rollback and roll-forward conditions;
- message-contract compatibility tests when asynchronous delivery exists; and
- a rehearsal of the highest-risk transition.

### Exit condition

The team can describe every deployment phase, the versions and schemas that
coexist in that phase, the signal that permits the next phase, and the safe
response to failure.

## 4. Operational Readiness

### Purpose

The current design system mentions service-level objectives, monitoring, and
recovery. It still needs a concrete readiness gate that proves an engineer can
act when the capability fails.

An alert is useful only when it identifies a meaningful condition and leads to
a safe action. A dashboard is not operational readiness by itself.

### Failure prevented

Without operational readiness, the team may discover that:

- no one knows whether the service is meeting its user promise;
- an alert reports symptoms but provides no diagnostic path;
- retries worsen an overloaded dependency;
- a backup exists but cannot be restored;
- delayed messages create incorrect behavior without an operator noticing;
- a recovery script is unsafe under the current schema; or
- the only engineer who understands the system is unavailable.

### Required questions

- Which service-level indicators represent user success?
- What service-level objective is required, and over which period?
- Which conditions require immediate action?
- Who responds, and what is the escalation path?
- How does an operator diagnose the failure?
- How are damaged, missing, duplicated, or delayed records reconciled?
- What are the recovery-time and recovery-point objectives?
- What happens when each dependency is slow, unavailable, or partially
  successful?
- Which recovery procedures have been exercised rather than merely written?

### Evidence

- service-level indicators, objectives, and an error budget;
- alerts tied to user impact or an approaching invariant/convergence failure;
- dashboards that support diagnosis;
- tested runbooks and safe administrative tools;
- dependency-failure and recovery exercises;
- backup restoration evidence;
- reconciliation queries or procedures; and
- an operational ownership and escalation record.

### Exit condition

An engineer who did not implement the capability can use the available signals
and runbooks to detect a representative failure, diagnose it, and perform or
escalate a safe recovery.

## 5. Delivery-Pipeline Assurance

### Purpose

Continuous integration and delivery should produce evidence for the risks of
the change. A large collection of checks is not automatically a strong
pipeline. The checks must exercise the properties, boundaries, and environment
conditions that matter.

The important question is not merely “Did CI pass?” It is:

> Did CI test the properties and environment conditions that matter for this
> change?

### Failure prevented

A pipeline may be green while:

- tests use SQLite even though correctness depends on PostgreSQL behavior;
- migration-only constraints are absent from test schemas;
- mocked infrastructure hides a transaction or serialization failure;
- a package installs differently from the developer environment;
- a container contains an unscanned vulnerable dependency;
- the built artifact differs from the artifact that was tested; or
- deployment succeeds but the application cannot serve a real request.

### Required questions

- Which requirement, invariant, or threat does each required check cover?
- Does the test environment preserve the production behavior being claimed?
- Are migrations tested from supported starting revisions?
- Is the tested artifact the artifact that will be deployed?
- Are tests deterministic enough to trust and diagnose?
- Which checks block release, and who may override them?
- What happens immediately after deployment to verify the new environment?

### Evidence

- a risk-to-check traceability table;
- formatting, linting, typing, and dependency-boundary checks;
- domain, property, integration, contract, migration, and concurrency tests as
  justified by the change;
- secret, dependency, image, and license scanning;
- reproducible or attestable build artifacts;
- environment promotion rather than untracked rebuilding;
- post-deployment health and smoke tests; and
- explicit override and failed-check handling.

### Exit condition

Every release-blocking check has a stated reason, every material change risk
has suitable automated or manual evidence, and the artifact that passed the
checks is the artifact promoted to production.

## 6. Performance, Capacity, and Cost

### Purpose

Performance is not only a late load test. The architecture should be based on
an expected workload, latency budget, resource limit, and cost envelope.

This discipline is particularly important for avoiding speculative
microservices. New infrastructure should respond to a measured or contractually
required constraint, not to the possibility that the system may scale someday.

### Failure prevented

Without capacity reasoning, a team may:

- meet functional requirements but miss the user latency objective;
- exhaust database connections before CPU or memory appears busy;
- create an unbounded queue or outbox backlog;
- perform a table scan during every search fallback;
- introduce a cache or service whose operational cost exceeds its benefit; or
- scale the wrong component because no workload model exists.

### Required questions

- What are the expected, peak, and exceptional workloads?
- What latency and throughput must the system provide?
- Which shared resources impose hard limits?
- How quickly do storage, indexes, caches, logs, and outbox tables grow?
- What happens when demand exceeds capacity?
- What is the acceptable infrastructure and operational cost?
- Which measured threshold would justify a cache, replica, queue, partition, or
  separate service?

### Evidence

- a workload and capacity model;
- end-to-end latency and throughput budgets;
- representative load, stress, and endurance tests;
- database connection and query-budget analysis;
- queue/backlog growth and drain-rate calculations;
- load-shedding and graceful-degradation behavior;
- cost estimates and production cost measurements; and
- recorded scaling triggers.

### Exit condition

The team can show that the design meets the required workload with reasonable
headroom and cost, and it knows which production measurements require the next
capacity decision.

## 7. Data Lifecycle

### Purpose

Assigning an authoritative model answers who may decide and change a fact. It
does not answer how long the data should exist, how it is corrected, how it is
restored, or what happens to its copies.

Persistent data needs a lifecycle from creation through deletion.

### Failure prevented

Without lifecycle design:

- invalid or partially migrated records remain indefinitely;
- personal data survives in events, caches, logs, or backups after deletion;
- a derived index cannot be rebuilt from authoritative facts;
- a backup restores successfully but violates the current schema;
- audit data is removed too early or retained too long; or
- cleanup jobs create locks and outages because volume was never considered.

### Required questions

- Who owns the data and how is it classified?
- What validation and database constraints apply at creation and update?
- Which copies and derived forms exist?
- How long is each form retained, and why?
- How is data corrected, migrated, archived, exported, or deleted?
- Can derived state be rebuilt from authoritative data?
- What is backed up, and has restoration been tested against the current
  application?
- How are legal hold, audit, and privacy obligations reconciled?

### Evidence

- a data inventory and ownership map;
- classification and retention rules;
- schema constraints and migration tests;
- lineage from authoritative data to projections and external destinations;
- deletion and derived-copy cleanup tests;
- bounded archival and cleanup procedures;
- backup and restoration exercises; and
- reconciliation and rebuild procedures.

### Exit condition

The team can follow each material data item from creation to every copy and
eventual deletion or archival, with tested procedures for migration,
restoration, and reconciliation.

## 8. Ownership and Decision Rights

### Purpose

Every requirement does not need a ceremonial owner field. Important decisions
do need clear authority. Otherwise unresolved organizational questions appear
as technical uncertainty.

This is the useful meaning of “who”: not a name attached to every sentence, but
clarity about who can make a decision and who must act when a promise is at
risk.

### Failure prevented

Without decision rights:

- no one can approve a change to an external contract;
- a team silently accepts a security or reliability risk without authority;
- two teams both assume the other operates a shared workflow;
- an incident stalls because no one may choose rollback or roll-forward;
- a formal model or specialized test suite becomes unmaintained; or
- a temporary exception becomes permanent because no one owns its removal.

### Required questions

- Who validates the outcome and approves material requirements?
- Who owns each authoritative model and external contract?
- Who may accept residual security, reliability, or data risk?
- Who operates the capability and responds to incidents?
- Who decides rollout, suspension, rollback, or roll-forward?
- Who maintains specialized evidence such as a formal model, migration tool,
  or recovery procedure?

### Evidence

- decision rights recorded in the change or system documentation;
- code, service, data, and operational ownership;
- review requirements for material risk classes;
- escalation paths; and
- expiry dates and owners for exceptions or temporary mechanisms.

### Exit condition

Every material approval, risk acceptance, operational action, and maintenance
obligation has one clearly authorized owner. This does not require adding a
person to requirements that have no ownership ambiguity.

## 9. Maintainability and Evolution

### Purpose

High-quality delivery includes the next engineer's ability to understand,
change, replace, or remove the system safely. Code that works today but cannot
be evolved without rediscovery is an incomplete delivery.

### Failure prevented

Without explicit maintainability practices:

- names and abstractions conceal the business behavior;
- documentation describes a design that is not deployed;
- an external contract cannot evolve without breaking clients;
- temporary compatibility code remains forever;
- dependencies become unsupported or unsafe;
- architecture accumulates because removal criteria were never written; or
- a test protects implementation details instead of the requirement.

### Required questions

- Can an engineer understand the behavior and authority without reading the
  entire repository?
- Are dependency direction and bounded-context relationships explicit?
- Which decisions are non-obvious enough to preserve in a decision record?
- What compatibility and deprecation promises exist?
- Which dependencies and runtime versions require maintenance?
- Which mechanism is temporary, and what event permits its removal?
- Does the documentation describe the deployed system?

### Evidence

- clear language, interfaces, boundaries, and dependency checks;
- architecture decision records for consequential choices;
- contract versioning and deprecation policies where compatibility is required;
- dependency ownership and upgrade cadence;
- removal criteria for flags, bridges, and temporary paths;
- current system, operational, and recovery documentation; and
- tests written around requirements and observable behavior.

### Exit condition

An engineer unfamiliar with the implementation can locate its business
purpose, authority, major decisions, tests, operational guidance, and safe
extension points without relying on undocumented history.

## 10. Post-Release Learning

### Purpose

Delivery is not complete when deployment succeeds. Production evidence must
confirm or challenge the assumptions that justified the change.

This closes the loop between product validation, architecture, operation, and
future simplification.

### Failure prevented

Without post-release learning:

- the team declares success because deployment completed;
- an unused capability continues to consume maintenance cost;
- a reliability target is missed without changing the design;
- an architecture assumption becomes false but remains undocumented;
- temporary rollout infrastructure becomes permanent; or
- repeated incidents fix individual symptoms without correcting the model or
  requirement.

### Required questions

- Did the user or business outcome improve?
- Were the requirements and assumptions correct?
- Did production behavior match the failure and capacity models?
- Did any invariant or convergence deadline approach violation?
- Were reliability, latency, error, and cost budgets met?
- What surprised the team?
- What should be changed, removed, simplified, or investigated next?

### Evidence

- outcome and adoption measurements compared with a baseline;
- service-level, performance, cost, and correctness evidence;
- incident, support, and usability feedback;
- assumption validation results;
- cleanup of temporary flags and compatibility mechanisms; and
- follow-up decisions recorded in requirements, architecture, tests, and
  operational guidance.

### Exit condition

The team has evaluated the release against its original outcome and technical
promises, recorded what it learned, and assigned concrete actions for any
unresolved result.

## The Extended Engineering Flow

The existing design reasoning remains the spine:

```text
Outcome
  -> validated requirements
  -> invariants and authority
  -> minimum design
  -> implementation
  -> verification
```

Delivery assurance adds a loop around that spine:

```text
Classify delivery risk
  -> activate the required assurance modules
  -> plan compatibility, migration, and release
  -> prove operational readiness
  -> deploy in controlled stages
  -> verify production behavior
  -> learn, correct, and simplify
```

The combined system becomes:

```text
Understand the real-world outcome
  -> validate and specify requirements
  -> identify invariants, policies, and authority
  -> classify product, security, data, change, and operational risk
  -> choose the minimum design and assurance mechanisms
  -> implement and verify them
  -> release through safe transition states
  -> observe the user and system outcome
  -> recover, improve, or simplify using production evidence
```

This is a loop rather than a one-way project plan. Production learning may
invalidate a requirement, change an invariant, expose a threat, or remove the
constraint that justified an architectural component.

## Risk-Based Assurance

The extension must not turn every change into a heavyweight review. Doing so
would recreate overengineering at the process level.

### Risk levels

| Level | Typical change | Minimum treatment |
|---|---|---|
| Low | Local, reversible presentation or documentation change | Clear outcome, focused review, automated checks, ordinary deployment verification |
| Medium | Persistent state, shared API, dependency, or meaningful user workflow | Requirement and invariant review, compatibility assessment, integration evidence, observable rollout |
| High | Sensitive data, material availability, destructive migration, cross-service workflow, or significant cost | Relevant assurance modules, explicit owners, staged rollout, tested recovery, post-release review |
| Critical | Safety, major regulatory exposure, irreversible data, consensus, or very high financial impact | High-risk treatment plus independent review, stronger formal evidence, rehearsal, controlled approval, and exercised recovery |

### Assurance modules and activation triggers

| Module | Activate it when the change... |
|---|---|
| Product and user | Changes user behavior, workflow, comprehension, or accessibility |
| Security and privacy | Changes identity, authorization, trust boundaries, sensitive data, external input, or abuse potential |
| Data lifecycle | Creates, changes, migrates, copies, retains, or deletes persistent data |
| Compatibility and release | Changes schemas, contracts, messages, configuration, deployment order, or supported versions |
| Reliability and recovery | Affects a user promise, dependency failure path, durable workflow, or recovery procedure |
| Performance and cost | Changes load shape, shared resource use, latency, throughput, storage growth, or infrastructure cost |
| Formal/property verification | Contains important input combinations, state sequences, concurrency, or distributed ordering that examples cannot cover credibly |
| Regulatory | Changes behavior or data governed by an external legal, audit, or industry obligation |

A module is activated by a risk, not by team preference or architecture fashion.
The team should record why a high-impact module is excluded when its trigger
appears to apply.

## Delivery Gates

Gates are decisions supported by evidence. They should not become meetings that
exist regardless of risk.

### Gate 1: outcome and risk accepted

- The problem and expected outcome are understandable without a proposed
  design.
- The change has a risk level.
- Relevant assurance modules have been selected.
- Important unknowns are recorded as assumptions.

### Gate 2: design and transition ready

- Requirements, invariants, authority, and minimum design are clear.
- Security, data, compatibility, capacity, and operational implications have
  been addressed where applicable.
- The deployment and migration sequence is known.
- Rollback, roll-forward, and suspension conditions are explicit.

### Gate 3: release evidence ready

- Required automated and manual verification has passed.
- The production artifact is identifiable and promotable.
- Dashboards, alerts, runbooks, and recovery procedures are ready.
- Known residual risks have authorized acceptance.

### Gate 4: production behavior accepted

- Staged rollout signals remain within their limits.
- Smoke tests and critical user paths succeed.
- Migrations, backfills, and projections are complete or progressing within
  their stated bounds.
- No stop or rollback condition is active.

### Gate 5: learning closed

- User, reliability, correctness, performance, and cost results have been
  evaluated at the planned time.
- Unexpected results have follow-up actions.
- Temporary rollout mechanisms have been removed or given an owner and expiry.
- Requirements and design documentation have been updated with what the team
  learned.

## Traceability

The extended trace should connect the reason for a change to its real outcome:

```text
Observed need
  -> validated requirement
  -> invariant, policy, SLO, threat, or external obligation
  -> design and enforcement mechanism
  -> implementation and transition plan
  -> pre-release evidence
  -> production signal
  -> post-release decision
```

An illustrative record for borrowing is:

| Element | Example |
|---|---|
| Observed need | An eligible patron needs to take one available physical copy |
| Requirement | A successful borrow returns a committed loan identity and due date |
| Invariant | A book has at most one outstanding loan |
| Threat | An unauthorized caller must not create a loan for another patron |
| Enforcement | Lending transaction, patron admission fence, partial unique index, authorization control |
| Transition | Deploy additive schema constraints before code that depends on them |
| Pre-release evidence | Domain, idempotency, authorization, migrated-database, and concurrency tests |
| Production signal | Borrow success rate, conflict rate, latency, constraint violations, notification lag |
| Learning decision | Keep, revise, simplify, or investigate based on outcome and operating evidence |

## Reusable Templates

### Delivery assurance record

```markdown
Change:
Expected user or business outcome:
Evidence that the problem exists:
Risk level:

Requirements and invariants:
Authoritative models:
Material assumptions:

Activated assurance modules:
Excluded modules and reason:

Security and privacy risks:
Data lifecycle effects:
Compatibility and migration sequence:
Performance and capacity assumptions:
Operational promises and dependencies:

Release strategy:
Stop condition:
Rollback or roll-forward condition:

Required CI and manual evidence:
Production verification signals:
Post-release review date:

Decision owners:
Accepted residual risks:
Temporary mechanisms and removal criteria:
```

### Operational readiness review

```markdown
User-facing promise:
Service-level indicator and objective:
Dependencies and degraded behavior:
Actionable alerts:
Diagnostic dashboard:
Runbook:
Recovery-time objective:
Recovery-point objective:
Backup restoration evidence:
Reconciliation procedure:
Operational owner and escalation:
Last recovery exercise:
```

### Release transition review

```markdown
Versions that may coexist:
Schemas/contracts/messages that may coexist:
Deployment order:
Migration or backfill stages:
Signal required to advance each stage:
Feature flag or traffic control:
Stop condition:
Rollback safety:
Roll-forward plan:
Destructive cleanup release:
Post-deployment smoke tests:
```

### Post-release review

```markdown
Original outcome:
Review period:
Outcome and adoption evidence:
Correctness and invariant evidence:
Reliability evidence:
Performance and cost evidence:
Security, privacy, or abuse observations:
Incidents and support feedback:
Assumptions confirmed or rejected:
Unexpected results:
Components or temporary paths to remove:
Follow-up decisions, owners, and dates:
```

## Adoption Plan

The team should introduce this extension incrementally.

### Step 1: add risk classification

Require every material change to select a risk level and the assurance modules
that apply. This creates visibility without immediately creating new review
meetings.

### Step 2: strengthen release transitions

Apply the release-transition template to schema, contract, event, and
configuration changes. This addresses a common source of incidents that design
and unit tests do not cover.

### Step 3: establish operational readiness

For user-facing or stateful capabilities, require an actionable signal,
operational owner, recovery path, and representative recovery exercise.

### Step 4: connect CI to risk

Record which checks prove each material requirement, invariant, threat, and
migration assumption. Remove checks that provide no useful evidence and add
missing production-relevant tests.

### Step 5: close the production loop

Schedule a proportionate post-release review. Use its evidence to change the
requirements, architecture, operational controls, or product decision.

### Step 6: create specialized guides only when needed

The gap areas can later become dedicated guides for security, migration safety,
operational readiness, capacity, and data lifecycle. Do not expand every module
before real changes demonstrate the need for more detail.

## What This Document Does Not Require

This extension does not require:

- microservices;
- a dedicated platform team;
- a formal model for ordinary CRUD behavior;
- a committee review for every pull request;
- a separate document for every template;
- perfect prediction of production behavior; or
- retaining architecture whose original constraint no longer exists.

It requires explicit reasoning and evidence proportional to the consequences
of being wrong.

## Final Principle

High-quality delivery is not the number of technologies, checks, documents, or
approval meetings involved. It is the team's ability to make and support a
credible claim:

> We understand the outcome, the rules, and the risks. We chose the simplest
> design and delivery controls that address them. We can release the change
> safely, detect when our assumptions are wrong, recover from failure, and use
> production evidence to improve or remove what we built.

That principle keeps delivery rigorous without making it needlessly heavy.

## Related Guides

- [Engineering Design System](ENGINEERING_DESIGN_SYSTEM.md)
- [Design to Requirements](DESIGN_TO_REQUIREMENTS.md)
- [Invariant-Driven Architecture](INVARIANT_DRIVEN_ARCHITECTURE.md)
- [Formal Methods and Property-Based Testing](FORMAL_METHODS_AND_PROPERTY_TESTING.md)
- [Engineering Planning and Estimation](ENGINEERING_PLANNING_AND_ESTIMATION.md)
- [Engineering Execution Management](ENGINEERING_EXECUTION_MANAGEMENT.md)
