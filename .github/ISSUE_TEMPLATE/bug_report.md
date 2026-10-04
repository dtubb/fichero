---
name: Bug
about: Something behaves differently from its spec (or has no spec yet)
title: ""
labels: ["type:bug"]
assignees: []
---

<!-- Spec-led (AGENTS.md): spec > code > review > test to the spec > issues/milestones/docs > guards.
     Milestone = the spec's name (e.g. preview-surface). Search first: gh issue list --search "<terms>" --state all -->

## Spec behaviour
<!-- `behaviour.id` in docs/contributor_manual/specs/<area>/<spec>.md, tagged [BROKEN] citing this issue.
     No behaviour yet? Say so; writing it is the first step of the fix. -->

## Found
<!-- Who/where/which build (DMG version or commit). Screenshot paths are fine. -->

## Repro
1.

## Expected (what the spec says)

## Actual

## Done when
- [ ] A test named for the behaviour fails before the fix and passes after (through a route, action, MCP tool or the real store, not a hand-built stand-in)
- [ ] The spec line is retagged and cites the test
- [ ] UX and server both done (a server-only fix is not done)
- [ ] Commit says `Fixes #<this>`; on-screen check needed? label `needs-your-test` with what to try and which build
