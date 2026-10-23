# Code Quality

Apply these as judgment calls, not absolutes. When they conflict, favor correctness, then clarity, then consistency with the codebase.

## Writing code

- Name things for what they represent or do; avoid vague names (`data`, `tmp`, `handle`, `mgr`) and unexplained abbreviations.
- Prefer early returns and guard clauses over deep nesting. Keep conditionals readable; extract a well-named variable or function when a condition needs explaining.
- Choose plain, explicit code over clever one-liners, dense chaining, or implicit behavior a reader must decode.
- Start with the most direct implementation. Add an abstraction, layer, config option, or dependency only when the current task actually needs it.
- Keep each function and module about one thing. Split when a unit mixes unrelated concerns or is hard to name; don't split into tiny pieces that force readers to jump around.
- Keep related logic together and make side effects (I/O, network, DB writes, global state) easy to spot.

## Duplication

- Extract shared logic when the duplicated code represents the same rule or behavior and would need to change together.
- Tolerate small or coincidental repetition; two or three similar lines are cheaper than the wrong abstraction.

## Fitting the codebase

- Before writing new code, look at nearby code and match its structure, naming, error-handling style, and formatting.
- Reuse existing helpers and patterns instead of introducing parallel ones.
- If a convention seems wrong, follow it for the task and mention the concern rather than changing it unilaterally.
- Touch only what the task requires. Note unrelated issues instead of fixing them in the same change.

## Defensive coding

- Validate and normalize input at trust boundaries (user input, API requests, files, env vars, external responses), then rely on it internally.
- Handle failures that can realistically happen; don't add checks for states the code already guarantees.
- Fail with errors that say what went wrong and with what context. Don't swallow exceptions or fall back silently.

## Comments

- Comment the why: intent, trade-offs, workarounds, constraints, and non-obvious behavior.
- Don't restate what the code says. If code needs a comment to be understood, consider clearer names or structure first.
- Update or remove comments that a change makes inaccurate.

## Before finishing

- Re-read the diff and remove dead code, debug output, unused imports, and leftover scaffolding.
- Look for anything more complex, duplicated, or indirect than it needs to be, and simplify it.
- Check for unintended behavior changes, especially in edge cases and error paths.
