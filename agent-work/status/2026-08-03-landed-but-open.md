# Open issues whose fix may already have landed

**Coverage, stated rather than implied:** I examined **31 open issues** across
seven milestones — Library View (Icons, List, Column Browser, Canvas, general),
Inspector, Keyboard Navigation, Drag & Drop. Of those, 14 had a commit
mentioning them on `origin/main`; I read the **full** log for each, not just
its newest entry. **19 have no fix commit and are left alone.**

Counts: A = 8 verify-then-close, B = 1 contradicted, C = 4 unclear, D = 19
untouched.

**A second sweep (section F) covers 41 more issues** across Engine, Sharing,
Workflow and Settings, and explicitly names the 65 it skipped.

Total examined: **73 open issues. 17 have a fix that is in a shipped build and
are still open** — 6 in section A, 11 in F1 — of which #3364 is a decision
rather than a verification. A further 5 (#4377, #4458, #4459, and the
#970/#1834/#2104 trio on one commit) are fixed but **not in any release**, so
testing them against v2026.08.02 would produce false failures.

The first sweep (sections A-E) covers UI milestones only; section F covers
Engine, Sharing, Workflow and Settings.

**Nothing here is closed. I am not authorised to close anything, and none of
this is a closure recommendation — it is a list of things to CLICK.**

## Why this list exists

Two findings tonight point the same way: #4408's fix landed on the day it was
filed and shipped in v2026.08.02, and #4386's supposed cause
(`contentShape`) already existed at sixteen sites twelve days before the
report.

But a landed commit proves **code changed**, not that the **feature works**.
#3390, #702 and #570 were each closed on a real, correct commit while PDF
drag-drop stayed broken from other sources — which is how #2386 survived three
fixes and had to be reopened. So: verify, then close. Never the reverse.

---

## A. Verify-then-close — fastest first

| # | Issue | Commit | In v2026.08.02 | What to click | Time |
|---|---|---|---|---|---|
| **4408** | two-finger scroll doesn't pan the canvas | `e4bfe9ede` (2D), `47f7b28c9` (iPad + 3D) | 2D **yes**; iPad/3D **no** | Open the canvas, two-finger scroll. Should pan. Space-drag should still work too. | 10s |
| **4398** | list rows: badges/errors/columns | `c83036b5c` | yes | Inspector Attributes strip: should default to nothing and not show storage internals | 20s |
| **4412** | one input grammar for every library view | `48f89b954` | yes | Switch to canvas/spatial mode, then back to list — arrow keys must still move the selection | 30s |
| **3364** | double-click should focus current window | `7d2d2fc4c` (2026-07-25, **after** the issue) | yes | **Do not click-test — see section E.** The commit does the opposite of what the issue asks, deliberately and with tests. It needs a decision, not a verification | — |
| **4377** | library multi-select conventions | `38c834c90` | **NO** — committed 2026-08-03, after the tag | shift-click range, ⌘-click toggle, arrow+shift extend. **Not in Daniel's build** — check on a fresh build only | 1m |
| **4376** | ⌘A in the focused surface | `ff8d592ae` | yes | Click a library row, ⌘A → all rows select. Click into a text field, ⌘A → selects the text, **not** the rows | 15s |
| **4459** | sidebar drop vanishes on load failure | `18fdfaa62` | **NO** — 2026-08-01, after the tag | Drop a file the loader cannot read onto a sidebar folder. It must report, not vanish | 30s |
| **4388** | 32pt serif headline in inspector entity detail | `23ef2431c` | yes | Open an entity in the inspector. The name should be a normal bold system headline, not a large serif | 10s |

## B. CONTRADICTED — the commit mentions the issue but does not fix it

**This section was wrong and is corrected here.** It had five entries. Four
were errors of my own, of exactly the class this document exists to warn
about — see *The method* below.

| # | Issue | Mentioning commit | What it actually does |
|---|---|---|---|
| **4458** | scope content-pane drop to detailColumn | `fbc1bbd1c`, `fbdaa1765` | `fbc1bbd1c` is titled **#4401** and touches only `Sidebar/`; `fbdaa1765` is a pbxproj build fix. Neither scopes the drop. The real fix is `6a11a9fc2` — now **merged to `integration`**, but not on `main` and **not in v2026.08.02** |

## C. UNCLEAR — do not act on these without reading them properly

| # | Issue | Why unclear |
|---|---|---|
| **4160** | EPIC: library view quality pass | `e40eb0c9e` is one STEP of a multi-step epic; the epic is not the step |
| **4005** | wire-in or delete legacy canvas fallbacks | `9ab922b62` moves `SpaceSceneView` between directories — filing, not wiring-or-deleting |
| **3700** | entities/annotations as columns | `b692ef127` is a merge commit; the work behind it was not read |
| **3703** | entities draggable | `eb9297dba` is a merge commit; same |

## D. STILL OPEN — no fix commit found (19)

1692, 1950, 1962, 2272, 2418, 2422, **3686**, 3687, 3688, 3689, 3697, 3698,
3699, **3707**, 3685, 3706, 4204, 4236, 4311.

Several are EPICs (1962, 3685) where "no commit" is expected.

**#3686** (focus management / tab order) and **#3707** (drop semantics via the
audited action layer) moved here from section B. Their only appearances on
`main` are a docs commit whose subject names #3690, and a coverage-baseline
chore. Neither issue has a fix commit of any kind, so there is nothing to
re-diagnose and nothing to click — they are simply open.

---

## E. #3364 — a decision for Daniel, not a fix

**Nothing changed. This needs your word before anyone touches it**, because it
alters a shipped interaction default.

**What #3364 asks (filed 2026-07-10):** double-click focuses/navigates the
selected item *in the current window*. Open-in-new-window/tab stays available
from the context menu and explicit commands only.

**What the code does (`7d2d2fc4c`, 2026-07-25, fifteen days later):** exactly
the opposite. `SidebarView+ViewComponents.swift:71` binds
`.onTapGesture(count: 2)` → `handleSidebarDoubleClick()` →
`WindowOpener.open(asTab:)`, honouring the system "Prefer tabs" setting. It has
tests (`SidebarOpenAffordanceTests`) and it ships in v2026.08.02.

**The part worth seeing.** The commit's own comment reads *"mirroring the
library table's container-level double-click contract (#3364)"* — it cites
#3364 as the precedent for the behaviour #3364 was filed to remove. The other
citation is #2496, and #2496 did **not** ask for this: it asked for easier
click-to-select plus a **trailing affordance**. A trailing affordance is
precisely the "explicit command" #3364 says should carry open-in-new-window.

So this is not two issues wanting opposite things. It is one change that
over-delivered: auxiliary-open was bound to the trailing affordance (asked
for) **and** to double-click (ruled out).

**Also relevant:** single-click already keeps select-in-place, and sidebar
selection drives the detail column. So the navigate-in-current-window half of
#3364 arguably already works — double-click is the only part in dispute.

**If you want #3364 honoured**, the change is one binding: drop the
`.onTapGesture(count: 2)` at `SidebarView+ViewComponents.swift:71`. The
trailing affordance, the row context menu and the File-menu commands all keep
working — they call `openPrimarySelection` directly, not through the gesture.
`SidebarOpenAffordanceTests` tests the *routing* function, not the gesture, so
it stays green either way.

**If you want to keep double-click-opens**, #3364 should be closed as
superseded rather than left open, since it currently reads as an unfixed bug
against deliberate, tested behaviour.

---

## F. Second sweep — Engine, Sharing, Workflow, Settings

**Coverage, stated rather than implied:** I examined **41 open issues** across
six milestones: Workflow View (252), Engine — Connection & Startup
Bulletproofing (110), Sharing & Pairing (263), Settings (126), Settings —
Models & Providers — HPC (240), Settings IA v2 (257).

**I skipped 65 open issues** in thirteen further Engine milestones — Bugs-Tests
(82, 235), Performance (239), Onboarding (132), Device Pairing (96), Accounts
(133), Multi-Library (218), Remote/Self-Hosting (74), Embed iOS (216), Embed
Mac (217), AI (90), Library-Engine (165), Inspector-Artifacts (247). A short
honest table beat a long speculative one twice, so I stopped at what I could
check properly. The Agent View milestones (191, 228, 139) were triaged in an
earlier pass and are not re-covered here.

**Nothing is closed and nothing is verified.** What follows establishes only
that a commit *claiming* each fix exists and which build carries it.

### F1. Fix shipped, issue still open (11)

| # | Milestone | Fix commit | Shipped in |
|---|---|---|---|
| **3362** | Connection | `c9121a262` sync sandbox bootstrap token on startup | v2026.07.13.4-beta |
| **3366** | Settings | `e79ca8ccd` route app menu settings into the settings window | v2026.07.13.4-beta |
| **3403** | Connection | `df634cbdf` delay live-updates paused state until repeated failures | v2026.07.13.4-beta |
| **4037** | Connection | `7dcb410db` loopback-owner for the in-memory ASGI transport | v2026.07.21-beta |
| **3791** | Sharing | `f8358d842` accept `https://fichero.app/pair` universal links + AASA | v2026.07.23 |
| **3928** | Connection | `ff7481c1c` move port preflight waits off main | v2026.07.26 |
| **4186** | Workflow | `3cf4dd0b5` drop the duplicate virtual workflow tree | v2026.07.29 |
| **4306** | Workflow | `489b077a0` translate runs against the owning library | v2026.08.02 |
| **4309** | Workflow | `d87b373ae` capture typed OCR geometry on every vision pass | v2026.08.02 |
| **4329** | Workflow | `82d8b88fb` OCR overlay + in-place HTML/SVG/Markdown renditions | v2026.08.02 |
| **4478** | Workflow | `76595815b` `file→files` joins `PORT_CONVERSIONS` | v2026.08.02 |

**Three have been shipped since 13 July.** #3362, #3366 and #3403 have been
fixed and in a build for three weeks while staying open.

**These are mostly not click-tests.** Unlike section A, the Engine entries are
verified with the CLI or a targeted pytest, not by clicking — #3362 and #4037
are auth/transport, #3928 is launch timing. Only #3366 (Settings menu routing)
and #4186 (duplicate workflow tree in the sidebar) are visible in the UI.

### F2. Fixed on `main`, NOT in any release (3)

**#970, #1834, #2104** — all three closed by one commit, `65ae3b675`
*"every word's rect was computed by Vision and thrown away"*. It is on `main`
and in **no tag**. Same trap as #4377/#4458/#4459: testing these against
v2026.08.02 gives a false failure.

#970 also carries `f7611693d` *"mark #970 blocked"* — an **older** commit. The
blocker was lifted by the later fix and the label was never updated.

### F3. Unclear — do not act without reading (3)

| # | Why unclear |
|---|---|
| **3968** | Its commits enable embedded-launch UI tests, and `9f410a53f` says in its own subject `[COMPILES; embedded run UNVERIFIED]`. Whether the tests actually run is the issue, and the commit declines to claim it |
| **3949** | Only a `test:` commit and a merge. No implementation commit found |
| **3678** | Settings IA v2 — only `docs:` commits. For a design issue the docs may BE the deliverable, which is a judgement about intent, not code |

### F4. No fix commit (24)

31, 1659, 3778, 3929, 3931, 3979, 3982, 3989, 3993, 4328, 4330, 4339, 4342,
4344, 4368, 4370 have no referencing commit at all.

3947, 3980, 4277, 4310, 4312, 4340, 4343, 4369 have only **incidental**
mentions — a commit whose subject names a *different* issue. Per the section-B
correction, that is no evidence, so they sit here rather than in a
"contradicted" section.

### A refinement to check 2

`git tag --contains <sha> | head -1` is wrong. This repo carries `archive/*`
tags, and for five of the eleven entries above the first line was an archive
tag, which reports nothing about what shipped. Filter to release tags and take
the earliest:

```
git tag --contains <sha> | grep -E '^v20' | sort -V | head -1
```

Unfiltered, #3366 reads `archive/inmemory-transport-streaming-seam`; filtered,
it reads v2026.07.13.4-beta — three weeks in Daniel's hands.

---

## G. #4388 is fixed, and the font sweep it invites would break things

**#4388 is landed and shipped.** `23ef2431c` (2026-08-01, in v2026.08.02)
changed exactly the line the issue names:

```
-    .font(.system(size: 32, weight: .bold, design: .serif))
+    .font(.title)
+    .fontWeight(.bold)
```

No serif and no hardcoded point size remains anywhere in
`EntityDigestView.swift`, and no `design: .serif` remains anywhere in the whole
`Views/Inspector/` tree. It moves to section A as a ten-second look.

### The part worth keeping

Reading outward from it, `.font(.system(size:))` appears seven more times in
the neighbouring ontology tree. **None of them is a font at all.**

| File | Line | What it sizes |
|---|---|---|
| `OntologyBrowser+Detail.swift` | 49 | `Image(systemName: "person.crop.rectangle.stack")` |
| `OntologyBrowser+List.swift` | 142 | `Image(systemName: "person.2" / "line.3.horizontal.decrease.circle")` |
| `Entity/EntityDetailView.swift` | 278 | `Image(systemName: iconForEntityType)` |
| `Entity/EntitySourceGroupsView.swift` | 55 | `Image(systemName: "doc.text")` |
| `ForceDirectedGraphView.swift` | 78 | `Image(systemName: "circle.grid.3x3")` |
| `Claim/ClaimSummaryCard+Details.swift` | 68 | `Image(systemName: "chevron.right")` |

Six are SF Symbols in empty-state placeholders and disclosure chevrons, where
`.font(.system(size:))` is the standard idiom for sizing a symbol. The seventh,
`ClaimSummaryCardView.swift:102-110`, derives from
`@AppStorage("editor.fontSize")` — a **user preference**. Replacing it with a
semantic style would delete a setting the user can change.

So a grep-driven "replace hardcoded sizes with semantic fonts" pass over this
area would have resized six icons and broken one preference, while fixing
nothing: the single genuine text violation was already gone two days earlier.
That is why the blanket-sweep rule exists, stated as a measurement rather than
a principle.

**Zero text-font drift found outside the already-fixed line.** Nothing to do.

---

---

## H. #4311 — one half is already built; the other is blocked in a signature

#4311 asks for two drag directions. They are in completely different states,
and the issue text ("dragging between windows of two different libraries or out
to the Desktop does nothing today") is stale for one of them.

### Direction 2 — out to the Finder: IMPLEMENTED

`LibraryItemDrag.transferRepresentation` (`Models/Document.swift:151-160`)
already vends a real file:

- `FileRepresentation(exportedContentType: .data)` calling
  `SidebarDragID.exportSourceFile`
- which resolves the owning library via `item.libraryId` →
  `LibraryManager.shared.getLibrary(id:)`
- and fetches through `storage.fetchSourceFile(documentId)` — the storage HTTP
  endpoint, **not** a local path, so it holds for a remote server
- filename prefers the server's `Content-Disposition`, falling back to a
  sanitised row name with newlines stripped and capped at 64 characters
- `.exportingCondition { $0.exportsSourceFile }` so a folder row, which has no
  `documentId`, exports nothing rather than a broken file

**Not verified.** This is what the code does; whether a drag to the desktop
actually produces the file needs a real drag session against a running engine.
It belongs on the click-list, not in a closed state.

### Direction 1 — across libraries: blocked, and precisely where

The drop side cannot tell its own library's export from another library's,
because the routing function has no library in it:

```
classifySidebarDropPayload(loadedIDs: [String], hasFileURL: Bool, carriesOwnProcessFlavor: Bool)
```

Every discriminator below it is library-blind. `isInternalSidebarItemID` checks
only the `doc:` shape; `carriesOwnProcessFlavor` is **process**-scoped, and two
libraries are two windows of one process; `isFicheroInternalDragExport` matches
a path prefix shared by every library's exports. A drag from A to B therefore
classifies as `.internalItems`, which is documented as *"a MOVE. Never an
import"* — a move within B of a document B does not have.

The symptom is already in the source as a user-facing untruth: the refusal
reads *"That item is already in this library"*, which is false for a
cross-library drag.

### The asymmetry worth keeping

**Both** drag payloads already carry the library — `SidebarDragID.libraryId`
and `LibraryItemDrag.libraryId`, both `UUID?`. The export path *uses* it to
pick the right storage service. The import path flattens the payload to
`[String]` and throws it away before deciding the route.

So this is not a missing-data problem and needs no new field. One side of the
same struct is library-aware and the other is not, which is why exporting works
and importing cannot.

Cross-library copy still needs a server-side copy endpoint for metadata,
originals and provenance, as the issue itself says. **Importing the exported
file would move the bytes and silently lose everything else** — a fix that
looks complete and is not, which is the shape this document exists to catch.

---

## I. #3686 — the focus map, before any fix

**Nothing changed.** This is the map, and it says the order is broadly right
while the mechanism behind it is only connected for one pane out of five.

### What exists

`PaneFocus` (`ContentView.swift:5`) has exactly the five cases the issue asks
for: `sidebar, content, preview, reading, inspector`. `cyclePaneFocus`
(`ContentView+ActionsNavigation.swift:44`) builds the cycle **conditionally**,
which is more careful than the issue assumes — `.preview` is appended only when
a preview pane actually renders (guarded for widescreen, #1448/#1516) and
`.inspector` only when the inspector is shown. Tab, shift-Tab and the
sidebar's own "next pane" request all route into it.

So the *order* is not the problem.

### The finding: one pane of five is actually focusable

App-wide there are **ten** `.focused()` bindings. Eight are text fields —
rename fields, note fields, the artifact editor, the library filter — which is
correct, local editing focus. One is the workflow canvas. Exactly **one**
binds a pane:

```
ContentView+SidebarLayout.swift:64   .focused($focusedPane, equals: .sidebar)
```

`.content`, `.preview`, `.reading` and `.inspector` are **assigned**
(`focusedPane = .inspector`) but never bound to a view with `.focused()`.

A `@FocusState` value that no view claims cannot take system focus. So Tab
moves a variable that draws a ring — `FadingFocusBorder(isActive: focusedPane
== pane)` — while real keyboard focus stays where it was. The indicator reports
success; the system never moved. **Predicted, not observed:** SwiftUI should
also reset that value to nil, which would make every Tab after the first fall
into the `guard let current = focusedPane` branch and jump to `.content`
forever. Confirming that needs a running app.

### But part of it is deliberate, and that changes the fix

`ContentView+DetailLayout.swift:323` says so directly:

> `// Focus tracking without .focusable() — avoids swallowing first click`

The inspector, preview and reading panes deliberately use a tap gesture plus a
custom overlay instead of real focus, because making a whole column focusable
eats the user's first click. The sidebar pays that cost on purpose, for a
stated reason: `// Make the sidebar focusable so arrow keys navigate the List.
(Removing this broke arrow-key navigation — see #560.)`

So `focusedPane` is **one variable with two meanings**: a genuine SwiftUI focus
binding for the sidebar, and a hand-rolled "which pane is active" indicator for
everything else. That is this month's defect class again — two representations
of one idea, only one of them backed by the system — but here the split was a
considered trade against a real regression, not drift.

**This is why I did not "add the four missing bindings."** That is the obvious
fix, it would make Tab genuinely move focus, and it would reintroduce
click-swallowing across three panes. The right answer is probably
`.focusSection()`, which groups a region for keyboard focus movement **without**
making it a click-stealing focusable control.

### Two smaller facts

- **`.focusSection()` and `.defaultFocus()` are used zero times app-wide.**
  Nothing declares where focus lands when a window opens, and no region is
  grouped for macOS focus movement. `.focusSection()` is very likely the
  missing mechanism for the whole issue.
- **`.reading` is never appended to the cycle.** It is a real `PaneFocus` case,
  set when the user clicks the reading pane (`DetailLayout:156`), but
  `cyclePaneFocus` appends only `.preview` and `.inspector` — so Tab cannot
  reach the reading pane even as an indicator. This is the one-line candidate,
  and I left it alone because the visibility predicate above it already
  conflates the two panes (`previewPaneVisible` is true when `showReadingPane`
  is), so "just append it" would need a run to confirm it does not double-count.

### The bindings were there. They crashed the app on launch.

This is not a prediction. The exact modifier stack — `.focusable()` +
`.focused($focusedPane, equals: .content)` + `.focusEffectDisabled()`, the
sidebar's pattern — **was applied to the content pane and was removed because
it crashed on launch.**

`7c27e9fe2`, 2026-04-16, *"fix: crash on launch — orphaned
`.focusable()`/`.focused()` in standard+widescreen layouts"*:

> The previous focus removal (73782d28) only matched the `.none` layout case
> due to indentation differences. The standard (VSplitView) and widescreen
> (HStack) cases still had `.focusable()` + `.focused($focusedPane)` +
> `.focusEffectDisabled()` which caused a crash at
> `ContentView.mainContentView` getter on launch.

Its diff removes precisely those three lines from the content pane in both
layouts, and adds the *"avoids swallowing first click"* comment on the preview
pane in the same hunk. So both halves of the current design are scar tissue
from one incident, and the comment I quoted above is the surviving note of it.

The surrounding issues confirm the shape of the trap on both sides: **#550**
"Focus ring permanent and wrong size after `.focusable()` removal" and **#560**
"Arrow keys no longer navigate sidebar (regression from `.focusable` removal)"
— removing it broke things too. The sidebar keeps the pattern because it is
built in a *different* view builder; the four unbound panes are all inside
`mainContentView`, which is the getter that crashed.

### Recommendation

**Do not add the four bindings.** It is the obvious fix, it is what the issue
implies, and it is a known launch crash in this exact file — reintroducing it
would trade a keyboard-navigation gap for an app that does not start.

The issue wants a real, non-click-stealing focus path. The mechanism for that
is `.focusSection()`, which groups a region for keyboard focus movement without
making it a focusable control — and it is used **zero** times app-wide, so it
is untried here rather than tried and rejected. That is the daylight job: a
design pass, a build, and a launch test, on the file with the worst
crash history in the app.

---

## The method, and how I got it wrong

`git log --grep "#NNNN"` finds **mentions**, not fixes. That was the stated
premise of this document, and I then broke it in the writing.

I took the **most recent** mention of each issue as its commit. For #4376 the
newest mention is `2fb051b40`, a `test(seams)` commit — so I filed the ⌘A
routing as CONTRADICTED. The actual fix, `ff8d592ae` *"⌘A routes by focus
instead of reaching nobody"*, is two commits older, ships in v2026.08.02, and
carries a dedicated `SelectAllRoutingPolicyTests.swift`. #4459 was the same
shape: a test-rename on top of a real fix.

So the correction has a rule in it. **A fix commit is usually followed by its
test and build-fix commits, which means the newest mention is the LEAST likely
to be the fix.** Read the whole log for an issue, not its head.

The remaining two, #3686 and #3707, failed the other way: an incidental mention
is not weak evidence of a fix, it is *no* evidence, and they belong with the
untouched issues rather than in a section implying someone tried.

Each surviving entry is checked three ways: the commit's **subject** (does it
claim to fix this?), its **files** (does it touch the surface in question?),
and `git tag --contains` (is it in the build Daniel actually has?).

That last one is what matters for Tuesday: **#4377, #4459 and #4458 are not in
v2026.08.02.** Testing them against the shipped DMG would produce false
failures and reopened issues that were never broken.
