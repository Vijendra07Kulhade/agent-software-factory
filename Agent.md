# Agent.md — Self-Healing Software Factory

## Purpose & Core Design Principles
This factory is an orchestration layer for software delivery and improvement. Its core design principles are **observable**, **customizable**, and **reusable**.
* **Observability:** Agents observe running software state directly in the environments where the software is deployed, using telemetry, logs, traces, dashboards, and monitoring systems.
* **Customizability:** The system supports specialized agents, skills, and toolchains tailored to different architectures, technologies, and workflows.
* **Reusability:** The factory is composed of reusable agents, skills, and tools that can be assembled into different execution paths without rewriting core logic.

---

## Entry Point: Ticket Intake
The factory does not begin from code or ad hoc prompts. The canonical entry point is a work item created in a ticketing system, primarily GitHub Issues and Jira.

### Intake Model
* **Ticketing System as Source of Truth:** Incoming work originates from GitHub Issues, Jira, or similar systems.
* **Collector Agents:** Customizable cron agents or scheduled pollers continuously collect newly created or updated tickets.
* **Normalization Layer:** Collector agents convert raw ticket data into a common internal work-item schema. This includes:
  * source system
  * external ID
  * title
  * description
  * labels / tags
  * priority
  * assignee
  * project / repository
  * status
  * created / updated timestamps
  * metadata
* **Canonical Work Item:** The normalized ticket becomes the internal unit of work that flows through the factory.

### Why This Matters
This ensures all downstream agents operate on a consistent representation of the task, regardless of whether the source was GitHub Issues, Jira, or another tracker. The factory’s orchestration logic can then be applied uniformly across different intake channels.

---

## Operating Phases & Assembly Line

### 1. Intake & Collection Phase
* **Applicability:** External work requests entering through GitHub Issues or Jira.
* **Objective:** Detect new or updated tickets, fetch their content, and normalize them into the internal work-item format.
* **Capabilities:**
  * Scheduled collector agents (cron-style jobs) poll ticketing systems.
  * Integration adapters fetch issue metadata, comments, labels, status, and linkages.
  * Internal work items are created and stored for orchestration.

### 2. Triage Phase
* **Applicability:** Determining whether an incoming ticket is actionable and what kind of downstream workflow it needs.
* **Objective:** Classify work by readiness and route it to the correct stage.
* **Capabilities:**
  * Analyze issue quality, scope, and completeness.
  * Apply a single readiness label such as `Ready to implement`, `Ready to spec`, `Needs info`, or `Wait to implement`.
  * Route tickets to specification, implementation, or information-gathering flows.

### 3. Specification Phase
* **Applicability:** Writing structured specifications for issues requiring definition or design work before implementation.
* **Objective:** Produce clear requirements, constraints, and acceptance criteria before code is generated.
* **Capabilities:**
  * Generate core artifacts such as `PRODUCT.md` and `TECH.md`.
  * Translate tickets into user stories, UX expectations, system behaviors, and technical architecture.
  * Require human review and alignment before implementation proceeds.

### 4. Development & Implementation Phase
* **Applicability:** Transforming approved specs or clearly scoped issues into production-ready code.
* **Objective:** Build the solution, validate behavior, and prepare a reviewable change.
* **Capabilities:**
  * **Design & Code:** Implementation agents fetch context, inspect codebases, write code, and validate changes.
  * **Verification:** Built-in verification agents run tests and validate behavior using browser or computer-use workflows when appropriate.
  * **Code Review:** Review agents inspect diffs for correctness, edge cases, and security issues before handoff.

### 5. Review & Closure Phase
* **Applicability:** Ensuring quality before final acceptance or merge.
* **Objective:** Confirm that the change matches the issue and meets required standards.
* **Capabilities:**
  * Automated review of implementation quality.
  * Link outputs back to the original issue or ticket.
  * Capture evidence, final status, and any follow-up items.

---

## Nested Architecture: Agents, Skills, and Tools
The system is organized as a nested execution model.

### 1. Agent Layer
Agents are top-level orchestrators responsible for decision-making, coordination, and workflow management.
* **Collector Agents:** Pull tickets from GitHub or Jira and normalize them.
* **Triage Agent:** Classifies work and decides routing.
* **Spec Agent:** Coordinates product and technical specification work.
* **Implementation Agent:** Executes code changes and validation.
* **Review Agent:** Performs quality and correctness checks.
* **Observer / Outer-Loop Agents:** Monitor outcomes, synthesize human feedback, and improve factory performance over time.

### 2. Skill Layer
Skills are specialized reusable capabilities that agents delegate to for domain-specific work.
* Product specification skills
* Technical architecture skills
* Testing and verification skills
* Security and review skills
* Monitoring and diagnostics skills
* Workflow optimization skills

### 3. Tool Layer
Tools are the execution primitives used by agents and skills.
* Ticket APIs (GitHub Issues, Jira)
* Code search and repository tools
* Build and test runners
* Browser or UI validation tools
* Logging, monitoring, and observability tools
* Review and diff-analysis utilities

This layering allows the system to stay modular: a collector agent can be specialized for a specific ticketing system without changing the orchestration model.

---

## Execution & Handoff Protocols
* **Work Items:** Maintained with full source context from intake through all factory handoffs, whether originating from GitHub, Jira, Linear, Slack, or monitoring webhooks.
* **State Passing & Artifacts:** Structured outputs such as `PRODUCT.md`, `TECH.md`, and `review.json` are used as contracts between independent stages.
* **Issue Traceability:** Every implementation should be traceable back to the originating ticket or issue ID.
* **Verification & Evidence:** Where relevant, validation captures screenshots, recordings, logs, or test evidence to reduce human review overhead.

---

## Self-Improvement & Feedback Loops
* **Continuous Optimization:** Outer-loop observer agents analyze human corrections, validate patterns, and propose workflow improvements.
* **Evals & Metrics:** The factory tracks throughput, cycle time, quality, and token cost to improve automation efficiency and reduce defect rates.
* **Adaptive Behavior:** Skills and agent policies evolve over time based on recurring failure modes, successful patterns, and human feedback.

---

## High-Level Factory Summary
The self-healing software factory operates as a ticket-driven orchestration system:
1. Collector agents ingest work from GitHub Issues and Jira.
2. Triage agents decide what kind of work it is and what readiness state it has.
3. Specification agents define the desired outcome when needed.
4. Implementation agents build and validate the solution.
5. Review agents verify correctness and traceability.
6. Observer agents improve the system over time.

This creates a reusable, configurable software delivery pipeline built around human-visible work items rather than ad hoc requests.