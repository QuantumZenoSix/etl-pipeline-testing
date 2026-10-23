---
description: Verify changes before declaring a task complete
alwaysApply: true
---

# Verify Before Declaring Done

- Never claim that a task is complete, working, or passing unless the relevant behavior has been verified.
- After modifying code, run the most relevant available tests, checks, or validation commands.
- If tests cannot be run, explicitly explain why and identify what remains unverified.
- Do not assume tests pass because the implementation looks correct or because an earlier version passed.
- When fixing a bug, verify the original failure condition is addressed whenever practical.
- When changing existing behavior, check for unintended regressions in related functionality.
- Never fabricate test results, command output, or verification steps.
- Before finishing, report:
  - What changed.
  - What verification was performed.
  - Whether verification passed, failed, or could not be performed.
  - Any remaining risks or limitations.
- If another agent performs verification, distinguish between tests you personally ran and results reported by that agent. Do not claim independent verification unless you performed it yourself.
