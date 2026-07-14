# Ambiguous Project Discovery

## Purpose

This document defines the discovery stage used when a client gives an ambiguous request such as:

> I want a talent funnel.

That statement is not yet an engineering outcome or validated requirement. It is a proposed concept that may contain several possible problems, purposes, actors, boundaries, and solutions.

The engineer must first expand the ambiguity into a whole-system view and then compress that understanding into an accepted outcome, first valuable increment, and body of evidence that can enter the [Engineering Project Lifecycle](ENGINEERING_PROJECT_LIFECYCLE.md).

This process is **Stage 0: Discover and Map the Problem System**.

## Governing Principle

```text
Name the important things
  -> connect them
  -> identify time and delay
  -> attach facts and uncertainty
  -> quantify where honest
  -> simulate decisions
  -> define the outcome and boundary
  -> encode stable judgment into software
```

Map before numbers. Use numbers before software. Automation multiplies both sound and incomplete judgment.

## Position in the Engineering System

```text
Ambiguous client request
  -> separate problem, purpose, and proposed solution
  -> reconstruct the current system
  -> map actors, value, time, rules, money, risks, and unknowns
  -> walk each actor through the system over time
  -> model stocks, flows, feedback, delays, and constraints
  -> convert unknowns into investigations and decisions
  -> define the purpose and 100-point outcome
  -> choose the first valuable system boundary
  -> review the discovery with the client
  -> enter Stage 1 of the Engineering Project Lifecycle
```

## Discovery Workflow

### Step 0.1: Record the request without interpreting it

Write exactly what the client said. Do not improve the wording yet.

Example:

> I want a talent funnel.

Separate the layers:

| Layer | Question | Initial state |
|---|---|---|
| Problem | What is going wrong or remains impossible today? | Unknown |
| Purpose | What result should improve, for whom, and why? | Unknown |
| Proposed solution | What does the client currently imagine might help? | Talent funnel |
| Deadline | When is the result needed, and what makes the date meaningful? | Unknown |
| Success evidence | What observation would prove improvement? | Unknown |

Do not begin with framework, database, interface, feature, or estimate questions. Begin with:

- What does “talent” mean in this context?
- What does “funnel” mean?
- What problem caused this request?
- What happens today?
- Who experiences the problem?
- What result cannot currently be produced?
- Why does the result matter now?
- What would happen if nothing changed?

#### Output

- verbatim client request;
- initial separation of problem, purpose, solution, deadline, and evidence;
- named discovery sponsor;
- and an initial question register.

---

### Step 0.2: Reconstruct the current system

Ask the client to demonstrate what happens today. Do not begin by asking for desired software features.

For a talent funnel, investigate:

- how people learn about opportunities;
- how they apply;
- who reviews applications;
- how candidates are assessed;
- who makes acceptance and rejection decisions;
- which evidence and policies they use;
- how long each stage takes;
- where candidates wait, withdraw, or disappear;
- how decisions are communicated;
- what happens after acceptance;
- how candidates are trained;
- who determines project readiness;
- how people are assigned to projects;
- what happens when an assignment succeeds or fails;
- whether project performance changes future selection and training; and
- which parts rely on spreadsheets, forms, email, chat, paper, memory, or existing software.

Ask for concrete evidence:

- recent applications;
- a recent selection decision;
- current forms and spreadsheets;
- assessment materials;
- messages sent to candidates;
- evaluator time and queues;
- rejection and withdrawal reasons;
- training records;
- project-assignment records;
- examples of successful and unsuccessful candidates;
- and any existing measurements.

The engineer is reconstructing reality rather than collecting opinions about a future application.

#### Output

- current-state process and evidence map;
- current actor journey;
- current systems and data sources;
- observed failures and delays;
- and facts separated from interpretation.

---

### Step 0.3: Build the divergent mind map

The first map should be broad. Its purpose is to expose missing actors, variables, relationships, costs, risks, emotions, and future stages before the team reduces the problem to a table or specification.

For a talent funnel, use these branches:

```text
Talent funnel
├── Purpose and outcomes
│   ├── Business, candidate, and project results
│   └── Evidence of success
├── Actors
│   ├── Candidates, recruiters, and evaluators
│   ├── Trainers, mentors, and engineering reviewers
│   ├── Project managers and clients
│   └── Investors, administrators, and operators
├── Stages
│   ├── Awareness, application, screening, and assessment
│   ├── Selection, onboarding, and training
│   ├── Project readiness and assignment
│   └── Performance, progression, retention, and exit
├── Value
│   ├── Candidate opportunity and growth
│   ├── Company capability and client delivery
│   └── Investor, trainer, and reviewer outcomes
├── Rules and authority
│   ├── Eligibility, assessment, selection, and progression
│   ├── Rejection and appeal
│   └── Data access and retention
├── Time
│   ├── Cohort dates, waiting time, and training duration
│   └── Project and decision deadlines
├── Capacity
│   ├── Evaluators, mentors, and reviewers
│   └── Training places and suitable projects
├── Data
│   ├── Identity, application, assessment, and decision
│   └── Capability, assignment, and performance
├── Risks
│   ├── Bias, privacy, fraud, and false scoring
│   └── Dropout, mentor overload, and unsafe assignment
├── Money
│   ├── Recruitment, training, review, and rework
│   └── Project revenue and attrition
└── Unknowns
    ├── Volumes, conversion rates, and quality thresholds
    └── Integrations, legal constraints, and assumptions
```

The map is intentionally divergent. It is not yet the system boundary, specification, data model, or task list.

#### Output

- whole-system mind map;
- missing-actor list;
- new questions;
- possible interpretations of the request;
- and contexts that should be modeled separately before combination.

---

### Step 0.4: Separate actors and purposes

Different actors can use the same phrase while expecting different systems.

| Actor | Possible value sought |
|---|---|
| Candidate | Fair opportunity, useful feedback, career growth, timely communication |
| Recruiter | Enough suitable candidates without excessive manual work |
| Evaluator | Reliable evidence and manageable evaluation load |
| Trainer | Students whose gaps are known and trainable |
| Engineering lead | People who can safely own defined classes of work |
| Project manager | Engineers available when project demand arrives |
| Client | Reliable delivery rather than a large number of trainees |
| Investor | Repeatable conversion with credible economics |
| Company | Capability, revenue, trust, and institutional knowledge |

These purposes can conflict. Investors may want larger intake while trainers have limited capacity. Clients may want project-ready engineers while candidates need a fair opportunity to develop. Management may seek lower cost while engineering requires stronger quality evidence.

Do not combine these into one average idea of value. Record what each actor gives, receives, values, risks, controls, and needs in order to continue participating.

#### Output

- actor and value map;
- conflicting-purpose register;
- power and decision-right observations;
- and value gaps that can destabilize the system.

---

### Step 0.5: Determine the actual purpose

“Talent funnel” could describe several different systems:

1. generate more applications;
2. identify candidates with potential;
3. select people fairly and quickly;
4. train beginners into project-ready engineers;
5. supply projects with engineers who perform successfully; or
6. build a repeatable national engineering-capability pipeline.

Each purpose creates different measurements and behavior.

- Optimizing applications can create thousands of unqualified applicants.
- Optimizing assessment pass rates can produce candidates who pass tests but cannot engineer software.
- Optimizing training completion can pressure trainers to lower the standard.
- Optimizing assignment can place people onto projects before they are ready.
- Optimizing billable hours can remove the practice time required for capability growth.

For a student-based engineering business, a stronger purpose is:

> Convert suitable graduates into engineers who can safely deliver defined classes of software work at the required quality and deadline, and use their later project performance to improve future recruitment, assessment, training, and assignment.

This purpose means the funnel does not end at “accepted.” It closes the feedback loop through training, project delivery, and later performance.

#### Output

- candidate purpose statements;
- consequences of optimizing each purpose;
- selected purpose;
- rejected purposes and non-goals;
- and evidence that would show whether the selected purpose is being achieved.

---

### Step 0.6: Model stocks, flows, feedback, delays, and constraints

The talent funnel is not merely a sequence of screens. It is a stock-and-flow system.

| Stock | Inflows | Outflows |
|---|---|---|
| Prospective candidates | Outreach, referrals, university relationships | Applications, loss of interest |
| Applicants | Submitted applications | Withdrawal, rejection, assessment |
| Assessed candidates | Completed assessments | Selection, rejection, reassessment |
| Trainees | Accepted candidates | Dropout, dismissal, progression |
| Project-ready engineers | Successful training and capability gates | Assignment, skill decay, departure |
| Assigned engineers | Project allocation | Completion, reassignment, exit |
| Mentor capacity | Experienced people, improved teaching systems | Mentoring demand, turnover, overload |
| Review queue | Student designs and changes submitted | Competent reviews completed |
| Company capability | Practice, feedback, production work, teaching, documentation | Turnover, forgetting, weak assignments |
| Client trust | Reliable delivery and early communication | Defects, surprises, missed commitments |

Example overload loop:

```text
More candidates accepted
  -> more trainees
  -> more demand for mentors
  -> slower feedback
  -> weaker learning
  -> more defects and rework
  -> less available mentor capacity
```

Example capability loop:

```text
Better training
  -> stronger delivery
  -> greater client trust
  -> better projects
  -> richer experience
  -> more capable engineers and mentors
  -> better training
```

The safe funnel rate is constrained by the smallest relevant flow:

```text
Minimum of:
  candidate supply
  assessment capacity
  training capacity
  mentor capacity
  review capacity
  suitable project demand
```

Increasing intake without increasing the limiting capacity can reduce the number of successful engineers.

#### Output

- stock-and-flow model;
- reinforcing and balancing loops;
- delays and thresholds;
- bottleneck hypothesis;
- and measurements needed to validate the model.

---

### Step 0.7: Walk every actor through time

Run the complete journey for each important actor. At every moment ask:

1. Who owns this moment, fact, decision, or result?
2. Why is this choice being made rather than another?
3. What does it cost in money, time, attention, complexity, risk, and human energy?
4. What does it communicate to the people affected?
5. What fails if nobody thinks about it?

#### Candidate journey

```text
Discovers opportunity
  -> reads requirements
  -> decides whether to apply
  -> submits application
  -> waits
  -> receives assessment
  -> completes assessment
  -> waits again
  -> receives decision
  -> joins training
  -> receives feedback
  -> passes capability gates
  -> joins a suitable project
  -> receives project evaluation
```

At each transition ask:

- Who communicates?
- How long can the person wait?
- What do they know about their status?
- Can they correct an error?
- What happens when a message is not delivered?
- What does silence communicate?
- What personal information is exposed?
- Is the decision explainable?
- Is an appeal or correction possible?

#### Company journey

```text
Predict project demand
  -> define needed capability
  -> attract candidates
  -> evaluate potential
  -> select within training capacity
  -> train
  -> verify readiness
  -> assign to suitable project risk
  -> review delivery
  -> measure performance
  -> improve selection and training
```

#### Trainer and reviewer journey

Ask:

- How many students enter each week?
- How much work does each submit?
- How long does review take?
- Which submissions require scarce judgment?
- What happens when the queue grows?
- Which information is required before review?
- Which repeated feedback should become teaching, automation, or a quality gate?
- When is the same reviewer required by several projects at once?

#### Output

- actor-by-time journeys;
- transition inventory;
- unowned moments;
- communication obligations;
- capacity collisions;
- and high-weight moments needing stronger preparation.

---

### Step 0.8: Convert unknowns into discovery work

Classify each important unknown:

| Discovery | Appropriate response |
|---|---|
| Missing fact | Research, interview, measurement, prototype, or experiment |
| Open decision | Options, evidence, decision owner, and deadline |
| Assumption | Validation method, owner, and expiry condition |
| External dependency | Coordination, contract clarification, fallback, and escalation |
| Material risk | Prevention, mitigation, detection, recovery, transfer, or authorized acceptance |
| Hard constraint | Enforcement and verification |
| Nonmaterial question | Record why no plausible answer changes the decision |

Example:

```text
Question:
How many applications must evaluators process each week?

Why it matters:
It affects workflow design, evaluator capacity, automation, and response times.

Current state:
Unknown.

Investigation:
Measure the last three recruitment cycles.

Owner:
Recruitment lead.

Decision deadline:
Before selecting the assessment and queue design.

Decision enabled:
Manual review, assisted review, or automated preliminary screening.
```

An unknown is acceptable. An unowned unknown embedded inside an estimate or design is not.

#### Output

- knowledge-state register;
- investigation plan;
- decision register;
- dependency and risk register;
- owners and deadlines;
- and stop conditions preventing premature design or commitment.

---

### Step 0.9: Define the 100-point outcome and system boundary

A proposed complete outcome for the talent system is:

> The company can define a needed engineering capability, receive applications, evaluate candidates using versioned evidence, make an authorized and auditable decision, place accepted candidates into the correct training path, determine project readiness through capability evidence, assign them only to suitable project risk, and use later project performance to improve the selection and training system.

Component quality bars may include:

- candidate experience;
- fair and explainable evaluation;
- timely decisions and communication;
- privacy and access control;
- assessment integrity;
- trainer and reviewer capacity;
- project-readiness evidence;
- correct project matching;
- operational visibility and recovery;
- and economically sustainable conversion.

The complete system may be too large for the first delivery. Define the first valuable vertical increment.

Example:

```text
First increment:
Define one engineering role, accept applications for one cohort, complete one
assessment, make an auditable decision, communicate the result, and enroll
accepted candidates into one training program.

Explicitly deferred:
Automated project matching, AI scoring, university integrations, advanced
analytics, and alumni management.
```

The first increment must remain compatible with the larger purpose. It should not create data or authority decisions that prevent later capability and project-performance feedback.

#### Output

- complete purpose and 100-point outcome;
- component quality bars;
- selected system boundary;
- first valuable increment;
- mandatory, optional, and excluded scope;
- preliminary risk classification;
- and future feedback loops the first increment must preserve.

---

### Step 0.10: Review discovery with the client

The discovery review should answer:

1. What did the client initially request?
2. Which current problem or opportunity exists?
3. What evidence supports it?
4. Who is affected, and what does each actor value?
5. How does the current system behave through time?
6. Which stocks, flows, bottlenecks, delays, and feedback loops matter?
7. Which purposes were possible?
8. Which purpose has been selected, by whom, and why?
9. What defines the complete outcome?
10. Which first increment will be engineered?
11. What is explicitly excluded?
12. Which facts remain unknown?
13. Which decisions, investigations, or dependencies remain open?
14. What is the preliminary risk level?

The review outcome must be explicit:

- discovery accepted;
- discovery accepted with named investigations;
- revise the problem or purpose;
- revise the system boundary;
- or reject the initiative because cost, risk, or weak evidence exceeds the expected value.

#### Gate 0: problem system sufficiently mapped

The team and client understand the current system, desired outcome, material actors, important unknowns, and first delivery boundary well enough to begin formal outcome and requirement validation.

## Entering the Engineering Project Lifecycle

After Gate 0, continue with [Engineering Project Lifecycle](ENGINEERING_PROJECT_LIFECYCLE.md):

1. frame and accept the outcome;
2. refine risk classification;
3. validate requirements and define verification;
4. build the correctness model;
5. assign authority and boundaries;
6. derive the minimum architecture;
7. discover the complete work and forecast it;
8. review before commitment;
9. baseline and control execution;
10. implement vertical outcomes;
11. produce release evidence;
12. release and operate;
13. close learning and simplify.

## Correctness Questions for the Talent-Funnel Example

Possible rules include:

- one application has one authoritative status;
- every assessment submission is tied to one candidate, role, cohort, and assessment version;
- submitted assessment evidence cannot be silently changed;
- every selection decision records its evidence, authorized decision maker, time, and applicable policy;
- only authorized roles can view protected candidate data;
- a candidate cannot be marked project-ready without the required capability evidence;
- the system cannot accept more trainees than approved training capacity without an explicit override;
- project-performance feedback identifies the capability model and project conditions under which it was produced; and
- derived dashboards cannot change authoritative application, capability, or assignment state.

These are candidate obligations, not final requirements. They must still be validated with domain evidence and policy authority.

## Estimating an Ambiguous Project

Do not estimate the complete software product directly from an ambiguous sentence. Provide two forecasts.

### Forecast 1: discovery

Estimate the bounded work needed to produce:

- current-state process and evidence map;
- stakeholder and value map;
- whole-system mind map;
- actor journeys;
- volume and capacity evidence;
- stock-and-flow model;
- purpose and complete outcome;
- risk classification;
- first valuable increment;
- material requirements and unknowns;
- and decisions required before implementation.

Discovery is legitimate engineering work and should have its own outcome, evidence, owner, range, confidence, and acceptance gate.

### Forecast 2: delivery

After discovery, decompose the first increment across:

| Dimension | Talent-funnel work |
|---|---|
| Understand | Candidate journey, current process, volumes, policies, constraints, integrations |
| Decide | Evaluation authority, role model, assessment policy, status model, system boundary |
| Build | Application, assessment submission, review, decision, communication, onboarding |
| Verify | Workflow, authorization, audit, concurrency, privacy, accessibility, client acceptance |
| Operate | Deployment, monitoring, failed-message recovery, support, retention, reconciliation |
| Learn | Conversion, waiting time, evaluator effort, candidate feedback, training and project outcomes |

For every deliverable, record:

- owner;
- completion evidence;
- dependency;
- effort and elapsed duration;
- uncertainty;
- reviewer;
- latest useful completion;
- and reforecast trigger.

## Planning Backward Through Time

Suppose the fixed event is:

> The first cohort must begin training on 1 October.

Build backward:

```text
Cohort begins
  <- accepted candidates complete onboarding
  <- selection decisions communicated
  <- selection review completed
  <- assessments evaluated
  <- assessment window closed
  <- candidates invited
  <- applications screened
  <- application window closed
  <- application system opened
  <- production verification completed
  <- controlled release completed
  <- release evidence approved
  <- complete vertical workflow integrated
  <- implementation and review completed
  <- requirements and architecture accepted
  <- discovery completed
```

Every arrow requires:

- completion evidence;
- owner;
- dependency;
- duration;
- uncertainty;
- quality bar;
- buffer where justified;
- and latest useful completion.

### Parallel tracks

Lay the tracks beside one another:

| Track | Work |
|---|---|
| Client and business | Purpose, policies, role definition, decision authority |
| Candidate experience | Application, assessment, communication, accessibility |
| Engineering | Domain, application, persistence, interfaces |
| Data and security | Privacy, retention, access, audit, abuse |
| Assessment | Rubric, evidence, evaluator workflow |
| Training | Capacity, onboarding, capability model |
| Operations | Deployment, monitoring, support, recovery |
| Communication | Candidate messages, client decisions, project status |
| Review | Requirements, architecture, security, release approval |

The same person may otherwise be scheduled to design the assessment, evaluate candidates, train accepted students, and review engineering work during the same period.

### Scenario-based forecast

Do not provide a single date without its conditions.

```text
Forecast:
10–14 weeks

Confidence:
Low to moderate

Optimistic conditions:
Existing identity, messaging, and assessment policies can be reused.

Most likely conditions:
Assessment workflow and privacy rules need refinement, and one integration
requires additional work.

Pessimistic conditions:
The client has no agreed definition of project readiness, requiring a
capability model and pilot before selection automation can be approved.

Largest uncertainties:
Assessment policy, historical application volume, communication integration,
and evaluator capacity.

Reforecast triggers:
Discovery rejects the assumed workflow, assessment authority changes, or
training capacity is lower than planned.
```

The values above are illustrative. Real ranges must come from the assigned team, evidence, prototypes, dependencies, and historical data.

## Execution Management After Commitment

Establish an execution baseline containing:

- accepted outcome;
- fixed event and its source;
- quality bars;
- mandatory and optional scope;
- dependencies;
- decisions and owners;
- person-by-time capacity;
- evidence-based milestones;
- leading indicators;
- current forecast;
- communication cadence;
- replanning triggers;
- and escalation path.

Run the control loop:

```text
Observe evidence
  -> compare with outcome, quality bars, and forecast
  -> identify variance and cause
  -> choose an intervention
  -> assign owner and decision time
  -> act
  -> verify
  -> reforecast
  -> communicate while choices remain
```

Leading indicators for the example include:

- role definition remains unapproved;
- assessment policy remains undecided;
- application volume exceeds evaluator capacity;
- candidate-message delivery is unreliable;
- review queues grow while new features continue to start;
- training capacity is below accepted-candidate volume;
- security or privacy evidence is incomplete;
- project-readiness criteria remain unknown; or
- the forecast reaches the cohort date without release buffer.

Report achieved evidence:

- role and assessment policy accepted;
- complete candidate journey works in a production-relevant environment;
- authorized review and decision path verified;
- candidate communication tested;
- privacy and audit evidence passed;
- onboarding handoff rehearsed;
- first production application completed;
- and client acceptance received.

Do not substitute activity or percentage-complete reporting for these states.

## Stage 0 Artifact Set

Every material ambiguous project should leave discovery with:

1. verbatim client request;
2. problem, purpose, and proposed-solution separation;
3. current-state evidence and process map;
4. stakeholder and value map;
5. whole-system mind map;
6. actor journeys through time;
7. stocks, flows, feedback loops, delays, and capacity constraints;
8. five-question interrogation;
9. unknown, assumption, risk, dependency, and decision registers;
10. purpose and 100-point outcome;
11. system boundary and non-goals;
12. first valuable vertical increment;
13. preliminary risk classification;
14. discovery forecast and delivery-estimation conditions; and
15. explicit client discovery decision.

## Compact Discovery Sequence

```text
Hear the request without silently fixing it.
Separate problem, purpose, solution, deadline, and evidence.
Observe the current system.
Diverge through a whole-system mind map.
Walk every actor through time.
Model stocks, flows, loops, delays, and constraints.
Turn important unknowns into owned investigations and decisions.
Converge on purpose, quality bars, boundary, and first increment.
Review the discovery with the client.
Only then validate requirements, design, estimate, and commit.
```

## Related Guides

- [Engineering Project Lifecycle](ENGINEERING_PROJECT_LIFECYCLE.md)
- [Engineering Design System](ENGINEERING_DESIGN_SYSTEM.md)
- [Design to Requirements](DESIGN_TO_REQUIREMENTS.md)
- [Invariant-Driven Architecture](INVARIANT_DRIVEN_ARCHITECTURE.md)
- [Engineering Planning and Estimation](ENGINEERING_PLANNING_AND_ESTIMATION.md)
- [Engineering Execution Management](ENGINEERING_EXECUTION_MANAGEMENT.md)
- [Delivery Assurance Gaps and Extension Plan](DELIVERY_ASSURANCE_GAPS.md)
- [Human-Centered Systems and Execution](HUMAN_CENTERED_SYSTEMS_AND_EXECUTION.md)
