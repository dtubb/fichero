---
name: session-start-team
description: Use when starting a headless team session with multiple unblocked tasks — spawns parallel agents. Single-task sessions fall through to direct execution without team overhead.
---

# /session-start-team

Multi-agent orchestrator. Reads project context and unblocked tasks, then either executes directly (1 task) or spawns a parallel agent team (2+ tasks). The orchestrator delegates implementation to the best available engine, then reviews and governs outcomes.

**Core loop:** orchestrator plans → implementation engine executes → orchestrator reviews → Guardian checks → PR created.

**Preserves `session-start-auto`:** Single-task work still runs sequentially. Team mode is only activated when 2+ tasks are unblocked.

Use this global skill by default.

---

## Step 0 — BLOCK Gate (mandatory)

Before loading context or spawning agents, check for repository-level `BLOCK.md`.

```bash
if [ -f BLOCK.md ]; then
  head -n 40 BLOCK.md
fi
```

If `BLOCK.md` exists and the first non-empty line starts with `BLOCKED`, stop immediately.
Do not load further context, do not spawn agents, and do not modify files.
Exit with:
- `STATUS: BLOCKED`
- `BLOCKED ON: BLOCK.md gate`
- first blocking line from `BLOCK.md`

If `BLOCK.md` is missing, or does not start with `BLOCKED`, continue normally.

---

## Step 1 — Load Context

Read in order (skip missing files):
1. `CLAUDE.md` — hard rules; read `TASK_TRACKING:` value
2. `SOUL.md` — project identity
3. `MEMORY.md` — conventions and lessons
4. `STATE.md` — current branch, focus, blockers
5. Tasks per `TASK_TRACKING:`: `local` → `TASKS.md`, `github` → `gh issue list --state open`, `both` → both
6. `.claude/agent-briefing.md` — compact briefing if present

---

## Step 1b — Check Inbox

```bash
ls .ai/inbox/*.md 2>/dev/null || ls <agent-inbox>/*.md 2>/dev/null || echo "inbox empty"
```

If `.md` files exist:
1. Read each one
2. Move it to the matching inbox `processed/` folder
3. If it contains a task request: create a GitHub issue (or TASKS.md entry) immediately and include it in the task pool for Step 2.
4. Include processed inbox items in the final report.

If inbox is empty, skip silently.

---

## Step 2 — Assess Tasks

Collect all unblocked tasks:
- GitHub: skip issues labelled `blocked` or `needs-human-test`
- TASKS.md: skip items with blockers listed

**0 tasks** → Exit with `STATUS: NO_TASKS`

**1 task** → Execute directly using the `session-start-auto` Step 4–7 flow. No team overhead. Exit with structured report.

**2+ tasks** → Continue to Step 4.

## Step 2.5 — Loop Sync + Branch Hygiene

Before spawning agents:

```bash
git fetch --all --prune
git status -sb
```

If \`CLAUDE.md\` defines \`UPCOMING_BRANCH: <name>\`, orchestrator should run from that branch.
Require each spawned agent to:
- rebase/sync before coding
- checkpoint to its task branch
- merge back through PR flow

After branch merges, remove merged branches/worktrees to prevent drift.

---

## Step 3 — Write Implementation Specs

For each task, write a concise implementation spec before spawning agents:
- Source: GitHub issue body + CLAUDE.md context + SOUL.md constraints
- Include: what to build, which files are in scope, acceptance criteria
- Exclude: exact coding mechanics (the implementation engine handles this)

Spec quality determines output quality. Be specific.

---

## Step 4 — Spawn Agent Team

```
TeamCreate → team_name: "<project>-session-<date>"
```

For each task, spawn one general-purpose agent (`run_in_background=true`).

Classify each task before spawning:

**Implementation-eligible** (clear spec, boilerplate, lint fix, test stubs, refactors with defined scope):

Write an implementation spec first — precise enough that any supported engine can execute without ambiguity. Include: what to change, which files are in scope, acceptance criteria, and any hard constraints from CLAUDE.md. Then spawn the agent with this prompt structure:

```
You are working on task #<N>: <title>

Your branch: feature/issue-<N> (worktree already created)

IMPORTANT: Use the engine-agnostic implementation flow (`/implement-task`) for this task. Do NOT skip review.

Implementation spec:
<paste the spec you wrote>

Steps:
1. Invoke /implement-task with the spec above
2. Review every change (ACCEPT / REJECT / MODIFY)
3. Run /build-and-test — must pass
4. Commit: git commit -m "<description> (#<N>)"
5. Report back via SendMessage with STATUS, BRANCH, and what changed
```

**Research or architecture tasks** (no concrete implementation path yet):
- Agent uses direct reasoning (no external implementation engine required)
- Agent works the task, commits or produces a report, sends `SendMessage`

---

## Step 5 — Monitor

Receive `SendMessage` reports from agents as tasks complete. Track: which tasks done, which branches exist. Agents report using this format:

```
AGENT COMPLETE — [task #N] — [date]
STATUS: DONE | BLOCKED
BRANCH: <branch-name>
NOTES: [summary]
```

---

## Step 6 — Guardian Check

For each completed branch, spawn guardian agent:

```
Agent(subagent_type="guardian")
```

Prompt: "Review branch `<branch>` against project governance. Run `git diff main...<branch>`, read SOUL.md, CLAUDE.md, MEMORY.md. Return ALIGNED or MISALIGNED."

- **ALIGNED** → proceed to Step 8
- **MISALIGNED** → fix gaps directly in the branch, then re-run guardian

---

## Step 7 — Review, Create PR, Clean Up Worktree

For each aligned branch, switch into its worktree and run `/pr-workflow` — this handles parallel review and then creates the PR via `gh`. Do not call `gh pr create` directly.

```bash
cd ../$(basename $PWD)-issue-<N>
# run /pr-workflow from inside the worktree
```

After PR is created:
```bash
cd ../$(basename $PWD)
git worktree remove ../$(basename $PWD)-issue-<N> --force
```

Doc-only changes (`.md`, `.json`, config): commit directly to main if `AUTONOMOUS_COMMITS: true`, skip `/pr-workflow`, then remove worktree.

---

## Step 8 — Wrap Up

1. Shut down team: `SendMessage(type="shutdown_request")` to each agent
2. Update `MEMORY.md` with durable lessons from this session
3. Update `STATE.md` — list PRs created, tasks completed, what's next

---

## Step 9 — Exit Report

```
SESSION COMPLETE — [Project] — [date]

MODE: TEAM | DIRECT
TASKS COMPLETED: [N]
TASKS BLOCKED: [N]

COMPLETED:
- #<N> — <title> — PR: <URL>
- #<N> — <title> — PR: <URL>

BLOCKED:
- #<N> — <title> — <reason>

NEXT: <what the next session should pick up>
```

---

## Constraints

- Guardian always runs before PR creation — never skip it
- If guardian returns MISALIGNED, fix before proceeding
- Never merge to main — PRs only (unless doc-only + `AUTONOMOUS_COMMITS: true`)
- One worktree per task — never stack tasks in one branch
- Team lifetime is one session — shut down agents before exiting
- Never ask questions — if blocked, record it and stop
