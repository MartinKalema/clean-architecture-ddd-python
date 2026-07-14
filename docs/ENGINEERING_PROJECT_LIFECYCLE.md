# Engineering Project Lifecycle

## Purpose

This document explains the exact operating path an engineer should follow from receiving a project through client acceptance and learning closure. It consolidates three views that already exist in the engineering system:

- the seven stages of engineering design;
- the six dimensions of a complete plan; and
- the five delivery-assurance gates.

These are not three competing processes. They are three views of one lifecycle:

- **Design stages** establish what should be built and why.
- **Planning dimensions** make sure the complete work is visible.
- **Delivery gates** decide whether sufficient evidence exists to advance.
- **Execution management** controls the work through time.
- **Human-centered constraints** apply throughout the lifecycle.

When the client's request is still ambiguous, begin with [Ambiguous Project Discovery](AMBIGUOUS_PROJECT_DISCOVERY.md) before framing the outcome.

## Governing Principle

The lifecycle begins with the real-world outcome—not the task list, requested technology, architecture, estimate, deadline, or code.

```text
Observed need
  -> understood outcome
  -> validated requirements and proof
  -> correctness model and authority
  -> minimum design
  -> complete plan and forecast
  -> controlled implementation
  -> release evidence
  -> production acceptance
  -> learning and simplification
```

## Complete Lifecycle

### Step 0: Receive and classify the project

Before engineering begins, transfer enough context for discovery:

- the observed problem;
- the client or internal sponsor;
- affected users and operators;
- what has already been promised;
- the requested deadline and its reason;
- contractual, financial, regulatory, or organizational constraints;
- available evidence;
- existing systems and dependencies; and
- people who can answer domain questions and make decisions.

The engineer should not receive only:

> Build this application by 1 September.

That combines a proposed solution and a date without supplying the problem, evidence, or meaning of success.

If the request cannot yet support an outcome brief, run the [Ambiguous Project Discovery](AMBIGUOUS_PROJECT_DISCOVERY.md) process first.

#### Output

- project-intake record;
- source and owner of the request;
- known promises and constraints;
- initial unknowns;
- and a named discovery owner.

---

### Step 1: Frame the real-world outcome

Ask:

- Who needs something to change?
- What is happening today?
- What problem or unrealized opportunity does that create?
- What observable result would count as success?
- What must not be harmed?
- What is explicitly outside this project?
- Is the requested technical solution actually necessary?

Produce an outcome brief:

```markdown
Outcome:
Primary scenario:
Exceptional scenarios:
Success observation:
Non-goals:
Known external constraints:
```

The outcome must be understandable without naming an architecture.

#### Gate: problem accepted

The team, client, or authorized decision maker agrees on the problem and intended result without relying on the proposed implementation.

---

### Step 2: Perform a preliminary risk classification

Classify the consequences of being wrong:

| Risk | Typical change | Minimum treatment |
|---|---|---|
| Low | Local, reversible, no persistent or sensitive data | Outcome, acceptance criteria, focused review, automated checks |
| Medium | Persistent state, shared API, dependency, or important workflow | Requirements, invariants, compatibility, integration evidence, observable rollout |
| High | Privacy, money, destructive migration, major availability, or cross-system coordination | Relevant assurance modules, explicit owners, staged rollout, tested recovery |
| Critical | Safety, major regulation, irreversible data, consensus, or very high financial harm | Independent review, stronger evidence, rehearsal, controlled approval, exercised recovery |

The preliminary classification determines:

- which assurance modules apply;
- which documents and evidence are required;
- who may approve the work;
- whether the assigned engineer is authorized to own it; and
- whether independent expert review is required.

Refine the classification after requirements and failure consequences become clearer.

#### Gate: preliminary risk accepted

The project has an initial risk level, relevant assurance modules, review authority, and explicit assumptions.

---

### Step 3: Validate and specify requirements

Translate the outcome into obligations using this order:

```text
Real-world outcome
  -> validated requirement
  -> verification method
  -> design
  -> evidence
```

For every material requirement, ask:

- Where did it come from?
- What evidence supports it?
- What failure does it prevent?
- What happens if it is removed?
- Is it a business truth, policy, security requirement, SLO, external contract, operability requirement, assumption, or design constraint?
- Under which conditions and thresholds must it hold?
- How will the team prove it before selecting the design?

Define verification before design. “We will test it later” means the requirement is not ready.

#### Outputs

- requirement records;
- acceptance criteria;
- verification methods;
- assumptions and unknowns;
- conflicts and trade-offs;
- non-goals;
- and an initial traceability matrix.

#### Gate: requirements ready

Material requirements are necessary, intentional, bounded, solution-neutral where possible, unambiguous, feasible, verifiable, and traceable.

---

### Step 4: Build the correctness model

Ask:

> What must remain true when requests repeat, overlap, time out, arrive out of order, or fail halfway through?

Separate:

- hard invariants;
- convergence requirements;
- business policies;
- service-level objectives;
- external contracts;
- security and privacy requirements;
- and derived-view expectations.

Examine:

- duplicate requests;
- concurrent requests;
- stale data;
- retries after timeouts;
- partial commits;
- invalid transitions;
- dependency failure;
- message duplication and reordering;
- and recovery.

#### Outputs

- invariant catalog;
- policy catalog where needed;
- consistency promises;
- failure model;
- and required evidence.

#### Gate: correctness review

Every material requirement is represented by an invariant, policy, SLO, external contract, threat control, or explicit acceptance behavior. Hard rules have an enforcement point capable of preventing invalid commits.

---

### Step 5: Assign authority and boundaries

Identify exactly one authoritative model for every fact that can change.

For each mutable fact, ask:

- Which model may decide and change it?
- Which other models may copy it?
- Are those copies explicitly derived?
- Which rules must change together?
- Does a proposed boundary split a hard invariant?
- Is a separate process or database required, or only a model boundary?

State that must change atomically should normally be colocated. A bounded context is not automatically a service or database.

#### Outputs

- authority table;
- bounded-context definitions;
- context map;
- transaction and aggregate boundaries;
- upstream and downstream contracts;
- and consistency promises for copied facts.

#### Gate: ownership review

Every mutable fact has one authority, every hard rule can be protected within a valid consistency boundary, and derived views cannot silently become sources of truth.

---

### Step 6: Derive the minimum architecture

For every architectural component, complete:

```text
We need <component>
because <validated obligation>
cannot be satisfied by <simpler alternative>,
as demonstrated by <evidence>.
```

Apply this order:

1. Question the requirement.
2. Delete unsupported requirements and components.
3. Simplify what remains.
4. Optimize measured bottlenecks.
5. Accelerate feedback and delivery.
6. Automate stable, necessary work.

Before deleting a component, ask what truth it protected and what will protect that truth afterward.

Address relevant assurance concerns while choosing the design:

- product and user validation;
- security, privacy, and abuse;
- data lifecycle;
- compatibility and migration;
- reliability and recovery;
- performance, capacity, and cost;
- regulatory obligations;
- and formal or property verification for large state spaces.

#### Outputs

- architecture-justification table;
- selected and rejected alternatives;
- model and process boundaries;
- dependency direction;
- assurance mechanisms;
- release-transition approach;
- operational implications;
- and requirement-to-design traceability.

#### Gate: architecture and transition ready

Every material component traces to a validated obligation. The team has shown why a simpler design is insufficient and has addressed the relevant security, data, compatibility, capacity, operational, and recovery consequences.

---

### Step 7: Discover the complete work and create a forecast

Plan across six dimensions:

```text
Understand
Decide
Build
Verify
Operate
Learn
```

These dimensions prevent the plan from containing only coding tasks.

Include:

- remaining discovery;
- open decisions;
- implementation;
- tests and evidence;
- security and privacy;
- database migration and compatibility;
- integration;
- environments and infrastructure;
- release and observation;
- recovery and reconciliation;
- documentation and training;
- client acceptance;
- post-release measurement;
- cleanup and simplification.

For every deliverable, record:

- outcome contribution;
- completion evidence;
- quality bar;
- predecessors and successors;
- owner, contributors, and reviewers;
- effort and elapsed duration;
- uncertainty;
- and latest useful completion.

Build backward from client or user acceptance. Model people and scarce roles through time. Expose decisions, review queues, external dependencies, and transitions that control completion.

Produce a forecast with a range, confidence, assumptions, largest uncertainties, and reforecast triggers.

```text
Current forecast: 4–6 weeks
Confidence: moderate
Conditions:
  - policy decision completed by 15 July
  - production-like data available for migration testing
Largest uncertainty:
  - migration duration and lock behavior
Reforecast trigger:
  - migration rehearsal exceeds the release window
```

An estimate is a forecast, not yet a promise.

#### Gate: plan and forecast review

The complete work, decisions, dependencies, quality bars, capacity, uncertainty, release obligations, and learning work are visible enough to support a decision.

---

### Step 8: Review and make the execution commitment

Review in this order:

1. Is the outcome correct and valuable?
2. Are the requirements valid and verifiable?
3. What must remain true?
4. Who controls every changing fact?
5. What can race or fail?
6. Why does each architectural component exist?
7. Is there a simpler valid design?
8. Is every obligation connected to evidence?
9. Has the complete work been discovered?
10. Is the forecast credible?
11. Can the deadline be accepted without sacrificing mandatory quality?
12. Are release, recovery, ownership, and operational responsibilities understood?

The review ends with one explicit result:

- accepted;
- accepted with named experiments;
- revise requirements;
- revise architecture or plan;
- or rejected because cost or risk exceeds value.

Only after sufficient evidence exists should the team convert the forecast into a commitment.

---

### Step 9: Establish the execution baseline

Before active implementation, record:

- promised outcome and acceptance conditions;
- deadline, its source, and whether it is truly fixed;
- current forecast and confidence;
- mandatory quality bars;
- mandatory, optional, and excluded scope;
- deliverables and dependencies;
- decision owners and latest responsible dates;
- person-by-time or role-by-time capacity;
- milestones and high-risk transitions;
- risks and unknowns;
- leading indicators and stop conditions;
- client communication cadence;
- replanning triggers;
- and escalation path.

The baseline is not frozen reality. It is the reference against which change and variance are understood.

---

### Step 10: Implement the smallest complete vertical outcome

Build a small complete path through the system:

```text
User action
  -> application operation
  -> business rules
  -> persistence
  -> response
  -> tests
  -> operational evidence
```

Implementation follows clean boundaries:

- domain code expresses business state and transitions;
- application code coordinates outcomes;
- infrastructure implements persistence and external integrations;
- presentation translates external input and output;
- composition selects implementations;
- derived views remain non-authoritative.

During implementation:

- limit work in progress;
- integrate frequently;
- verify requirements continuously;
- test high-risk assumptions early;
- rehearse transitions before the deadline depends on them;
- update evidence-based milestones;
- and communicate material variance.

Quality is not postponed to a later testing phase.

---

### Step 11: Run the execution control loop

Throughout implementation, integration, review, and release:

```text
Observe current evidence and state
  -> compare with the plan and quality bars
  -> identify material variance and its cause
  -> choose an intervention
  -> assign the action and decision time
  -> execute
  -> verify the effect
  -> update the forecast
  -> communicate while choices remain
```

Report:

- evidence completed;
- quality bars at risk;
- controlling work;
- next transition;
- blocker and blocker age;
- decisions due;
- dependency, scope, and capacity changes;
- material variance and cause;
- intervention in progress;
- current forecast and confidence;
- and stakeholder action required.

Do not report only activity or percentage complete.

---

### Step 12: Produce release evidence

Before release, prove the claims appropriate to the risk:

- functional behavior;
- invariants and concurrency;
- retries and idempotency;
- security, privacy, and abuse controls;
- external contracts;
- migration and compatibility;
- performance, capacity, and cost;
- deployment behavior;
- observability;
- recovery and reconciliation.

Prepare:

- an identifiable production artifact;
- rollout stages;
- advance and stop signals;
- rollback or roll-forward conditions;
- dashboards and alerts;
- an operational owner;
- runbooks;
- production smoke tests;
- and authorized acceptance of residual risk.

#### Gate: release evidence ready

Required evidence has passed, operational controls are ready, the release transition is understood, and remaining risk has an authorized owner.

---

### Step 13: Release in controlled stages and operate

The release owner:

1. confirms entry evidence;
2. deploys the identified artifact;
3. performs schema, data, configuration, and code transitions in the planned order;
4. observes advance and stop signals;
5. runs production smoke tests and critical user paths;
6. verifies migrations, backfills, and derived views;
7. rolls forward, rolls back, or suspends when required;
8. communicates production state; and
9. confirms operational ownership and escalation.

Code entering production is not project completion.

#### Gate: production behavior accepted

Critical user paths work, staged-rollout signals remain within limits, transition work is complete or progressing within agreed bounds, and no stop condition remains active.

---

### Step 14: Confirm the outcome, learn, and simplify

After sufficient production evidence exists, ask:

- Did the user or business outcome improve?
- Did every mandatory quality bar hold?
- Which assumptions were confirmed or rejected?
- Which work was discovered late?
- Which question would have exposed it earlier?
- How did actual effort and duration compare with the forecast?
- Which defects escaped?
- What did support and operations experience?
- Which temporary mechanisms can be removed?
- Which requirement, architecture decision, test, signal, or planning rule should change?

#### Outputs

- outcome review;
- estimate-versus-actual evidence;
- validated and rejected assumptions;
- requirement, design, test, and runbook updates;
- process corrections;
- cleanup and simplification work;
- reusable estimation history;
- and training material.

#### Gate: learning closed

Production and execution evidence has produced explicit decisions. Temporary mechanisms have been removed or assigned an owner and expiry, and the next plan can use what was learned.

## How the Existing Documents Fit Together

| Document | Function |
|---|---|
| [Engineering Design System](ENGINEERING_DESIGN_SYSTEM.md) | Main reasoning spine from outcome through operation |
| [Ambiguous Project Discovery](AMBIGUOUS_PROJECT_DISCOVERY.md) | Stage 0 for converting unclear client language into an engineerable outcome |
| [Design to Requirements](DESIGN_TO_REQUIREMENTS.md) | Converts outcomes into valid, verifiable obligations |
| [Invariant-Driven Architecture](INVARIANT_DRIVEN_ARCHITECTURE.md) | Derives correctness, authority, and architecture from business truths |
| [Strategic DDD Guide](STRATEGIC_DDD_GUIDE.md) and [Context Map](CONTEXT_MAP.md) | Model the domain, language, ownership, and context relationships |
| [Engineering Planning and Estimation](ENGINEERING_PLANNING_AND_ESTIMATION.md) | Discovers complete work and produces a decision-useful forecast |
| [Engineering Execution Management](ENGINEERING_EXECUTION_MANAGEMENT.md) | Controls quality, work, people, dependencies, time, and communication |
| [Delivery Assurance Gaps](DELIVERY_ASSURANCE_GAPS.md) | Selects risk controls, assures release, and closes production learning |
| [Human-Centered Systems and Execution](HUMAN_CENTERED_SYSTEMS_AND_EXECUTION.md) | Protects sustainable human capacity, agency, dignity, and health |

## Human Invariant

The following condition applies to every lifecycle stage:

> Delivery must not depend on repeatedly violating sustainable human capacity, dignity, agency, or health.

Planning tools should reveal overload and protect capacity, not fill every available minute. Ownership must include authority. Early reporting of uncertainty should be rewarded. Overtime is exceptional incident response, not the normal reconciliation mechanism for inaccurate plans.

## Operational Gaps Still to Be Standardized

This lifecycle establishes the order. A complete employee-facing SOP still needs:

1. a standard project-intake form;
2. accept, reject, and discovery-only routing;
3. authorization rules connecting engineer capability to project risk;
4. role and decision-right definitions;
5. artifact locations, naming, and versioning;
6. lightweight, standard, high-risk, and critical workflow variants;
7. reviewer assignment and response expectations;
8. tool integration for source control, project tracking, CI/CD, and status;
9. student training and capability gates for every lifecycle stage;
10. business handoff for cost, contract, payment, and prior promises; and
11. ownership for maintaining and improving the lifecycle.

These operational details should implement the lifecycle without changing its governing order.

## Compact Sequence

```text
Discover ambiguity when necessary.
Frame the outcome.
Classify risk.
Validate requirements and define proof.
Model correctness and failure.
Assign authority and boundaries.
Derive the minimum architecture and assurance.
Discover all work and forecast it.
Review before committing.
Baseline the execution system.
Build the smallest complete vertical outcome.
Control execution through evidence and early communication.
Prove release readiness.
Release and operate in controlled stages.
Use production evidence to learn and simplify.
```
