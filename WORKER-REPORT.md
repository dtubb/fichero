# Worker Report — lane/uireform (batch 3)

Author: Claude · worktree `ms-uireform` · base `c224697b` (reset to origin/main).
**Not pushed.** Milestone: **#93 UI Reform — Representations**.

## What I picked and why

I reset to main (prior #2264/#2265/#2266/#1684 already merged) and triaged the 5
open non-EPIC issues. After verifying each against its acceptance criteria, exactly
**one** was a genuine, safe, net-new gap — the rest are already done, a forbidden
toolbar file, or substantial/design-gated. I implemented the one and verified the
others precisely so the manager can close them.

| Issue | Verdict | Action |
|-------|---------|--------|
| **#2519** artifacts-browser multi-select + delete | **net-new gap — DONE** `f9737c05` | implemented + tests |
| #2481 three-pane split | **DONE** (verify/close) | `SplittablePane.paneCount` cycles 1/2/3 |
| #2474 sidebar mini-toolbar touch + glass | **DONE** (verify/close) | `SidebarModeBar:116-117` 44pt + `.glassEffect` |
| #2520 immersive full-screen | **partial — design-gated** | core built; remainder needs #2516 + build |
| #2467 reader mini-toolbars | **skipped** | ReaderToolbar = forbidden file |
| #2670 / #2667 | **EPICs — skipped** | — |

## #2519 — artifacts browser multi-select + delete (`f9737c05`)

The earlier sweep (`e334f3c2`) gave multi-select+delete to 6 browsers (notes,
research projects, entities, claims, workflow chains, workflow library) but **skipped
the artifacts browser itself — #2519's headline target.** `ArtifactListView` still
used single-selection (`List(selection: $focused.id)`), so ⇧/⌘-click + ⌫ didn't work.

Implemented by mirroring the proven `NoteListView` pattern (iterate-never-replace):
- `List(selection: Set<String>)` native multi-select; ⌫ (`onDeleteCommand`) +
  context-menu "Delete" act on the **full** selection with a destructive confirm.
- **Detail-follow + multi-window sync preserved** via a guarded two-way mirror with
  the shared `FocusedArtifact` (single → focus that row, multi → keep current so the
  detail doesn't jump mid-batch, empty → clear). No custom gestures fighting
  `List(selection:)` — honours the no-wholesale-list-rerender rule.
- New **`ArtifactStore.delete(_:)`** — the store owns the endpoint (observable-data-
  layer); the view never calls the service. Best-effort batch under each artifact's
  own `documentId`, then one `reload()` reconciles in place.
- Pure logic factored into **`ArtifactSelection`** (`resolve` / `focusedID`) and
  unit-tested.

Files: `Views/Library/ArtifactListView.swift` (+`ArtifactSelection` helper),
`Models/ArtifactStore.swift` (+`delete`), `fichero-tests/ArtifactSelectionTests.swift`.

### Tests (`ArtifactSelectionTests`, 7 cases — repro + edge + regression)
- resolve returns the full selection in **list order** (not set order);
- **empty selection → [] (regression: never delete-all)**;
- stale/absent ids dropped; empty-list → [];
- focus rules: empty → nil, single → that row, **multi → keep current (no jump),
  and stays nil if current is nil**.

## Gate results (from this worktree)
- **No backend changes this batch** → `ruff`/`pytest` N/A (all Swift). For
  reference, the engine is untouched since the last merged batch.
- **swiftlint: clean** on all three changed Swift files (also under the 400-line
  file-length limit — ArtifactListView 270).
- **Swift build/tests: the manager's Xcode gate** (no xcodebuild on Daniel's
  desktop). Cross-file SourceKit "cannot find type / unable to type-check"
  diagnostics seen in-editor are isolation false positives (same-module symbols).
- **pbxproj note:** the test target is a filesystem-synchronized group (Xcode 16) —
  `ArtifactSelectionTests.swift` is auto-included by living in `fichero-tests/`; I
  reverted `add-swift-file.rb`'s erroneous attempt to compile it into the *app*
  target (which would have broken the build).

## Verified-done (manager: close)
- **#2481** — `SplittablePane` has `paneCount` and "each axis cycles through 1, 2,
  and 3 panes" with `verticalPaneCount`/`horizontalPaneCount` + resizable dividers.
- **#2474** — `SidebarModeBar` normalizes to 44pt (`MiniToolbar.standardHeight`) and
  applies `.glassEffect(.regular, in:)`. Both criteria met.

## Flagged (not safe/clean to do blind)
- **#2520 immersive** — `FullScreenImagePreview` already does black-bg + page-only +
  pinch-zoom + close + swipe-dismiss. Remaining acceptance: auto-hide bottom filmstrip
  and overlay annotation buttons — both substantial, and annotations are explicitly
  gated on the #2516 palette decision ("reuse, don't fork"). Also platform-conditional
  (`#if os(macOS)` / `canImport(UIKit)`) — needs a build + visual loop.
- **#2519 sweep (fix-then-sweep):** the documents/files list, search results, and
  actions browsers may still lack a consistent multi-delete. Search-result / action
  deletion is semantically ambiguous (results aren't owned rows; actions are audit
  records) — needs a product call before wiring. Left for a follow-up under #2519
  rather than expanding this commit (one-commit-per-issue).
- **#2467** reader mini-toolbars — ReaderToolbar.swift is a forbidden file (Daniel's
  area); untouched.
