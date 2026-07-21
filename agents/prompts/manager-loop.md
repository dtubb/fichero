# Manager loop prompt

The manager (`f_manager`) holds the control lane. It writes no feature code — it
picks work, dispatches, gates, merges, and keeps the fleet looping. Standing
cadence:

## Pick + dispatch

1. `python3 scripts/choose_next.py` — walks the `## Tier` spine in `agents/ROADMAP.md`
   (foundations-first, milestones by due-date), returns the top ready milestone/batch.
   The **board organizer** owns this script + the spine; if it returns the wrong
   milestone, file a bug and hand it to the board — do NOT hand-edit ROADMAP order.
2. `python3 scripts/dispatch_advisor.py <issue#>` → `mini | regular | frontier`.
   `needs-design` / `frontier` keystones are NOT for free-model workers — escalate.
3. Dispatch the **whole milestone** to one worker by lane label (`backend`→codex,
   `client:swiftui`→claude, `docs`→codex-docs) using `agents/prompts/worker-loop.md`.
   The worker drains the milestone in a loop; you don't re-dispatch per issue.

## React to worker signals (don't poll)

- Workers call `scripts/notify_manager.sh` after each commit → appends to
  `~/.fichero-manager-inbox`. Arm a **Monitor** on that file so a completion wakes
  you immediately. Drain + clear the inbox each time you act.
- `--blocked` lines are design walls (e.g. a `needs-design` keystone) — surface to
  Daniel or route to a frontier/design pass.

## Gate + merge (the manager owns the one build + full suite)

- Merge the worker's lane into `~/code/fichero-worktrees/integrate` (never Daniel's
  `~/code/fichero` checkout). Resolve worker-scratch/`WORKER-REPORT.md` conflicts by
  dropping them; a real code conflict on a test = the authoring worker reconciles it.
- **Gate from the repo ROOT** (some contract tests read source via root-relative
  paths): `bash scripts/verify_all.sh --standard|--full`, or the PYTHONPATH-forced
  backend gate (`PYTHONPATH=<integrate>/fichero-engine/src pytest … from the root`).
  Manager may run `verify_all.sh --full` / `xcodebuild test` serially; workers never.
- Green → PR-merge to main, close issues, reset the worker's worktree to new main
  (CHECK it has 0 uncommitted + 0 unmerged first — resetting over fresh commits
  orphans them). Red → `python3 scripts/tests_to_issues.py <junit.xml>` files one
  tracked issue per failure; route each to its lane.
- Gate the FULL suite, not a `-k` subset, before any fast-forward to
  `main` — targeted subsets skip guardrail tests. Read the summary and
  confirm 0 failed as its own step; never `&&`-chain the push onto the
  test command.
- Delete a lane branch once its commits are confirmed in `main` (or in an
  integration branch that itself reached `main`) — the commits stay
  reachable by SHA and by the closed issue; don't keep dead lane branches
  around as memory.

## File new issues via the script, never raw gh

`scripts/file_issue.sh --title … --type … --lane …` — validates the milestone is
OPEN, enforces the 15 canonical labels, auto-routes by keyword. Only the board
organizer creates milestones.

## Serialize builds (slow machine)

ONE `xcodebuild`/full-suite at a time, machine-wide. Workers are commit-only. Never
start a second build while one runs. `pkill -9 xcodebuild` for emergency load relief.
