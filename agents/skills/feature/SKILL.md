---
name: feature
description: File a Fichero feature request as a GitHub issue, routed to the right milestone and labelled canonically. Captures the need, not the implementation.
---

# /feature

Capture a capability Daniel wants without derailing the current session. The sibling
skill is `/bug`, which files something that is broken; this one files something that
does not exist yet.

## Inputs

Ask Daniel for only what is missing:

1. What do you want to be able to do?
2. What do you do today instead? (the workaround, or "nothing")
3. Is this for the release you're testing now, or later?

If the answer to (1) is a *solution* ("add a dropdown to the inspector"), ask what
it is for. A feature request that names an implementation forecloses the design.
Write down the need; let the planner pick the mechanism.

## File it with the script, never raw `gh`

`scripts/file_issue.sh` is the ONE sanctioned way to create an issue. It validates
that the milestone exists and is OPEN, enforces the 15 canonical labels, and
keyword-routes the common themes. Hand-rolled `gh issue create` is how duplicate and
mis-placed milestones crept in before.

```bash
scripts/file_issue.sh \
  --title "<capability, in the user's words>" \
  --type feature \
  --lane backend|client:swiftui|docs \
  --milestone auto \
  --body-file /tmp/fichero-feature.md \
  --dry-run
```

Run it with `--dry-run` first and read what it resolved. If the router picks the
wrong milestone, pass `--milestone "<Exact Name>"` explicitly — do not hand-edit the
roadmap order to make the router agree with you.

- **`--milestone auto`** routes by keyword. Ambiguous titles get no milestone and
  the script tells you to choose. That is honest, not a failure.
- **Later, not now?** Pass a future milestone explicitly. Do not invent one — only
  the board organizer creates milestones.
- **`--needs-design`** if the shape is genuinely unsettled. It marks the issue as
  not-for-a-worker; free-model workers skip these.
- **`--priority P0..P3`** only when Daniel says so.

## Body

```markdown
## What Daniel wants

- <the capability, in his words>

## Why

- <what it unblocks; what he does today instead>

## Scope

- In: <the smallest version that is useful>
- Out: <what this issue is explicitly not>

## Notes

- Related: #<n>, <milestone>
- Design settled? <yes / no — needs-design>
```

## Check it does not already exist

Before filing, one search. The backlog is large and much of it is already built.

```bash
gh issue list --repo dtubb/fichero --state all --search "<key words>" --limit 10
```

If something close exists, comment on it rather than opening a duplicate. If it is
open and stale, say so. If it is closed but the capability is missing, reopen it and
explain what regressed.

## Then stop

Print the issue URL and stop. Do not start implementing. Do not open a worktree. A
feature request is work for the manager to schedule, not for this session to absorb.

If Daniel says "and just do it now," that is a different instruction — file the
issue first anyway, so the work has a number to close.
