---
name: session-start-bugtriage
description: Bug-triage lane for any project — take a bug report, reproduce or narrow it, identify the likely owning surface, and turn it into a clean issue or worker prompt. Does not implement the fix.
---

# /session-start-bugtriage

Bug-triage-only session start. This lane clarifies bugs before implementation begins.

## Startup Checklist

1. Read the reported bug carefully.
2. Check if the bug is already fixed: `check_references { name: "<symbol>" }` + recent commits.
3. Identify a reproduction path.
4. Locate ownership with jCodemunch — `search_symbols`, `find_references`, `get_blast_radius` — not Read/Grep.

## Owns

- Restate the bug in concrete terms
- Reproduce it when practical
- Narrow the likely root cause area
- Decide whether it is frontend, backend, both, or environment/tooling
- Write a crisp issue or worker prompt when the report is underspecified

## Does Not Own

- No broad feature work
- No final fix implementation unless explicitly reassigned
- No merge/push ownership

## Workflow

1. Restate the bug in concrete terms.
2. Check it isn't already fixed.
3. Identify a reproduction path.
4. Gather only the minimum code/context needed to locate ownership.
5. Report:
   - repro status
   - likely surface / owner
   - probable files
   - suggested next lane (worker model tier if applicable)

## Output

Leave behind one of:

- a clean bug report (ready to assign to a worker)
- a worker-ready prompt
- a blocked note explaining what info is missing

## Constraints

- Optimize for clarity and fast handoff
- Avoid drifting into implementation unless explicitly asked
