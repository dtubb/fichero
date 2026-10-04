---
name: Spec task
about: A behaviour to build, from a spec (write or extend the spec first)
title: ""
labels: ["type:task"]
assignees: []
---

<!-- Milestone = the spec's name. One issue per reviewable slice. Blocked on the maintainer
     (a ruling, a token, credit, an account)? Label `needs-your-decision` and say exactly what is needed. -->

## Spec behaviours
<!-- `behaviour.id` lines this delivers, in docs/contributor_manual/specs/<area>/<spec>.md -->

## Why

## Scope (UX and server)
- Server:
- App:
- MCP / CLI / AppleScript (generated from OpenAPI):

## Out of scope

## Done when
- [ ] Tests named for the behaviours, written to the spec, fail first then pass
- [ ] Spec lines retagged (PARTIAL/OK) citing the tests; docs updated where the manual describes it
- [ ] Guards green (scripts, security, seams, contracts)
- [ ] Commit says `Fixes #<this>` (or `Part of`, with a `residue` follow-up issue)
- [ ] `needs-your-test` with what to try and which build, if it can only be checked on screen
