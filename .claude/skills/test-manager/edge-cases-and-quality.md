# Edge cases and test quality reference

## Edge-case checklist

Go through this list before you finish a test suite. **Pick the cases that fit** the code's behavior, dependencies, and realistic ways it could fail. Don't test every category for every function.

| Category | Examples |
|---|---|
| Input shape | Empty, missing, null or undefined, malformed, wrong type, extra or unknown fields |
| Boundaries | Min, max, zero, negative, off-by-one, first and last element, exactly at a limit |
| Duplicates | Duplicate records, repeated requests, retried submissions, idempotency |
| State and order | Invalid state transitions, operations in the wrong order, acting on deleted or archived items |
| Data store | Missing record, conflicting record, unique or foreign-key violations, stale reads |
| Partial failure | A failure partway through a multi-step operation; rollback and compensation |
| Network | Errors, timeouts, retries, rate limiting (429), malformed or partial responses |
| Auth | Unauthenticated, insufficient permission, expired or revoked credentials, another user's resource |
| Concurrency | Simultaneous updates, lost updates, double-spend, overlapping jobs |
| Time | Time zones, day, month, and year boundaries, DST transitions, leap days, clock skew |
| Text | Unicode, emoji, combining characters, right-to-left text, special characters, very long or empty strings, encoding |
| Scale | Large datasets, pagination edges, payload size limits, memory and resource limits |
| Adversarial | Injection (SQL, shell, HTML), path traversal, oversized input, when security is relevant |
| Cleanup | Resources released and state restored after success *and* after failure |

**Techniques for choosing cases:**

- **Boundary-value analysis:** test just below, at, and just above each limit.
- **Equivalence partitioning:** one representative per class of input that behaves the same way.
- **Decision tables:** a table-driven or parameterized test for combinations of conditions.
- **Property-based testing:** for invariants such as round-trips, idempotency, or ordering, when the project has the library.

## Assertion rules

- Assert **specific expected values**, not just that a value exists. Prefer `expect(total).toBe(42.50)` to `expect(total).toBeDefined()`.
- Check **side effects and state changes**, and check that **nothing unintended** happened, such as no row written or no email queued when validation fails.
- When they're part of the contract, check **error types, status codes, response structure, and messages**.
- Avoid broad assertions that wrong behavior could still satisfy, such as `toBeTruthy()`, `len(x) > 0`, or matching only a substring of the output.
- Each assertion should have a reason to be there. Don't repeat checks that another test already covers.
- Use **readable test data** so that a failure explains itself, like `user_with_expired_trial` instead of `u2`.
- **Never** weaken an assertion or change an expected value just to make a failing test pass.

## Determinism

| Source of flakiness | Fix |
|---|---|
| Current time | Inject a clock or freeze time (fake timers, `freezegun`, a clock interface) |
| Randomness | Seed it, or inject the generator |
| Network or external services | Stub at the boundary, or use a local or containerized dependency |
| Shared mutable state | Fresh fixtures per test; reset globals and singletons in teardown |
| Execution order | No test depends on another test; run in random order if the runner supports it |
| Async timing | Await completion or poll a condition with a bounded timeout. **No fixed sleeps** |
| Machine-specific settings | No absolute paths, locale or time-zone assumptions, or reliance on ambient env vars |
| File system | Use temp directories and clean them up |

## Naming and structure

- Name the test after the behavior and expected outcome, such as `rejects_order_when_inventory_is_insufficient` or `returns 404 for another user's invoice`.
- Use arrange, act, assert, with one behavior per test. Several assertions are fine when they describe one outcome.
- Use fixtures, factories, and helpers when they make the test clearer. Inline setup when a helper would hide what's being tested.
- Clean up temp files, DB rows, env changes, and patched globals.

## Anti-patterns

- **Tests that can't fail:** no assertions, assertions that are always true, or catching and ignoring the exception the test should check.
- **Mirror tests:** tests that re-implement the production logic to compute the expected value.
- **Mocking everything:** a test that only checks mocks called mocks shows nothing about real behavior.
- **Testing internals:** asserting on private methods, call counts of internal helpers, or exact internal data structures when the public result is what matters.
- **Snapshot dumping:** large snapshots accepted without review. Use them only for stable, meaningful output.
- **Coverage padding:** tests written to hit lines rather than check behavior.
- **Sleep-based synchronization:** `sleep(2)` and hoping.
- **Silenced failures:** `skip`, `xfail`, `.only`, or commented-out tests left behind to get a green run.

## Final self-check

Before reporting, ask of each important test:

1. Would this test **fail** if the behavior it covers were broken?
2. Does it fail with a **clear message** that points to the problem?
3. Is it **deterministic** across machines, time zones, and run orders?
4. Does it test **behavior** that a user or caller would care about?
5. Is there a **cheaper level** that would give the same confidence?
