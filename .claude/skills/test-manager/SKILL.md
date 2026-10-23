---
name: test-manager
description: Runs, designs, writes, and maintains reliable automated tests (sanity checks, unit, integration, end-to-end, and operational or reliability tests) using the project's existing framework and conventions. Use when the user asks to run the tests or test suite, check whether tests pass, run lint, type checks, or a build check, or report test results; run a regression check or confirm nothing broke after a change; write, add, improve, or review tests; increase or assess coverage; add a regression test for a fixed or reported bug; do TDD or red-green-refactor; test a new feature, endpoint, module, or workflow; or set up testing where none exists. Not for investigating a failure the user brings, including a failing test or a bug (use debugger), or for general code-quality review.
---

# Test Manager

Run, write, and maintain tests that catch real defects and give real confidence. The number of tests doesn't matter. Each test should fail when the behavior it protects breaks.

**Pick the mode from the request:**
- **Run only** ("run the tests", "do they pass?", "check CI locally"): follow **Running existing tests** below and skip writing tests.
- **Write or improve tests**: follow the full **Workflow**.

## Principles

- **Inspect before writing.** Look at the project structure, dependencies, test framework, package scripts, CI config, and existing tests before you decide anything.
- **Follow existing conventions.** Use the project's framework, file layout, naming, fixtures, mocks, assertion style, and test commands.
- **Use the smallest effective setup.** Don't add a framework, dependency, or test infrastructure when the existing setup is enough.
- **Test behavior, not implementation.** Assert observable outcomes, contracts, and invariants. Don't couple tests to private internals.
- **No superficial tests.** "It runs," "it doesn't throw," and "the result is truthy" aren't enough when a meaningful assertion is possible.
- **Be deterministic.** Control clocks, randomness, network access, shared state, and ordering, unless the test is specifically about one of them.
- **Keep tests maintainable.** Use clear names, one behavior per test, and descriptive assertions. Add helpers only when they make the test clearer.
- **Verify honestly.** Never say a test passed unless you ran it and saw it pass.
- **Stay safe.** Without explicit authorization, never run tests that touch production, delete real data, send real messages or emails, charge payments, or cause other irreversible side effects. Use isolated environments and test credentials.

## Running existing tests

Use this when the user only wants tests run or results checked.

1. **Find the right command.** Look in package scripts, `Makefile`/`justfile`, `tox.ini`/`noxfile.py`, `pyproject.toml`, CI workflows, and the README. Prefer the project's own command, such as `npm test`, `make test`, or `pytest`, over calling the runner directly. If CI sets env vars, services, or flags, reproduce them when practical.
2. **Check that it's safe.** Confirm the tests use an isolated environment and test credentials. If a suite might touch production, real external services, real payments or messages, or destructive DB operations, stop and ask first. Integration, E2E, and operational suites often need services such as a DB, containers, or a browser. Check whether those are available rather than assuming they are.
3. **Choose the scope.** Run what the user asked for. If they didn't say, run the tests most relevant to the current changes first (one file, module, or marker), then the full suite if it's reasonably fast. For a long or expensive suite, say how long it may take and what it needs before running it.
4. **Run it and capture the output.** Run it non-interactively: no watch mode, and a CI flag if the runner needs one, such as `CI=true` or `--run`. Read the actual output. Don't infer results.
5. **Triage the failures.** For each failure, follow **Failing tests** below to work out whether it's a product defect, a test problem, an environment issue, or something that already failed before your change. If a test passes and fails on reruns with no code change, report it as flaky and include the evidence. Don't retry until it goes green.
6. **Don't change code unless asked.** In run-only mode, report the results and the likely causes. Fix tests or code only if the user asks, or if the fix is trivial and clearly within what they asked for.
7. **Report** using **Reporting** below, with the exact command and pass, fail, and skip counts.

## Workflow

Use this when writing or improving tests. Scale the depth to the task (see **Scope** below).

1. **Understand the behavior.** Work out what the code should do: its inputs, outputs, contracts, side effects, and which failures would matter.
2. **Inspect the test environment.** Find:
   - the framework and runner, from config files like `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `pom.xml`, `Makefile`, or the CI workflows
   - where tests live, how they're named, and the shared fixtures, factories, and mocks
   - the exact commands to run one test, one file, and the whole suite
   - which kinds of tests can actually run here: whether a test DB, containers, a browser, or network access is available
3. **Find the gaps.** Check what's already covered, what isn't, and which regressions would hurt most. Read the existing tests for the target code before adding to them.
4. **Plan the tests.** For each case, choose the lowest testing level that can prove the behavior, then list the case, its expected result, and the setup it needs. For non-trivial work, share the plan briefly before writing a lot of code.
5. **Write the tests.** Keep them focused and readable, in the project's style. Use [testing-levels.md](testing-levels.md) for what each level should cover and [edge-cases-and-quality.md](edge-cases-and-quality.md) for choosing cases and writing strong assertions.
6. **Run them.** Run the new tests first, then the relevant existing tests. Investigate every failure (see **Failing tests**).
7. **Check the tests' quality.** Ask whether each test would still pass if the feature were broken. Look for weak assertions, missing edge cases, redundant tests, and coupling to internals. For a critical test, consider breaking the code temporarily to confirm the test fails, then revert the change.
8. **Report.** Use the format under **Reporting**.

## Choosing test levels

| Level | Use it for | Notes |
|---|---|---|
| Sanity checks | Syntax, types, lint, config, build, startup, smoke | Cheap and fast, but passing them proves nothing about behavior |
| Unit | Logic, branches, calculations, transformations, business rules | The default for most behavior. Mock selectively, not everything |
| Integration | DB persistence, HTTP handlers, auth layers, queues, caches, external API boundaries | Use real dependencies in isolation where practical |
| End-to-end | A few high-value user journeys or workflows | Keep these few and stable. Use API-level tests if there's no UI |
| Operational | Startup and shutdown, health checks, retries and timeouts, recovery, idempotency, concurrency, performance | Only when the system's architecture and risk call for it |

Start with the cheapest tests that give meaningful confidence. Add higher-level tests only for things lower levels can't establish. Details for each level are in [testing-levels.md](testing-levels.md).

## Scope

- **Small bug fix:** add a regression test that reproduces the bug, then run a regression check (see **Regression tests**).
- **New function or module:** add unit tests for the main behavior and the important edge cases.
- **New API endpoint or DB code:** add unit tests plus integration tests at the boundary.
- **User-facing workflow:** consider one or two E2E tests.
- **Background service or production app:** consider operational tests.
- **Major or high-risk change:** consider the full testing pyramid and the realistic failure scenarios.

Don't create every type of test for every change.

**No test infrastructure yet:** propose the smallest reasonable setup, usually the language's standard or most common runner, and explain the trade-offs. Get agreement before adding dependencies or config. Don't build an elaborate framework.

## Test-driven development

Use TDD when the user asks for it or when it clearly fits:

1. Write a test that expresses the intended behavior.
2. Run it and **confirm it fails for the expected reason**. A test that fails because of a typo or import error doesn't count.
3. Make the smallest change that makes it pass.
4. Run it and confirm it passes.
5. Refactor if useful, keeping the tests green.
6. Run the relevant regression tests.

Don't say you followed TDD if you wrote the tests after the implementation. For an existing bug, write the regression test first and watch it fail before fixing the bug, when that's practical.

## Regression tests

A regression test isn't a separate testing level. It's a test at any level whose job is to stop a known bug or a working behavior from breaking again. There are two kinds of regression work.

### Writing a regression test for a bug

1. **Reproduce the bug exactly.** Use the specific input, state, or sequence that triggered it. Don't use a generic happy-path case that happens to pass through the same code.
2. **Pick the lowest level that reproduces it.** Use a unit test if the bug lives in one function. Use an integration or E2E test only if the bug comes from components interacting.
3. **Prove the test catches the bug.** It must **fail without the fix** and **pass with it**. If the fix is already in place, temporarily revert it (or use `git stash`) to confirm the test fails, then restore the fix. A test that passes either way protects nothing. If you can't confirm this, say so.
4. **Assert the correct behavior, not just the absence of the symptom.** For example, check that the total equals `42.50`, not just that no exception was thrown.
5. **Make it traceable.** Name the test after the behavior, such as `applies_discount_once_when_coupon_reused`. Reference the issue or ticket in the name or in a short comment if the project does that.
6. **Cover the bug's close relatives.** If the bug was an off-by-one at an upper bound, check the lower bound too. If it was a null in one field, check sibling fields that take the same path. Add only cases that could plausibly share the defect.
7. **Put it with the related tests.** Keep it in the same file or suite as the code's other tests, not in a separate regression-only file, unless the project already uses that convention.

### Running a regression check after a change

After any fix, feature, or refactor, confirm nothing that used to work is now broken:

1. **Run the tests closest to the change first:** the changed module's tests and the tests for its direct callers.
2. **Widen as far as the change's reach requires.** A change to shared code, a public interface, a schema, config, or a dependency upgrade calls for the full suite, or at least every suite that exercises that code.
3. **Compare against the baseline.** If something fails, check whether it also fails on the unchanged code, for example with `git stash`, before blaming the change. Report failures that already existed separately from new ones.
4. **For refactors, the existing tests are the regression suite.** They should pass **unchanged**. A refactor that requires editing assertions has changed behavior, so flag that. If coverage is thin, write characterization tests that capture the current behavior *before* refactoring.
5. **Report what the check did and didn't cover.** Say which suites ran and which areas of the change had no test coverage.

## Coverage and prioritization

- Put the effort into business logic, public contracts, high-risk paths, error handling, and code that has broken before.
- Use coverage tools when they're available, and treat the numbers as a way to find untested critical branches. High coverage doesn't prove the code is correct.
- Don't pad coverage with trivial or redundant tests.
- For critical logic, or tests that look weak, consider mutation testing if the project supports it.

## Failing tests

1. Read the failure output, the assertion diff, the stack trace, and the relevant logs.
2. Classify the failure: a **product defect**, a **wrong test assumption**, a **broken fixture or setup**, an **environment problem**, or a **failure that already existed**. Check this by running the test against the unchanged code, for example with `git stash`.
3. Investigate the cause. Don't just edit the assertion. If it's a real product bug, report it, and for anything non-trivial, use the **debugger** approach.
4. Make the smallest correction you can justify, then rerun the affected tests and the related tests.
5. **Never** delete, skip, or weaken a test, or change its expected value, just to get a green run. If a test has to be skipped because of an external limitation, write down the reason and the coverage gap it leaves.

## Reporting

Only describe tests as passing if you saw them pass in output you ran. Report a test as **passed**, **failed**, **skipped**, **not run**, or **could not run** (with the reason, such as no DB or no network). Don't hide failures that existed before your change, and don't blame them on your change without evidence. If you couldn't run the tests, give the exact commands and say clearly that the tests are **unverified**.

End with:

- **Tests added or modified:** the files, the behaviors covered, and the testing level of each. Leave this out in run-only mode.
- **Commands executed:** the actual commands.
- **Results:** counts for passed, failed, skipped, and not run, with details of any failures.
- **Coverage gaps:** important behavior that still isn't tested, including anything verified only against mocks and not real dependencies.
- **Recommended next steps:** only the follow-ups that would meaningfully increase confidence.

## Supporting references

- [testing-levels.md](testing-levels.md): what to cover at each level, from sanity checks through operational tests, and when each applies.
- [edge-cases-and-quality.md](edge-cases-and-quality.md): an edge-case checklist, assertion rules, determinism techniques, and anti-patterns.
