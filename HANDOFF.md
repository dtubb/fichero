# HANDOFF — resume after 2026-08-01 (token budget resets Saturday)

Written 2026-07-30, ~23:00 ADT, at 99% of the week's budget. Daniel is camping
and will have tested the DMG/TestFlight build by the time you read this.

## Where things stand

- `origin/main` = `origin/integration` = **`b66ea518c`**. 200 commits landed
  tonight. Fast-forwarded, nothing rewritten.
- Branches: **`integration` and `main` only**, local and remote. 27 stale
  branches reviewed one by one and archived in
  `~/code/fichero-archive/stale-branches-2026-07-30.bundle` (verified complete).
  Two archive tags: `archive/inmemory-transport-streaming-seam`,
  `archive/research-tools-audit`.
- Worktrees: `integration` and Daniel's checkout. Nothing else.
- All subagents stopped.
- A release was running when the session ended: `scripts/release-all.sh --dev
  --github` — DMG + GitHub release + Mac TestFlight + iOS TestFlight.
  **Check `build/releases/` and the TestFlight tracks before assuming it
  finished.** `notarytool --wait` is unreliable here: submit without it, poll
  `info`, staple manually.

## Do this, in this order

### 1. Confirm the release actually landed

Do not take it on trust. `ls build/releases/`, check the GitHub release, check
both TestFlight tracks. If notarization stalled, poll and staple by hand.

### 2. BUGS FIRST — Daniel needs a build he can test on Tuesday

This supersedes the ratchet ordering below. Daniel's instruction on the night
of the 30th, as he left to go camping: two days of autonomous bug cleanup,
then a build cut Monday evening.

Go to section 3 and work backwards from the newest issue number. Come back to
the ratchets AFTER Tuesday's build is in his hands.

The ratchets matter and he asked for them repeatedly — but a ratchet he cannot
see is worth less this week than a sidebar that does not crash when he deletes
something.

### 2b. The ratchets milestone (#268) — after the build

Daniel asked for this explicitly and repeatedly. The rule: **it may not get
slower, bigger, or heavier, and it gets better over time.**

`#4439` is DONE — elapsed time, every test, automatic, held to its best-ever.
The mechanism lives in `fichero-server/tests/perf_ratchet.py`:
`note_test_duration` collects, `flush_session` compares once. Each new
dimension is a value alongside the timing, not a new system.

Order:

1. **`#4440` peak memory — DONE.** `flush_session_memory` holds the run's peak
   RSS to its best ever, in the same `perf_baseline.json`, under a `"mb"` key
   beside the `"ms"` ones.

   It is **session-level, and the name says so**: `mem::session::<paths pytest
   was run on>`. Peak RSS is process-wide and monotonic, so a per-test number
   would be the suite's memory wearing a test's name — it would look per-test,
   sort per-test, and be wrong per-test, which is worse than not having it. The
   scope is part of the name because one file and the whole suite have
   genuinely different peaks, and a shared bar means the narrow run tightens it
   below anything the full suite can meet. What IS per test is
   `peak_test_hint()` — where the high-water mark last ADVANCED, printed with
   that caveat attached, as a place to start looking.

   **Exit codes: 3 = regression, 4 = the ratchet went blind.** `peak_rss_mb()`
   returns `None` rather than a number it cannot stand behind — `getrusage`
   refused in a sandbox, or a value under a megabyte, which means the unit is
   wrong (`ru_maxrss` is BYTES on macOS and KILOBYTES on Linux, a 1024x error
   in either direction). "I could not measure" reported as success is how a
   guardrail stops existing without anyone noticing.

   Tests: `fichero-server/tests/unit/test_memory_ratchet.py`, including
   `test_many_small_growths_cannot_creep_past_it` (the memory equivalent of the
   anti-creep test) and a live, unstubbed plausibility check on the real
   measurement so a unit error on a new platform fails loudly. Every fixture
   synthesises its own violation — nothing is borrowed from the committed
   baseline, so none of it rots when those numbers change.
2. **`#4443` query count per endpoint.** Cheapest real win. A count is exact —
   no noise floor, no jitter allowance — and 3 → 47 queries is the answer, not
   a hint. An N+1 is a correctness bug wearing a performance costume.
3. **`#4444` binary/DMG size.** Trivial (`stat`), and it fails the RELEASE, not
   just the gate.
4. **`#4446` warning-count ratchet.** Daniel: *"if we run swiftlint, why do we
   not fix the warnings… otherwise we never get to them."* ~207 SwiftLint
   warnings, 0 errors. A ratchet turns a cleanup nobody schedules into
   something that happens without being scheduled.
5. **`#4441` launch time**, then **`#4442` the Swift-side ratchet** (shares the
   same `perf_baseline.json` — two files would drift).
6. **`#4445`** is the epic tying them together: automatic, nothing opts in.

**The property that must survive every one of these:** compare against the
BEST EVER, never against last week. Otherwise the window absorbs each
regression and the bar drifts up with the thing it was meant to catch. Fifty
accepted 5% slips are a 12x slowdown. There is a test for exactly that
(`test_many_small_slowdowns_cannot_creep_past_it`) — write its equivalent for
every new dimension.

### 3. Bugs — work BACKWARDS from the newest issue number

Daniel's most recent issues are the ones he hit while using the app, so they
are the live defects. Older ones are often aspirational, superseded, or
already fixed without being closed (34 were closed that way on 2026-07-30).

```bash
gh issue list --state open --limit 60 --json number,title \\
  --jq 'sort_by(.number) | reverse | .[] | "#\\(.number) \\(.title)"'
```

Exceptions that jump the queue at any number: anything that CRASHES or loses
data, and anything blocking the Tuesday build.

Filed on 2026-07-30, roughly by cost:

- **`#4434`** the engine suite leaks a multi-GB temp dir per run — 77 GB
  accumulated and took the machine to 100%. Hypothesis: the memory watchdog
  `SIGKILL`s pytest, which then never runs teardown. Wanted: unconditional
  cleanup, a startup sweep keyed on PID liveness (self-heals existing
  machines), and **a free-space preflight in `scripts/gate`** — that last one
  would have saved the evening, since the failure was invisible until total.
- **`#4447`** source-scanning guards name ONE file. Daniel spotted the real
  flaw: *"new files won't be tested."* A guard asserting "this file does X"
  when the invariant is "the app does X" breaks on a split AND misses a new
  offender. Two were fixed to scan directories tonight; dozens remain. The
  **absence form** ("nowhere under Views/ does the app do Y") is the valuable
  half and is nearly missing.
- **`#4382`** half the Python guardrails pass against an empty tree. Same
  family: a guard that scans nothing reports success.
- **`#4395`** `db.embed()` returns the same falsy value for "nothing to embed"
  and "the model failed to load", and `_create_pdf_page_children` defaults to
  `auto_embed=False`. This is why 676 of 745 documents were unembedded.
- **`#4420`** the seam program — categories 4, 7, 8 outstanding.
- **`#4437`** restore the headless UDS round-trip + transport profiling
  harness from the bundle. UDS is wired end to end and **nothing exercises a
  live round trip**, which is why transport bugs reach Daniel as sign-in
  failures instead of test failures.
- **`#4435`** re-apply the recovered audited/invertible research tools onto
  post-rename paths. The valuable part is `_invert_source_to_delete` — an
  inverse, so the mutation is undoable rather than merely logged.
- **`#4438`** split `ProviderAPIService`: it mixes a global catalog with
  library-scoped refs and nothing in its signatures says which needs a library.
- **`#4433`** Sparkle should announce updates in-app, never in a window over
  the user's work (Rogue Amoeba's change). Deferred deliberately.
- **`#4017`** the launch prompt screen is still there. Confirmed tonight.


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
- **A workflow runs in one library but not another.** Daniel's own second
  thought is the important part: *"or maybe that makes sense, workflows, but
  not for defaults."*

  So do NOT unify this blindly. A workflow a user BUILT belongs to the library
  they built it in — per-library is correct there, and flattening it would be a
  worse bug than the one being fixed. But a **default workflow is part of the
  app, not part of a library**, and must be available in every library on every
  host. If defaults are stored per-library, then which presets you get depends
  on which library you opened, and a fresh library silently has fewer
  capabilities than an old one.

  The review question is therefore **"where is the line between a default and a
  user workflow, and does the storage respect it?"** — not "why is this
  per-library". Check whether defaults are seeded per-library (wrong: they
  diverge, and a preset update reaches only libraries opened since) or resolved
  from the app (right).

  If it turns out to be a scope-plumbing problem after all, the question
  underneath is **"what carries library scope, and where is it reconstructed
  rather than passed?"** — a reconstructed scope is a guess, and a guess is
  wrong somewhere.

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

### 4. Two things I shipped past — check these first if Daniel reports oddness

- **`ui-hermetic` failed and I did not diagnose it.** Daniel said ship; I
  shipped. If the app misbehaves in a way that smells like UI wiring, that leg
  was already saying something.
- **`ToolbarGroupingTests` crashes with "index out of range"** after I fixed
  its paths. The app compiles clean so it did not block the build, but it is an
  unexplained runtime crash in test code.

### 5. The 48 known-broken specifications

`fichero-server/tests/known_specification_failures.txt` lists tests that
describe filed, unfixed defects (#4382 #4395 #4420), applied as
`xfail(strict=True)` per test id and printed LOUDLY in red on every run.
**Adding a line there is not a fix.** Strict means that when the defect is
fixed the test fails FOR PASSING — that is the reminder to delete the line.

## Lessons from tonight worth not relearning

- **Read the right exit code.** I reported "build succeeded" from a wrapper's
  status and "0 failures" from a grep matching the wrong output format —
  three times. Parse the gate's own `RC=` and its leg summary table, nothing
  else.
- **A clean merge is not a working tree.** Git merged `PDFPageView` with no
  conflict and produced code that did not compile: each lane's removal left the
  other's `@MainActor` orphaned. Only a build tells you.
- **Never edit `scripts/gate` while a gate is running.** Bash reads scripts
  incrementally by byte offset; my edit made a running instance resume
  mid-function in `cmd_self_test`.
- **Check for uncommitted work before killing anything.** A worker's `git
  commit` was interrupted by ENOSPC and its work existed only in the working
  tree.
- **`gate part <area>` exists now** (14 areas) and runs lint + build + tests +
  ratchet on one area in minutes. AGENTS.md makes it a hard rule: an issue is
  not done until it is green. Use it rather than the 90-minute gate.
- **Perf runs LAST** in verify-all now. It used to run third at ~51 minutes,
  so a Swift compile error was reported an hour late.
