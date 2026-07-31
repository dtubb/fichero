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

1. **`#4440` peak memory.** First, because it is the failure that stops work —
   the disk filled mid-gate tonight, XCUITests have hit 56 GB, builds shed
   under swap. Note: peak RSS is monotonic within a process, so naive per-test
   attribution gives every later test the high-water mark of every earlier one.
   Use deltas or accept session granularity and SAY so.
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
