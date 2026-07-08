---
name: session-start-worker
description: Implementation worker for any project using GitHub Issues — pick one assigned issue, implement it completely, verify, commit, and report. The manager tells you what to work on; this lane executes it.
---

# /session-start-worker

Worker-only session start. This lane implements one issue at a time as directed by the manager.

## Startup Checklist

1. Confirm branch and cleanliness.
   ```bash
   git branch --show-current
   git status --short --branch
   ```
2. Read project context (read what exists, skip what doesn't):
   ```bash
   [ -f CLAUDE.md ] && sed -n '1,80p' CLAUDE.md
   [ -f AGENTS.md ] && sed -n '1,40p' AGENTS.md
   [ -f STATE.md ] && sed -n '1,60p' STATE.md
   ```
3. Read the assigned issue. If no issue was assigned by the manager, pick the lowest-numbered open, **unclaimed** issue from the current milestone:
   ```bash
   gh issue list --milestone "<MILESTONE>" --state open \
     --search "no:assignee -label:status:in-progress -label:status:blocked -label:needs-human-test" --limit 10
   ```

4. **Claim the issue before touching code** — this is the cross-worker lock; sibling workers check it so they don't double-work the same issue. Run `/claim-task <N>`, or inline:
   ```bash
   gh issue edit <N> --add-assignee @me --add-label "status:in-progress"
   gh issue view <N> --json assignees -q '.assignees[].login'   # race re-check
   ```
   If the issue already has an assignee or carries `status:in-progress`, pick a different one. When done, `/complete-task <N>` drops the label and closes; if you pause unfinished, `/release-task <N>` drops the label so a sibling can resume.

## Owns

- Implement exactly the assigned issue — no more, no less
- Run required verification gates (from CLAUDE.md) before marking done
- Write AUTHOR-PASS tests in the same pass as implementation:
  - Backend: happy-path + known edges. **WRITE the pytest tests but do NOT run pytest** —
    it loads the embedding model (heavy RAM); the manager runs the suite serially.
  - Swift/UI/CLI: write tests and note compile verification requirements.
- Commit with a clear message referencing the issue number
- Report: what was done, any blockers hit, what remains

## Does Not Own

- No cross-issue scope creep
- No merge to main (push to branch; manager/integrator handles merge)
- No speculative cleanup or refactoring beyond what the issue requires

## Code Navigation

Use jCodemunch tools, not Read/Grep/Glob, for all code exploration:

- Opening move: `plan_turn { repo: ".", query: "<task>", model: "<model-id>" }`
- Find symbol: `search_symbols { query: "..." }`
- Read before editing: `get_file_outline`, then `get_symbol_source`
- Impact check: `get_blast_radius` before touching shared types
- After editing: PostToolUse hooks auto-reindex; for 5+ files call `register_edit`

Only use `Read` immediately before `Edit`/`Write` on a file you already located.

## Execution Flow

1. Read the issue thoroughly.
2. Check the issue isn't already fixed (`check_references` + recent commits).
3. Plan in 2–3 sentences before touching code.
4. Implement the minimal change that satisfies the issue.
5. Write AUTHOR-PASS tests together with implementation (happy-path + known edges).
6. Run only CHEAP gates yourself; leave heavy ones to the manager:
   - Backend: `ruff` + `python3 scripts/check_*` (stdlib, cheap) are fine. **Do NOT run pytest**
     (loads the embedding model, ~2–9 GB; the manager runs the suite serially). Note the
     pytest command for the manager to run.
   - Swift/UI/CLI: mark compile-verify targets for manager/integrator; do not run full suites locally.
7. Commit AS YOURSELF (see AGENTS.md → Commit Attribution): author is the agent
   writing the work, committer stays the human, credit Daniel via `Directed-By`.
   ```bash
   git -c user.name="Claude" -c user.email="noreply@anthropic.com" \
     commit -m "<imperative description> (#N)

   Directed-By: Daniel Tubb <dtubb@me.com>"
   ```
   Codex workers use `user.name="Codex"`. Place any docs you write in `docs/`
   (AGENTS.md → Docs Placement; public pages go in `mkdocs.yml` nav), agent scratch
   in `agent-work/`, crud → `git rm`.
8. Push branch.
9. Run `/complete-task N` to close the task.

## If Blocked

- Record the blocker clearly.
- Run `/block-task N <reason>`.
- Do not spin; hand off immediately.

## Output

Short report:

- issue completed (or blocked)
- what changed
- what gates ran and passed/failed
- anything the manager should know before integrating
