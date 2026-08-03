# Open issues whose fix may already have landed

**Coverage, stated rather than implied:** I examined **31 open issues** across
seven milestones — Library View (Icons, List, Column Browser, Canvas, general),
Inspector, Keyboard Navigation, Drag & Drop. Of those, 14 had a commit
mentioning them on `origin/main`; I read all 14 subjects and inspected the
ambiguous ones. **17 have no referencing commit and are left alone.**

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

## B. CONTRADICTED — the commit mentions the issue but does not fix it

These would be mislabelled "landed" by a `git log --grep` alone. **Each needs
re-diagnosis, not closing.**

| # | Issue | Mentioning commit | What it actually does |
|---|---|---|---|
| **4458** | scope content-pane drop to detailColumn | `fbc1bbd1c` | Titled **#4401**; touches only `Sidebar/` files. Does **not** touch `ContentViewModifiers` or `RootLayout`. The real fix is `6a11a9fc2` on `lane/lane-crash2`, **not yet merged** |
| **3707** | drop semantics via the audited action layer | `964cff1e5` | `chore: restore release gate coverage baselines` — an incidental reference |
| **4459** | external drop temp-copy cleanup | `eeda9aff8` | `fix(tests): the drop-cleanup test follows its function to its new name` — a test rename, not the cleanup |
| **3686** | focus management / tab order | `283a28e52` | A docs/audit commit whose subject names **#3690** |
| **4376** | ⌘A in the focused surface | `2fb051b40` | `test(seams)` — a test commit, not the ⌘A behaviour |

## C. UNCLEAR — do not act on these without reading them properly

| # | Issue | Why unclear |
|---|---|---|
| **4160** | EPIC: library view quality pass | `e40eb0c9e` is one STEP of a multi-step epic; the epic is not the step |
| **4005** | wire-in or delete legacy canvas fallbacks | `9ab922b62` moves `SpaceSceneView` between directories — filing, not wiring-or-deleting |
| **3700** | entities/annotations as columns | `b692ef127` is a merge commit; the work behind it was not read |
| **3703** | entities draggable | `eb9297dba` is a merge commit; same |

## D. STILL OPEN — no referencing commit found (17)

1692, 1950, 1962, 2272, 2418, 2422, 3685, 3687, 3688, 3689, 3697, 3698, 3699,
3706, 4204, 4236, 4311.

Several are EPICs (1962, 3685) where "no commit" is expected.

---

## The method, and why it matters

`git log --grep "#NNNN"` finds **mentions**, not fixes. Five of fourteen
matches in section B are exactly that — and one of them, #4458, would have had
me report a bug as already-fixed when the real fix is sitting unmerged on my
own branch.

So each entry was checked three ways: the commit's **subject** (does it claim
to fix this?), its **files** (does it touch the surface in question?), and
`git tag --contains` (is it in the build Daniel actually has, or only on
`main`?).

That last one is the distinction that matters for Tuesday: **#4377 is on `main`
but not in `v2026.08.02`.** Testing it against the shipped DMG would produce a
false failure and a reopened issue that was never broken.
