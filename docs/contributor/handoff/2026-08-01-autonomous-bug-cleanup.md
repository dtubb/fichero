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


## Order: work BACKWARDS from the newest issues

Start at the highest issue number and work down. Daniel's most recent issues are
the ones he hit while actually using the app, so they are the live defects — the
ones standing between him and using it on Tuesday.

```bash
gh issue list --state open --limit 60 --json number,title,createdAt \
  --jq 'sort_by(.number) | reverse | .[] | "#\(.number) \(.title)"'
```

Older issues are not less real, but many are aspirational, superseded, or
already fixed without being closed — tonight's sweep closed 34 that way. Newest
first means every hour is spent on something that is definitely still broken.

Two exceptions that jump the queue regardless of number:

1. **Anything that crashes or loses data.** The sidebar delete crash outranks
   every cosmetic issue no matter how recently filed.
2. **Anything blocking Tuesday's build.**


### 3b. When a bug points at a system, review the system

Daniel, explicitly: *"bugs, and if bugs suggest system review do the system
review. like why are there different ingest roots? why can I run workflow in
one library but not the other."*

Most of these bugs are not one-off defects. They are a coherence problem
showing through at one spot, and patching the spot leaves the next four to be
found by hand. His two examples are the shape to look for:

- **Different ingest roots.** If ingest resolves its root more than one way,
  every importer disagrees about where things live and each disagreement
  surfaces as its own bug report. The review question is not "why did THIS
  import go to the wrong place" but **"how many ways can a root be resolved,
  and why is it more than one?"**
- **A workflow runs in one library but not another.** That is not a workflow
  bug. It means library scope is carried differently down two paths, so one
  of them loses it. The review question is **"what carries library scope, and
  where is it reconstructed rather than passed?"** — a reconstructed scope is
  a guess, and a guess is wrong somewhere.

How to tell the difference:

- **One-off** — the code meant to do X and had a typo. Fix it, add a test, move on.
- **System** — the code does X in two places that were never made to agree.
  Fixing one instance is how the class survives. Do the review.

When it is a system problem:

1. **Count the implementations.** Grep by capability-noun, not by symptom. Say
   how many exist and how they differ. Tonight's #4436 is the template: four
   selection implementations all writing the same `Set<String>` and disagreeing
   on every rule that produces it, with #4377 and #4409 as consequences rather
   than independent bugs.
2. **Say which one is right**, and why.
3. **Make the others impossible**, not merely fixed. `impossible > checked >
   documented`. A folder selection that cannot name two containers (#4414) is
   worth more than a check that it does not.
4. **File the finding even if you do not do the work.** A named, counted
   incoherence is worth more than a closed symptom.

Do not let a system review become the whole two days. Timebox the review, land
the fix for the reported bug, file the program, keep moving. The build on
Tuesday is the commitment.

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
