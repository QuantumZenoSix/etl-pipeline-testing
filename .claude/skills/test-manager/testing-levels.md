# Testing levels reference

Pick the cheapest level that proves the behavior. Each section says what to cover and the pitfalls to avoid at that level.

## 1. Sanity checks

Fast checks that catch obvious breakage:

- syntax and compile errors, and type-check errors (`tsc --noEmit`, `mypy`, `cargo check`, and so on, if the project already uses them)
- lint and static analysis that's already configured
- config and environment validation (required keys present, values parse correctly)
- input validation and required-field checks
- smoke tests: the main components initialize, entry points run, and the app builds and starts
- serialization round-trips where they matter

**Remember:** static checks aren't runtime tests. Passing lint or type checks doesn't mean the code behaves correctly. Don't install new tools for a basic check when the project already has equivalent tooling.

## 2. Unit tests

Test individual functions, methods, classes, and modules.

Cover:

- normal inputs, and the exact return values and output shapes
- boundaries and off-by-one cases
- empty, missing, null, and wrong-type inputs, where applicable
- errors and exceptions: their type, their message when it's part of the contract, and that no side effect happens on failure
- every important branch and decision path
- state transitions and side effects
- calculations, transformations, invariants, and business rules
- how the code behaves when a dependency returns an error, unexpected data, or an empty result

**Test doubles:** mock at real boundaries such as the network, clock, randomness, file system, and third-party services. Don't mock the code under test or plain value objects. If a test needs a lot of mocking, it may be a sign the code should be tested at a different level. Prefer testing real logic directly.

Test the **positive and negative** sides of a behavior: valid input produces the intended result, and invalid input is rejected *and* leaves nothing changed.

For dense branching or rules, consider **decision-table** tests, which are often table-driven or parameterized. For functions with clear invariants such as round-trips, idempotency, ordering, or conservation, consider **property-based** tests if the project has a library for them (Hypothesis, fast-check, proptest, and so on).

## 3. Integration tests

Test components working together:

- application code with a database: persistence, retrieval, constraints, transactions
- HTTP handlers or routers with middleware, validation, and serialization
- authentication and authorization layers
- internal service and module boundaries
- message queues, caches, file systems
- external API clients, at the contract boundary

Verify, where relevant, that:

- data round-trips correctly through persistence
- errors propagate or get translated correctly across boundaries, such as a DB error becoming a specific HTTP status
- transactions commit on success and roll back on failure, leaving no partial writes
- retries, timeouts, and rate limits behave as designed
- connections, files, and temp resources get cleaned up
- both sides agree on data formats and contracts

**Dependencies:** use real ones in an isolated environment (a test DB, testcontainers, an in-memory server, or a local emulator) when that gives meaningful confidence. Otherwise use realistic fakes, such as recorded responses or contract stubs. **Never report an external integration as verified when you tested it only against mocks.** List those as coverage gaps.

Isolate test data per test with transactions that roll back, unique IDs, or truncation in setup, so tests don't depend on each other or on the order they run in.

## 4. End-to-end tests

Test a few high-value journeys from an external entry point through the real system:

- the create, read, update, delete lifecycle of a key resource
- logging in and then doing a protected operation, plus the forbidden case
- submitting a form or request and checking the resulting state
- a multi-step workflow (an API call, then a DB write, then a visible result), including a failure partway through

Guidelines:

- Use the project's E2E tool (Playwright, Cypress, Selenium, a supertest-style API harness, and so on). With **no UI**, write API-level or CLI-level workflow tests instead of forcing a browser in.
- Keep the suite **small and stable**. Don't repeat unit-level cases here.
- Where practical, check both the **visible result** and the **persisted state**.
- Wait on conditions or use bounded polling. Never use fixed sleeps.
- Use stable selectors, such as `data-testid` or roles, rather than brittle CSS paths.

## 5. Operational tests

Use these only when the architecture and risk justify them. A small utility library usually doesn't need any.

| Concern | Example checks |
|---|---|
| Lifecycle | Clean startup; fails fast and clearly on missing or invalid config; graceful shutdown that drains in-flight work |
| Health | Liveness and readiness endpoints report correctly when a dependency is down |
| Resilience | Timeouts, retries with backoff, and recovery after transient failures or network interruptions |
| Degradation | A noncritical dependency fails and the core function keeps working |
| Resources | Connections and handles released; behavior under pool or memory exhaustion |
| Idempotency | Duplicate requests or jobs don't cause double effects |
| Jobs and workers | Scheduled or background jobs run, retry, and don't overlap when they shouldn't |
| Data integrity | Consistency after a partial failure or a restart |
| Concurrency | Concurrent writes and race conditions on shared resources |
| Observability | Errors are logged or reported with useful context and no secrets |
| Deploy and migrate | Migrations apply and roll back; compatible across supported environments |
| Performance | Latency, throughput, and resource use against a **measured baseline** or a stated requirement |

**Performance:** use realistic workloads and thresholds that come from baselines or requirements, never made-up numbers. Keep slow or load tests out of the default fast suite if the project separates them, using markers, tags, or a separate command.

**Authorization required:** clearly flag, and get explicit approval before running, any operational test that needs production infrastructure, real external services, significant resources, or potentially destructive actions.
