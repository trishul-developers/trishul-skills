# Recheck: {{step}}, round {{round}}

This continues your own review thread. Your earlier verdict and findings are already in context, so don't re-read the whole diff and don't re-review unchanged code. Don't edit files.

## What changed
- Repository `{{repo_dir}}`, branch `{{branch}}`. Your last verdict was on `{{prev_head}}`; the new head is `{{head}}`.
- Read only `git diff {{prev_head}}..{{head}}`.
- The implementor says it fixed: {{fixes}}

## Check
1. Each BLOCKER you raised: fixed, not fixed, or fixed differently but acceptably.
2. Each SHOULD-FIX: addressed, or carried. Carried items need no action.
3. Any new defect the fix itself introduced, judged by the same blocker rules as before.

## Output (exactly this shape)
### Verdict: PASS | CHANGES_REQUIRED
- Reviewed head: `<sha>`
#### Earlier findings
1. `<finding>` — FIXED | NOT FIXED | ACCEPTED AS IS
#### New findings
1. **BLOCKER | SHOULD-FIX | NIT** `<file>:<line>` — scenario; required action. (Write "none" if there are none.)
