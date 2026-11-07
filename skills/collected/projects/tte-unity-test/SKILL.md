---
name: tte-unity-test
description: Run Unity tests for this project by class, name or category in batch mode and return only counts plus the first failure. Use whenever you need to run EditMode or PlayMode tests, read a CI test artifact, or check one test. Executor role.
---

# Run Unity tests (executor)

Never read raw Unity logs into chat. Return counts, the first failure and at most about 50 lines.

## Rules
- **Project path:** pass `-ProjectPath` = your own worktree. Never use a path another Unity editor has open (one editor per project path). The CI runner uses its own checkout, so parallel runs on different paths are fine.
- **Never run the full suite locally.** CI runs it on every PR (about 13 min). Locally run only the classes or names you changed.
- **No `-quit`** (the test runner exits the editor itself). The script already handles this.
- **Categories:** `Heavy` (long cases) and `P17FocusedLongActivity` are excluded on PRs; `[Explicit]` tests run only when named in `-TestFilter`.
- **Flaky:** if a `SteadyState_*` allocation test fails once, re-run it alone before reporting (issue #39).

## Commands (PowerShell)
```
# classes or full test names, semicolon separated
powershell -NoProfile -ExecutionPolicy Bypass -File ci/unity-run-tests.ps1 -Platform EditMode -OutDir <scratch dir outside the repo> -NoGraphics -ProjectPath <worktree> -TestFilter "Ns.ClassA;Ns.ClassB.TestName"

# everything except long cases (what CI does; avoid locally)
... -Categories "!Heavy;!P17FocusedLongActivity" -NoGraphics

# PlayMode needs graphics: omit -NoGraphics
```
The script prints a counts table and the first failures, and exits 1 on any failure or on zero selected tests.

## Reading results
```
python -I ci/test-summary.py <OutDir>/editmode.xml --first 10 [--find SomeTestName] [--slowest 5]
```
From CI: `gh run download <run-id> -n unity-editmode-results -D <scratch>` (or `unity-playmode-results`), then the command above. `gh run list --workflow unity-ci.yml --branch <branch> --limit 3` finds the run.

## Report format
`<N total / P pass / F fail / S skipped>`, then each failing test with a one-line message, then "matches the red list: yes/no". Do not paste logs; name the artifact instead.
