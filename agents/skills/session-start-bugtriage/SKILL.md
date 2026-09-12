---
name: session-start-bugtriage
description: Bug-triage lane — take a bug report, reproduce or narrow it, identify the likely owning surface and owning spec, and turn it into a clean issue or worker prompt with a required regression test. Does not implement the fix.
---

# /session-start-bugtriage

Bug-triage-only session start. This lane clarifies bugs before implementation
begins; it does not fix them.

## Startup Checklist

1. Read the reported bug carefully.
2. Check if it's already fixed: `check_references { name: "<symbol>" }` +
   recent commits.
3. Identify a reproduction path.
4. Locate ownership with jCodemunch — `search_symbols`, `find_references`,
   `get_blast_radius` — not Read/Grep/Glob (see `AGENTS.md` → Code Navigation
   Policy).
5. Locate the owning spec: `docs/contributor_manual/specs/<area>.md`. If none
   exists for this surface, or the existing one doesn't describe the behavior
   the bug violates, that's part of the triage output, not a follow-up task.

## Owns

- Restate the bug in concrete terms
- Reproduce it when practical
- Narrow the likely root cause area
- Decide whether it is frontend, backend, both, or environment/tooling
- **Identify and, if needed, update the owning spec**
  (`docs/contributor_manual/specs/<area>.md`) so the fix has something to be
  correct against — a bug against an unspecced or wrong spec gets the spec
  fixed first, not just the code
- Write a crisp issue or worker prompt when the report is underspecified, and
  that issue/prompt **must require a regression test that pins the bug** — no
  fix lands without a test that would have failed before it and passes after

## Does Not Own

- No broad feature work
- No final fix implementation unless explicitly reassigned
- No merge/push ownership

## Workflow

1. Restate the bug in concrete terms.
2. Check it isn't already fixed.
3. Identify a reproduction path.
4. Gather only the minimum code/context needed to locate ownership.
5. Identify the owning spec; note whether it needs updating (and how) or is
   already correct and just wasn't followed.
6. Report:
   - repro status
   - likely surface / owner
   - probable files
   - owning spec (path, and whether it needs an update)
   - the regression-test requirement to hand the worker
   - suggested next lane (worker model tier if applicable)

## Output

Leave behind one of:

- a clean bug report (ready to assign to a worker), with the owning spec named
  and the required regression test stated
- a worker-ready prompt carrying the same two items
- a blocked note explaining what info is missing

## Constraints

- Optimize for clarity and fast handoff
- Avoid drifting into implementation unless explicitly asked
- Never hand off a fix prompt without a named regression-test requirement
