# Handoff for f_manager — choosing next work & filing issues (2026-07-03)

The board is consolidated and priority-ordered. Two things you do every loop:
**pick next work**, and **file new issues** (through the board organizer, not by hand).

---

## 1. Choose the next issue(s) to work on

The selector is deterministic — it walks the `## Tier` PRIORITY SPINE in
`docs/ROADMAP.md` (foundations-first) and returns the highest-priority ready,
unclaimed batch. Run it:

```bash
python3 scripts/choose_next.py            # human-readable
python3 scripts/choose_next.py --json     # machine-readable (for scripting)
```

It gives you: the tier, the milestone, the mode (one-big vs small-batch), a
recommended model, and the specific issue(s). Right now it returns
**Tier 1 → CLI keystone #2888**.

Then size each issue to a worker class:

```bash
python3 scripts/dispatch_advisor.py <issue#>     # -> mini | regular | frontier
```

Dispatch rules (unchanged):
- **Lane by label:** `backend` → codex · `client:swiftui` → claude · `docs` → codex-docs.
- External worktree only (`~/code/fichero-worktrees/`), **commit-only**, one build at a time.
- The selector already skips `status:in-progress`, `status:blocked`, `needs:human`,
  and anything assigned — so what it returns is genuinely ready.
- `needs-design` issues are NOT for free-model workers (design-blocked).
- On completion: gate with full relevant tests → cherry-pick to the milestone
  branch → mark the issue → re-run `choose_next.py` for the next batch.

**Do not hand-edit `docs/ROADMAP.md` order or milestone `due_on` to reprioritize** —
those two must stay in sync (the board organizer owns that). Ask the organizer to
re-sort instead.

---

## 2. File a new issue — call the script

Do NOT `gh issue create` by hand (that's how duplicate/mis-placed milestones crept
in). Use the wrapper — it validates the milestone is OPEN, rejects closed ones with
their successor, enforces the 15 canonical labels, and auto-routes common themes:

```bash
scripts/file_issue.sh --title "CLI: add --as-user flag" --type feature --lane backend \
  --milestone "Developer Experience" [--priority P1] [--needs-design] [--body "..."]
# or let it route by keywords:
scripts/file_issue.sh --title "harden token rotation on pairing" --type task --lane backend
#   -> auto-routed to milestone: Security
scripts/file_issue.sh ... --dry-run     # preview the gh command without creating
scripts/file_issue.sh --self-test        # sanity-check the router
```

Rules the script enforces for you:
- `--type` ∈ feature|bug|task, `--lane` ∈ backend|client:swiftui|docs (rejects anything else).
- Milestone must exist AND be open; a closed one (CLI, AI Infrastructure, per-corpus
  archives, …) errors with its live successor so you never re-create it.
- `--milestone auto` (the default) keyword-routes the high-traffic themes; if it can't
  route confidently it makes you pass an explicit `--milestone`.

**When the script can't route it, or you think a NEW milestone is needed** → ask the
board organizer (this Opus lane) over tmux — the organizer is the ONLY milestone
creation point and keeps the spine in sync:

```bash
tmux send-keys -t <board-organizer-session> \
  "FILE ISSUE: <title> | milestone: you pick | body: <why + acceptance>" Enter
tmux send-keys -t <board-organizer-session> Enter   # 2nd Enter submits
# new milestone: "NEW MILESTONE: <name> | scope: <one line> | where in spine: after <X>"
```

**Routing rule** (which milestone owns what) lives in
`agent-work/2026-07-03-milestone-consolidation-plan.md` §5. Quick hits:
- CLI work → Developer Experience #64 · security/auth/ACL/transport → Security #69
- AI-infra/model-use → AI Backend Hardening #90 · any corpus/demo dataset → Source Archives #65
- Closed milestones (CLI #63, Security-old, AI Infrastructure #83, Test Coverage #82,
  Networking #101, Docs Review #108, per-corpus #84–#89) are historical — **do NOT
  re-create them**; their themes route to the live successors above.

---

## Canonical label set (15) — use these, nothing else
lane: `backend` · `client:swiftui` · `docs`  |  type: `type:feature` · `type:bug` · `type:task`
gates: `status:in-progress` · `status:blocked` · `status:ready-for-test` · `needs:human` · `needs-design`
priority: `priority:P0`–`P3`

## Current spine (top of order)
Tier 1 Foundation (Dev&Build #109, Dev Experience #64, API Surface #70, Guardrails #92,
Repo Hygiene #103) → Tier 2 Security #69 + Connection #110 + Multi-user #111 + … →
Tier 3 app-structure → embedding → UX → Mac chrome → content → AI/agent → … →
Source Archives #65 → far future (tvOS #114, visionOS #95). Full list: `docs/ROADMAP.md` bottom.
