# Codex QA Workflow

This repository uses a human-in-the-loop issue workflow for implementation and QA.

## Identity Without a Separate Bot User

When posting from the same GitHub account, Codex comments should start with:

`[CODEX]`

Daniel responses can start with:

`[DANIEL]`

This keeps authorship clear even when account identity is shared.

## Required Labels

- Area: `area:*`
- Type: `type:*`
- Owner: `owner:*`
- Status: `status:*`
- Needs: `needs:*`

## Status Flow

1. `status:in-progress` + `owner:codex`
2. `status:ready-for-test` + `needs:daniel-response`
3. Daniel posts QA result
4. If fixes needed: `status:in-progress` + `needs:codex-action`
5. On completion: `status:done`

## QA Request Requirements

Each QA request must include:
- exact steps
- expected result for each step
- environment preconditions (backend running, schema sync, etc.)
- pass/fail summary from Daniel

