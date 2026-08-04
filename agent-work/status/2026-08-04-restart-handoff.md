# Restart handoff — 2026-08-04, Daniel's live testing session

`integration` @ `2c800bdde`, in sync with origin. Only two worktrees remain:
Daniel's checkout and `integration`. Both lane worktrees removed (verified 0
dirty, 0 unmerged first).

**Engine: NOT running.** Stopped and the socket cleared at Daniel's request.

When he wants to test again, Dev Local is `debugExternal` — it dials an external
engine and **never spawns one**. Start it with:

```
fichero-server/scripts/start_backend.sh --uds=/Users/danieltubb/Library/Containers/app.fichero.fichero/Data/tmp/fichero.sock --fast
```

Killing that engine while he is testing is what broke his session this morning.
Ask before stopping it.

---

## THE JOB — read this before dispatching anything

Daniel spent the morning testing and filed 13 bugs. Fix them **systematically**.

**Dispatch a FABEL agent**, and have that agent do the diagnosis, not just the
typing. Its brief:

1. **Do a thorough CODE REVIEW, not a patch.** Read the surrounding code before
   changing it.
2. **DOUBLE-CHECK THE COMMENTS AND THE ISSUES — the diagnosis may be wrong.**
   This is Daniel's explicit instruction and it is well earned: on 2026-08-03 a
   sweep found **nine issues whose stated mechanism the code contradicted**
   (#4408 fixed the day it was filed; #4386's supposed cause predated the report
   by twelve days; #4486's premise wrong in both halves; #3686 not an oversight
   but a deliberate removal that had CRASHED the app). A comment asserting
   something false has no test and will survive indefinitely — one was found
   claiming an endpoint no longer existed when it does.
   **If an issue's premise does not survive reading the code, say so and STOP
   rather than "fixing" a non-bug.**
3. **Check for hand-rolled URLs and OpenAPI compliance.** Every call goes through
   the generated OpenAPI client — no string-built endpoints, no bespoke
   URLSession. Per AGENTS.md and the knowledge-consistency mandate: one
   OpenAPI-backed reactive path. Finding one is a finding worth reporting.
4. **Review the BACKEND code too**, not only Swift. Several of these bugs
   (#4523 scope, #4450 resolution, #4402 stop) are engine-side or span both.
5. **Ponytail pass on its own diff**: the best code is the code not written.
   Prefer deleting a representation over synchronising two. No abstraction with
   a single caller.

Lanes could not be spawned this session: tmux had no free pane. A restart should
clear that. If it does not, free a pane or switch to in-process teammates in
`/config` — otherwise everything runs serially through the manager.

---

## BUGS, GROUPED BY ROOT CAUSE

Grouped deliberately: several share a mechanism, and fixing the class is cheaper
than fixing six instances.

### A. Environment / scene invariants — CRASHES

- **#4513 — CRASH: `ArtifactService` missing in a list/column view.**
  A fix is written but NOT yet committed (working tree, `ContentView+Navigation.swift`).
  `ArtifactService` is injected in **2** places and read in **9**. Any path to a
  reader not descending from those two traps — a missing `@Environment` object is
  a fatal error, not a nil. This is #4448's shape for the **third** time. It has
  earned a guardrail: every `@Environment(X.self)` reader must be reachable from
  an injection of X.
- **#4517 — two Global libraries open at once.** Likely the same class as the
  Activity fix below: an invariant true only because nobody opened a second.
- **#4518 — closing a library leaves Preview/Reader/Inspector showing
  "empty for this document" when there is no document.** Preview even offers
  **Retry** for a file belonging to nothing. Probably ONE missed teardown, not
  four empty-state bugs — a stale "Transcribe Paleography" chip persists too.

**Already fixed and pushed (`2c800bdde`), for reference:** the Activity window
crash (`ActivityDetailWindow` omitted `artifactService`) and five Activity
windows (`WindowGroup` → `Window`, singleton by construction; that also fixed
"menu opens the wrong window", since `openWindow(id:)` targets a group).
⚠️ **This was pushed before its build produced a verdict.** Verify it compiles.

### B. Workflow scope and resolution — COSTS MONEY

- **#4523 — URGENT: running a workflow on ONE selected file runs it on EVERY
  file in the folder.** Vision/LLM bills per page, so this multiplies spend
  silently, and writes artifacts to documents the user never chose, on real
  archival material. This is the **mirror of #4467**: that fix made the engine
  refuse an EMPTY resolution (lower bound); nothing pins the UPPER bound. Test
  that the resolved set **equals** the selection, not that it is non-empty.
- **#4450 (REOPENED) — a global default workflow 404s from a non-global
  library.** The sidebar offers it; the engine says "not found in this library".
  Daniel's rule: **global defaults visible AND runnable everywhere**, with the
  workflow menu showing global defaults and library-local workflows as distinct
  groups. Fix resolution to fall back to global scope. Do NOT "fix" it by hiding
  unrunnable menu items — that stops the lying without giving the behaviour.
  Read #4306 (`translate runs against the owning library`) first.

### C. Drag and drop — DELIVERY, not classification

- **#4520 — dragging a FOLDER or an image from Finder to the sidebar drops and
  pops back.** `Reentrant message: kDragIPCCompleted, current message:
  kDragIPCLeaveApplication`. The **same files import fine via the sidebar's
  bottom import menu**, so the importer is capable and the DROP path is not.
  Suspicion: the handler starts async work and returns before completing, so
  AppKit reads it as refused. A directory needs recursive enumeration; an image
  may arrive as data rather than a file URL.
  **This proves last night's #2386 fix was incomplete** — it converged five
  surfaces onto one extraction path but did not cover these payload shapes.
- **#4401 (REOPENED) — intra-library drag shows a `+` copy cursor, should be a
  MOVE, and then nothing happens.** Closed 2026-08-03 with four commits, one of
  which is literally titled *"the whole drop-path table, 8 paths, 4 gaps not
  fixed"*. Ask which of those four gaps this is, and whether the other three are
  also live.

### D. Sidebar / library consistency

- **#4514 — default workflow folders are purple + locked in the SIDEBAR but
  render as ordinary folders in LIBRARY VIEWS**, and accept drops. The sidebar
  row is the reference implementation — **reuse its predicate, do not write a
  second one**. Daniel noted the sidebar is correct "once they're loaded", which
  hints the styling depends on load order; that is a flicker bug in time.
- **#4516 — workflow nodes have no icon** in sidebar or library. One SF Symbol,
  used in both.
- **#4515 — sidebar lazy load is too lazy**: a visible folder should already know
  whether it has children. A disclosure triangle is a promise; guessing it means
  the UI is misinforming, not merely slow.
- **#4522 — importing ONE file redraws the whole sidebar TWICE.** The *twice* is
  diagnostic: likely a direct post-import reload AND a change-stream event both
  firing. **Count the triggers and report both before removing either.** Standing
  rule: stores update one item in place, never re-render a list.

### E. Toolbar information architecture

- **#4519 — the connection glyph and activity indicator sit inside the
  Library/Preview/Reader toggle cluster.** They are STATUS; those are CONTROLS.
  Move them into the path, or to its right in their own lozenge.
- **#4521 — search chrome is always present**; it should appear only when a
  toolbar search icon is clicked — **and that icon does not exist**. Add the icon
  first or search becomes unreachable.
- **#4391 — the connected glyph is a green tilde** that reads as "approximately",
  is the same green and size as the adjacent pane toggles, and does not
  distinguish local from remote. Screenshot on the issue. #4519 decides where it
  lives; this decides what it looks like.

### F. Controls that do nothing

- **#4402 (REOPENED) — Stop and Pause in the Activity window do nothing.**
  The previous fix (`9b2ef96c3`, "Stop honoured at every boundary") IS in his
  build. So establish **which half** is broken: the button never issues the
  request, or the engine ignores it. Do not assume the engine again.
  Note #4316 closed `paused`/`accepted` as dead-end states — if `paused` was
  unified away, a Pause button with no state to move to explains this exactly.

---

## THE PATTERN DANIEL SHOULD SEE

**Six issues were closed while still broken**: the three predecessors that let
#2386 survive, plus #4401, #4450 and #4402 — all reopened today with evidence
that their fixes are in his build and the behaviour is still wrong.

Last night's sweep found the mirror: **11 issues with a shipped fix still open**,
three since 13 July (`agent-work/status/2026-08-03-landed-but-open.md`).

Both directions have one cause: **issues are closed on a landed commit rather
than on observed behaviour.** The rule that fixes it is one line — an issue
closes when someone watched it work.

---

## ALSO OUTSTANDING

**Testing matrix** (Daniel wants general / mac / iphone / ipad, unit AND UI):
- `FicheroIOSTests` target EXISTS (he created it; committed `69e7953f9`).
- ⚠️ **Xcode registered it as a testable in all 14 schemes, including the 12
  macOS ones.** An iOS bundle cannot run on My Mac, so `FicheroTests.xcscheme`
  will fail. **Strip it from the Mac schemes.**
- 479 of 493 existing test files are platform-agnostic, and the targets already
  declare `iphoneos iphonesimulator macosx` — so "general tests on all three" is
  a PLAN/destination change, not a migration.
- Daniel wants the test folders consolidated under one `fichero/tests/` tree
  (`general/ mac/ ios/ ipad/ ui/ plans/`) instead of four root-level
  `fichero-*-tests` folders. Synchronized root groups take any path, so this is
  one `path =` string per group.
- Needs: `fichero-ios.xctestplan`; add `FicheroUITests` to `fichero-ipad.xctestplan`
  (currently unit-only, so iPad UI is unverified); three idiom canaries so a plan
  running on the wrong device fails loudly (#4472: the iPad plan sat green for a
  month having executed nothing).

**#4511 — no Swift test executes here.** `build-for-testing` compiles and never
runs, printing `TEST BUILD SUCCEEDED`. Every "Swift tests green" this week means
*compiles*. Root cause found: `LibraryManager`'s singleton `init()` always calls
`loadGlobalLibrary()` → … → `GET /api/documents/roots`, so touching it dials the
engine. A guard landed and is NOT sufficient — the host still hangs, also dialling
`/api/registry`, `/api/search/saved`, `/api/chains`, `/api/workflows/tools`.
**With an engine running, tests may now execute** — worth retrying first.

**#4512 — `check_xcode_registration.py` is BLIND** after the objectVersion 100
bump. It exits 2 rather than passing on an empty parse, which is correct, but the
Xcode-registration invariant is currently unenforced. **Do not describe the gate
as 82/82 until this parses.**

**Transport, now settled** (`eaff33759`): all four Mac Local schemes use UDS;
iOS/iPad stay HTTPS (a simulator cannot reach a socket in the Mac's container);
one container path, `app.fichero.fichero`. The engine's startup banner used to
tell Dev Local it could not reach the socket it dials — inverted end to end,
fixed, with `scripts/check_transport_banner_matches_schemes.py` to stop it
drifting again.

**Feature request:** if the app truly cannot connect at launch, Daniel wants a
modal that offers to send the log via TestFlight — while noting it should not be
reachable in the first place.

---

## PONYTAIL / STYLE — Daniel's explicit direction

- **Prefer the platform to our own code.** Reach for Swift and SwiftUI
  affordances, and Pydantic on the backend, before writing bespoke machinery.
  A stdlib or framework answer beats a hand-rolled one even when the hand-rolled
  one already exists — deleting ours in favour of theirs is a win, not churn.
- **NEVER disable SwiftLint. That defeats the purpose.**
  On 2026-08-04 an Xcode-side assistant "fixed warnings" in `ActivityStore.swift`
  by adding `// swiftlint:disable:previous line_length` — over a line that did
  not violate the rule. The result was a NEW warning
  (`superfluous_disable_command`) and the ratchet went 72 → 73. Reverted; back to
  72. Fix the code, or say the warning is wrong and why. A disable comment is a
  mute button, and this codebase has rejected mute buttons repeatedly.
- Daniel has stopped making changes in Xcode, so the working tree should be
  quiet apart from the lanes.

## STANDING RULES THAT KEEP EARNING THEIR KEEP

- **Make the detector prove it can see the bad case before trusting it seeing
  nothing.** Five separate instances this week of absence read as success — a
  missing `timeout` binary, an rc-127 guardrail loop, a reaped background suite,
  an orphan detector whose pattern never matched, and `build-for-testing` read
  as a passing suite.
- **Verify the result, not that the command ran.** Parse the summary line.
- **Fix the class, not the instance** — nearly every real defect this month was
  two things with nothing forcing them to agree.
- Lanes are COMMIT-ONLY; only the manager pushes and builds. One xcodebuild at a
  time. pytest from the repo root.
- No paid providers without explicit authorisation.
