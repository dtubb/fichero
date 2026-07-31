# KICKOFF — 2026-08-01, autonomous bug cleanup (2 days)

A cron job (`89f2c2d3`, fires Aug 1 09:07) should start this automatically.
Cron jobs are SESSION-ONLY — if the tmux session `f_inspector_manage` died,
they died with it. This file is the durable copy: paste it as a prompt.

---

/session-start-manager

AUTONOMOUS BUG-CLEANUP RUN — day 1 of 2. Daniel is camping until Tuesday and
wants a build to test on Tuesday. The weekly token budget has just reset.

## First

1. Read `HANDOFF.md` at the repo root — full state as of 2026-07-30 plus the
   mistakes worth not repeating.
2. Create the hourly management cron: `CronCreate`, cron `"37 * * * *"`,
   recurring true, prompt: *"Manager check-in: read worker inboxes, merge
   finished lane branches into integration, push, unblock anyone waiting, make
   sure every lane has work. Retire lanes whose work is merged. If a lane is
   idle, give it the next issue rather than letting it sit."* It auto-expires
   after 7 days.
3. Confirm the 2026-07-30 release landed: `build/releases/`, the GitHub
   release, and BOTH TestFlight tracks. A `--skip-dmg` rerun was in flight for
   the uploads after an error-90277 bundle-id fix. If notarization stalled,
   poll `notarytool info` and staple by hand — never `--wait`.

## Then: bugs, autonomously, for two days

Daniel's words on what is broken:

- running workflows **across libraries** doesn't work — he'd like to run a
  workflow on a host against local things
- **deleting things in the sidebar causes a crash** ← highest priority named
  here; a crash during a delete is one step from data loss
- can't import via the menu, the contextual menu, and the bottom `+` button
- **drag and drop of a PDF doesn't work from some locations**
- ingest problems

He has flagged many more as issues. Go find them; don't work only from this
list.

## Workers — three, each choosing its own issues

- one **Swift/frontend** lane
- one **opus** lane for anything needing real reasoning
- one **fabel** lane for reviews and second opinions

Give each a DISJOINT slice so claims don't contend. Every dispatch brief MUST
say: claim with `/claim-task <N>` before coding; skip anything already assigned
or labelled `status:in-progress`; commit-only (workers never push to main);
notify via `scripts/notify_manager.sh`.

**You are the manager.** Don't write product code beyond trivial unblocking.
Merge, gate, push, keep everyone fed.

## Discipline, learned the hard way on 2026-07-30

- Parse the gate's own `RC=` and its leg summary table. Do NOT grep for "FAIL"
  and trust the count — that misreported green three times in one evening.
- A clean merge is not a working tree. Only a build says that.
- Never edit `scripts/gate` while a gate is running (bash reads scripts by byte
  offset; an edit makes a running instance resume mid-function).
- Check for uncommitted work before killing any process or removing any
  worktree. A worker's commit was interrupted by ENOSPC and existed only in its
  working tree.
- Use `scripts/gate part <area>` (14 areas) while working — minutes, not the
  90-minute full gate. An issue is not done until it's green.

## By Tuesday

A tested build. Cut it Monday evening so there's room to fix what the gate
finds.
