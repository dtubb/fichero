---
description: Build, test, and lint the project. Reads commands from AGENTS.md — works for any stack. Run before completing any code task.
name: build-and-test
---

# /build-and-test

Run the full quality cycle for this project. Commands come from `AGENTS.md` — this skill adapts to any stack.

## Step 1 — Read the commands

Read `.Codex/AGENTS.md` or `AGENTS.md`. Find the "Build / Test / Lint" or "How I Ship" section. Extract:
- Build command(s)
- Test command(s)
- Lint command(s)
- Any pre-requisites (e.g. backend must be running, PYTHONPATH must be set)

## Step 2 — Run in order

Run each command. For each one:
- Print the command before running it
- Capture output
- Stop immediately if a command fails — do not continue to the next

## Step 3 — Report

```
BUILD AND TEST — [project] — [date]

Build:  [PASS / FAIL]
Tests:  [PASS / FAIL] ([N passed, N failed])
Lint:   [PASS / FAIL] ([N warnings/errors])

ISSUES:
[If any failed — exact error, file, line]

VERDICT: [Ready to commit / Fix before committing]
```

## Step 4 — On failure

Do not mark any task complete. Do not create a PR. Fix the failure first.

If the failure is in a generated file or outside the current task's scope — flag it, don't fix it, and note it in MEMORY.md.

## Step 5 — Update memory

If a new class of failure is discovered (a command that always needs a specific env var, a test that's flaky, a lint rule that fires on a pattern we use), add it to `MEMORY.md` Lessons Learned.
