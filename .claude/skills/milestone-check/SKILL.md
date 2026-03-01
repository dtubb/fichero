---
description: Verify all acceptance criteria for the current milestone are met before marking it complete.
name: milestone-check
---

# /milestone-check

Check whether the current milestone is actually done. Reads acceptance criteria from `agents/RELEASE_PLAN.md` or `docs/agent-workflow/PLAN.md`.

## Step 1 — Find the milestone definition

Read in order:
1. `agents/RELEASE_PLAN.md` — look for the current milestone
2. `docs/agent-workflow/PLAN.md` — alternative location
3. `STATE.md` — what milestone is in focus

Extract the acceptance criteria ("Done when:") for the current milestone.

## Step 2 — Check each criterion

For each acceptance criterion:
- Can it be verified programmatically? → run `/build-and-test` or specific test
- Is it a behaviour? → describe how to verify it manually
- Is it a documentation requirement? → check the file exists and is complete
- Is it a code quality requirement? → run lint/tests

## Step 3 — Report

```
MILESTONE CHECK — [milestone name] — [date]

Criteria:
[ ] or [x] [criterion 1] — [how verified / what's missing]
[ ] or [x] [criterion 2]
...

Automated checks:
- Build: [PASS/FAIL]
- Tests: [PASS/FAIL]
- Lint:  [PASS/FAIL]

VERDICT: [Complete — ready to tag / N criteria not met / Blocked]

If not complete:
REMAINING:
- [what's missing and what to do]
```

## Step 4 — If complete

Suggest next steps:
- Tag the release: `git tag -a v[version] -m "[summary]"`
- Run `/changelog` to generate release notes
- Open next milestone in RELEASE_PLAN.md

Do NOT tag without Daniel's approval.

## Step 5 — Update STATE.md

Note the milestone check result in STATE.md In Progress / Blocked.
