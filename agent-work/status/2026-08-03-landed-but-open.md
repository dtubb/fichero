# Open issues whose fix may already have landed

**Coverage, stated rather than implied:** I examined **31 open issues** across
seven milestones — Library View (Icons, List, Column Browser, Canvas, general),
Inspector, Keyboard Navigation, Drag & Drop. Of those, 14 had a commit
mentioning them on `origin/main`; I read the **full** log for each, not just
its newest entry. **19 have no fix commit and are left alone.**

Counts: A = 7 verify-then-close, B = 1 contradicted, C = 4 unclear, D = 19
untouched.

I examined none of the Engine, Sharing, Chat, Workflow or Settings milestones.

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
| **3364** | double-click should focus current window | `7d2d2fc4c` (2026-07-25, **after** the issue) | yes | Double-click a sidebar row. If it opens a NEW window rather than focusing the current one, the issue stands — the commit ADDED open-in-new-tab/window, which may be the behaviour complained about | 20s |
| **4377** | library multi-select conventions | `38c834c90` | **NO** — committed 2026-08-03, after the tag | shift-click range, ⌘-click toggle, arrow+shift extend. **Not in Daniel's build** — check on a fresh build only | 1m |
| **4376** | ⌘A in the focused surface | `ff8d592ae` | yes | Click a library row, ⌘A → all rows select. Click into a text field, ⌘A → selects the text, **not** the rows | 15s |
| **4459** | sidebar drop vanishes on load failure | `18fdfaa62` | **NO** — 2026-08-01, after the tag | Drop a file the loader cannot read onto a sidebar folder. It must report, not vanish | 30s |

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
