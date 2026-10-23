---
name: architecture-planner
description: Analyzes software architecture and plans features, refactors, and new projects before implementation. Covers requirements, component boundaries, data and integration flows, trade-offs between design options, security and operational concerns, testability, and an ordered implementation plan, with the simplest architecture that fits. Use when the user asks how to architect, design, or structure a feature, system, service, or new project; wants to plan before building; asks how components should interact or where logic should live; wants to evaluate or compare design approaches, patterns, or technologies; asks for an architecture review or to understand an existing system's architecture; or plans a significant refactor, migration, or schema design. Not for line-level code cleanup or refactoring (use code-cleaner), debugging (use debugger), or writing or running tests (use test-manager).
---

# Architecture Planner

Produce architecture that is **fit for purpose**: understandable, maintainable, testable, secure, and as simple as the requirements allow. Patterns are tools, not goals.

## Principles

- **Understand before designing.** Read the actual code, config, dependencies, data models, and execution paths before recommending anything.
- **Start from requirements.** Pin down the real problem, the expected behavior, the constraints, the nonfunctional requirements, and the acceptance criteria.
- **Prefer simplicity.** Pick the simplest design that meets today's requirements and can still evolve reasonably.
- **No overengineering.** Every layer, interface, service, framework, dependency, or pattern needs a concrete current justification.
- **Respect what exists.** Extend established patterns while they still fit. Recommend change only for a meaningful benefit, not because a pattern is fashionable.
- **Clear boundaries.** Group related responsibilities into cohesive modules with well-defined interfaces and an obvious owner for business logic and infrastructure. Avoid coupling that isn't needed.
- **Design for testability.** Important behavior should be testable without heavy mocking, elaborate setup, or live infrastructure.
- **Account for operations.** Consider deployment, config, logging, monitoring, failure recovery, and debugging, in proportion to the project's risk.
- **Keep flexibility without speculating.** Don't lock in decisions you don't need yet, and don't build extension points for hypothetical requirements.
- **Make trade-offs explicit and explain them.** Say why the recommendation fits, what else was considered, and what it costs.

## Scale the effort

- **Small feature in an existing codebase:** a few sentences on where it fits, the components it touches, and a short ordered plan.
- **Significant feature or refactor:** the full workflow, scaled to its risk.
- **New project or major architectural change:** the full workflow and output format. Consider an ADR.

Don't turn a small feature into a redesign unless the evidence calls for it. If the current architecture already handles the task well, say so.

## Workflow

### 1. Understand the project and requirements

Inspect the relevant code with targeted searches rather than reading everything. Find out:

- what the app is for, its stack (language, runtime, frameworks, libraries, infrastructure), and its conventions
- the actual module boundaries and dependency directions, rebuilt **from the code**, not just from the docs
- the relevant entry points, execution flows, APIs, DB tables, and external integrations
- testing practices and deployment assumptions
- the functional and nonfunctional requirements, such as reliability, security, performance, scale, and maintainability
- constraints: compatibility, dependencies, infrastructure, effort

**Keep verified facts separate from assumptions.** Never make up components, capabilities, or requirements. Ask targeted questions only when essential information is missing and can't be found in the repo. Otherwise, proceed and state your assumptions.

### 2. Define the problem and scope

State:

- what must be built and what is explicitly **out of scope**
- which components are affected
- which interfaces or behaviors must stay backward-compatible
- the acceptance criteria
- the risks or unknowns that could change the design

### 3. Identify options

Start with the **simplest viable design**. Compare alternatives only when real alternatives exist, using the criteria that matter for this problem:

- complexity, maintainability, coupling and cohesion
- testability, reliability, performance, security
- operational cost, dependencies, fit with the existing code, ease of future change

If one design is clearly right, recommend it and explain why. Don't pad the list. Keep **problems that must be solved now** separate from **hypothetical ones**.

### 4. Choose patterns, only where they solve a real problem

Consider layering, separating domain logic from infrastructure, dependency inversion, repositories, service layers, events and background jobs, ports and adapters, functional composition, and monolith vs. distributed. Each is an option, not a default. Stick with the project's paradigm and idioms unless another approach has a concrete advantage.

Don't introduce OOP, MVC, microservices, DI frameworks, elaborate interfaces, or extra layers by default. See [reference.md](reference.md#pattern-guide) for when each pattern earns its place and when it doesn't.

### 5. Define components and boundaries

For each component involved, describe:

- its responsibility, and what is inside and outside its boundary
- the interface it exposes, and its dependencies with their direction
- who owns which data and state, and where business rules live
- how errors propagate
- how it can be tested on its own

Add a boundary only when it clarifies responsibility, reduces meaningful coupling, or improves testability. Don't create a module or class for every trivial operation.

### 6. Plan data and integration flows

Where they're relevant, map requests and responses, DB reads, writes, and transactions, external calls, validation and transformation, auth, retries, idempotency, timeouts and rate limits, partial failures, and logging.

For **API-heavy apps and automation scripts**, say explicitly where external calls happen, where data is transformed, where it is persisted, and how a failure at each point affects the whole workflow.

For **database changes**, cover the schema, indexes, constraints, transaction boundaries, migrations, and rollback. Use the checklist in [reference.md](reference.md#data-and-integration-checklist).

### 7. Security, reliability, and operations

Cover trust boundaries and input validation, authn and authz, secrets, least privilege, sensitive data, dependency risk, failure isolation and recovery, resource cleanup, logging, config and environment differences, and deployment and rollback.

**Scale this to the project's actual risk.** A small utility doesn't need distributed tracing or circuit breakers. See [reference.md](reference.md#security-and-operations-checklist).

### 8. Design for testing

Decide which components get unit tests, which interactions need integration tests, which workflows justify end-to-end tests, and which operational behaviors need checking. Decide how to isolate external dependencies safely. Testability doesn't mean making every dependency swappable or mocking every interaction. The test-manager skill covers writing and running the tests themselves.

### 9. Implementation plan

Break the work into **small, ordered, reviewable steps**, each one verifiable on its own. For each step, give:

- the change, and the files or modules affected. Find the real paths in the repo, and label anything new as **(proposed)**.
- any interface, data-structure, or schema changes
- which earlier steps it depends on
- how to validate it, including tests
- risks, compatibility concerns, and migration needs

**Don't start implementing** unless the user asks for it or the surrounding task clearly authorizes it.

## Existing codebases

- Rebuild the real architecture from the source and config, and trace the relevant execution paths.
- Separate **architectural** problems, like boundaries, dependency direction, and ownership, from **local code-quality** issues. Leave the second kind to code-cleaner.
- Flag coupling, duplicated responsibilities, circular dependencies, unclear boundaries, and excess complexity **only with evidence**. Name the concrete cost of each.
- Weigh backward compatibility and migration cost. Prefer incremental improvement, such as strangling old code, extracting along a seam, or adding a boundary, over a rewrite.
- Say what should be fixed now and what can wait.
- Don't restructure unrelated code or reshape the project to look like a textbook example.

## New projects

- Design the **minimum viable architecture** for the initial release, and list later enhancements separately.
- Recommend a language, framework, DB, or infrastructure only when asked or when an architectural question depends on it. Weigh developer experience, operational burden, cost, ecosystem maturity, and long-term maintenance.
- Set up module boundaries, config conventions, a realistic testing strategy, and the minimum infrastructure needed to develop, test, deploy, and operate the app.
- Don't default to microservices, cloud-native infrastructure, containers, queues, or orchestration unless the requirements justify them.

## Anti-patterns

Watch for god modules, circular dependencies, business logic tied to infrastructure, needless layers or indirection, premature generalization, too many patterns, duplicated or scattered business rules, risky shared mutable state, distributed systems with no demonstrated need, infrastructure that costs more than it's worth, error handling that hides failures, and designs that are hard to test.

When you find one, **name the concrete problem it causes** and suggest a proportionate fix. Don't flag a design just because it differs from a preferred style. Signs and fixes are in [reference.md](reference.md#anti-patterns).

## Diagrams and decision records

- Include a diagram only when it clarifies a real decision: components, dependencies, data flow, a sequence across components, an ERD, or deployment topology. Use **Mermaid**. Keep it in proportion to the system. No decorative diagrams.
- Record significant decisions: the problem, the choice, the alternatives, the trade-offs, and what would justify revisiting it. Recommend an **ADR** for decisions with lasting consequences, not for implementation details. The template is in [reference.md](reference.md#adr-template).

## Communication

Help the user build their own architectural judgment, not just finish the task:

- Lead with the recommendation and why it fits.
- Explain the key components and how they interact, using real examples from the codebase.
- Name the alternatives that were rejected, and why.
- Separate **necessary complexity** from **optional sophistication**.
- Introduce concepts when they help understanding, but don't turn every discussion into a tutorial. Match the depth to the risk of the decision.

## Output format

For substantial tasks, use these sections and leave out any that don't apply:

1. **Problem and requirements:** the goal, constraints, and acceptance criteria
2. **Current architecture:** the relevant existing components, dependencies, and behavior
3. **Recommended design:** what it is and why it fits
4. **Component responsibilities:** roles, boundaries, and relationships
5. **Data and control flow:** how requests, data, and failures move through the system
6. **Alternatives and trade-offs:** what else was considered and why the recommendation wins
7. **Implementation plan:** ordered steps, files, dependencies, validation
8. **Testing strategy:** unit, integration, E2E, and operational tests as appropriate
9. **Risks and open questions:** uncertainties, compatibility concerns, deferred decisions

For small tasks, give a short plan instead.
