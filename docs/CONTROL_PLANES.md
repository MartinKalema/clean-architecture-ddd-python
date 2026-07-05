# Who Creates the Topics? From Auto-Create to Control Planes

This guide explains, in simple English, how infrastructure resources
(Kafka topics here, but the same applies to databases, queues, and
buckets) get created and governed as a company grows — and what this
repository does about it.

---

## 1. Two kinds of work: data plane and control plane

Think of the post office again (see `SAGAS_AND_CONSISTENCY.md`,
section 11). Clerks handling envelopes are the **data plane** — the
actual work. Somewhere in the back, someone decides *how many lines
exist, who gets a counter, and what the rules are*. That is the
**control plane**. It never touches an envelope; it manages the
machinery that does.

Creating a Kafka topic is control-plane work. The question of this
guide is: **who is allowed to do it, and how?**

---

## 2. The three eras

### Era 1: the ticket

You email the platform team: "we need a topic." Someone reads it on
Tuesday, asks about your throughput, creates it on Thursday.

Safe, because a human applies judgement. Slow, because a human applies
judgement. As the company grows, the platform team drowns in tickets
and everyone waits.

### Era 2: the wild west

Anyone creates anything: `auto.create.topics.enable=true`, shared admin
access, no rules. Fast — and chaos. Nobody knows who owns the topic
called `test-final-v2`, why it has 400 partitions, or whether deleting
it breaks billing.

This repository caught a live example of the wild west (section 5
below): a *consumer* accidentally decided a topic's partition count,
just by asking about it.

### Era 3: self-service

A vending machine with rules. You go to an internal website or API and
say "my team needs a topic, roughly this much traffic." The system —
not a person — checks that your team exists, applies the naming rules,
picks a partition count from your traffic estimate, stamps your team as
**owner**, creates the topic, and starts a monthly cost report.

Thirty seconds, no human involved, and every guardrail the platform
team cares about was enforced automatically.

> **Self-service means the platform team's judgement is encoded in
> software, so users serve themselves without losing the safety a human
> reviewer used to provide.**

Humans only see the exceptions: "I need 200 partitions" goes to an
approval queue; "I need a normal topic" never does.

---

## 3. How much work is it to build?

Three honest tiers. Each exists to make the safe path also the lazy
path — and each costs more than the one before.

### Tier 1 — days: self-service by pull request

A git repository of resource definitions (YAML or Terraform), a CI
pipeline that applies them, and a `CODEOWNERS` file so the platform
team reviews changes.

This *is* a self-service control plane — the portal is GitHub. The
registry is git history. The audit log is `git log`. The approval
workflow is a pull-request review.

**Most companies should stop here.** The Debezium connector configs in
`deploy/debezium/` are the embryo of this tier: topic shape, declared
in a reviewed file.

### Tier 2 — a quarter, then forever: the portal

A real service, built from these parts:

| Part | Plain meaning |
| --- | --- |
| Registry | A database of what exists and who owns it |
| Policy engine | The encoded judgement: quotas, naming rules, capacity formulas |
| Executor | The thing that actually calls Kafka's admin API |
| Auth + audit | Who may do what, and a record of who did what |
| UI / API / CLI | The counter where people ask |

Two to four engineers for a few months to launch. But the trap is in
the word "then forever": **a control plane is a product**. It has
users, bugs, feature requests, on-call, and a roadmap — permanently.
You are not building a tool; you are founding a small internal company.

Build this when the pull-request tier drowns: when "waiting for
platform review" is a real, measurable tax across dozens of teams.

### Tier 3 — years: the big-tech version

LinkedIn, Uber, and Netflix add what only their scale demands:
automatic capacity placement (which cluster should this topic live
on?), continuous rebalancing of partitions across brokers, chargeback
(each team pays for what it uses), migration tooling, and multi-region
awareness. Dedicated teams own this permanently.

Justified by thousands of topics and hundreds of teams. Nothing
smaller needs it.

### The climbing rule

Same logic as scaling the pipeline: **friction is the meter**. Climb a
tier only when the current one's friction is measurably hurting — not
because the next tier sounds impressive. A ticket queue that answers in
an hour does not need a portal. A pull-request pipeline that merges in
a day does not need a UI.

---

## 4. What this repository does

Tier 0-going-on-1, deliberately:

- **The broker refuses to improvise.** `auto.create.topics.enable` is
  off (`docker-compose.yaml`), as in production. No resource exists
  unless someone deliberately created it.
- **Each topic has exactly one owner who declares its shape.** The
  Debezium connectors declare their data topics
  (`topic.creation.default.partitions: 4` in
  `deploy/debezium/register-*.json`). The messaging layer creates its
  own dead-letter topics on first use
  (`KafkaClient._ensure_topic`).
- **Declarations live in reviewed files.** Changing a partition count
  is a pull request, not a shell command someone forgets.

Moving to the cloud, the same declarations become Terraform resources
(`google_managed_kafka_topic`, or the Confluent provider on AWS) — the
tier-1 pattern with a cloud executor.

---

## 5. The lesson we proved live

While making this change, a live test demonstrated *why* auto-create
must be off for any of this to matter:

1. A topic was deleted, expecting the connector to recreate it with its
   declared 4 partitions.
2. It came back with **1 partition** — created not by the connector,
   but by a *consumer* whose routine metadata request hit the broker
   first. With auto-create on, the broker grants whoever asks first,
   with defaults.
3. With auto-create off, the same test produced the connector-declared
   4 partitions.

The general rule: **declared configuration is only real when the
improvised path is closed.** A rulebook nobody is forced to follow is a
suggestion. This is true of topic creation, database migrations, and
every other control-plane decision: turn off the accidental path, or
the accidental path wins the race.

---

## Quick glossary

| Term | Plain meaning |
| --- | --- |
| Data plane | The machinery doing the actual work (moving messages) |
| Control plane | The machinery managing the machinery (creating topics, setting rules) |
| Self-service | Users get resources instantly; the platform's judgement is enforced by software, not meetings |
| Registry | The list of what exists and who owns it |
| Policy engine | Rules as code: naming, quotas, capacity formulas |
| Executor | The component that actually performs the change |
| Chargeback | Each team pays (or at least sees the bill) for what it uses |
| Auto-create | The broker improvising a resource for whoever asks first — the enemy of all of the above |
