---
description: Audit the features in this project — what works, what doesn't, what's tested. Produces a feature inventory. Works for any codebase.
name: feature-audit
---

# /feature-audit

Build a clear picture of what actually works in this project. No assumptions — verify each feature.

## Step 1 — Find the feature list

Read `CLAUDE.md` or `.claude/CLAUDE.md` — the architecture section lists what the project is supposed to do. Also check:
- `agents/RELEASE_PLAN.md` — features planned per milestone
- `docs/` — any feature documentation
- `README.md` — user-facing feature list

Build a list of all claimed features.

## Step 2 — Spawn audit team

For large codebases, use TeamCreate to audit in parallel by layer:
- **frontend-auditor** — UI, views, user interactions
- **backend-auditor** — API, data, business logic, tests
- **integration-auditor** — does frontend + backend actually connect correctly?

For small projects, audit directly.

## Step 3 — For each feature, determine

- **Status:** Working / Broken / Partial / Not Started / Unknown
- **Test coverage:** Tested / Untested / No tests exist
- **Last touched:** `git log --oneline -- [relevant files]`
- **Evidence:** what confirms it works (test output, manual verification, last green CI)

Do NOT fix anything during the audit. Observe only.

## Step 4 — Report

Write to `memory/feature-audit-[date].md`:

```
FEATURE AUDIT — [project] — [date]

| Feature | Status | Tests | Notes |
|---|---|---|---|
| [feature] | Working | Tested | [brief note] |
| [feature] | Broken | Untested | [what's broken] |
| [feature] | Partial | — | [what works, what doesn't] |

SUMMARY:
- Working: N / Total
- Has tests: N / Total
- Priority fixes: [top 3 broken features]

RECOMMENDED NEXT STEPS:
1. [most important thing to fix or test]
2.
3.
```

## Step 5 — Update TASKS.md

For each broken or untested feature worth fixing, add a task via `/assign-task`.

Update `MEMORY.md` with the audit summary — current feature health at a glance.
