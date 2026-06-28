# Worker Report — lane/uireform (batch 5)

Author: Claude · worktree `ms-uireform` · base `07f12d99` (reset to origin/main).
**Not pushed.** Milestone: **#94 UI Reform — Inspector & Annotation**.

## Picked + implemented

| Issue | Verdict | Commit |
|-------|---------|--------|
| **#2470** interpretations out of the KG tab | **net-new — DONE** | `7d2ff441` |
| #2536 flushAutoSave drops trailing edit | **already fixed on main** (verify/close) | — |
| #2661 click opens new window | **fixed on main** `cb87fa8e` (verify/close) | — |
| #2455 list-detail slide-in from right | **fixed on main** `89ecf5eb` (verify/close) | — |
| #2696 Content-pane default attributes | **design-blocked** ("needs a small design pass first") | — |
| #2458 annotation controls on every reader | **big frontend** — backend CRUD exists; UI is build-gated | — |
| #2255 PencilKit→OCR driver | **needs-design** (labelled) | — |

After verifying each open issue against its acceptance on fresh main, **#2470 was the
one clean, non-design-blocked net-new** — implemented. Three others are already fixed
on main (manager: close); the rest are design-blocked or large build-gated frontend.

## #2470 — interpretations split out of the KG tab (`7d2ff441`)

The KG tab folded the user's **Interpretations** in with the AI's facts. Per the
three-layer model (Ontology = AI facts · Hermeneutic = what sources say ·
Interpretation = the user's reading) and the AI-integrity north star, the KG tab must
not present the user's interpretation as an AI-asserted fact.

First step of #2470 — iterate, not rewrite (moves the existing section, builds no new
list UI):
- Removed `DocumentInterpretationsSection` from `DocumentInspectorArtifactsTab+KGSection`.
- Added a dedicated **`.interpretations` inspector tab** ("Interpretation"), placed
  right after Notes — Daniel's "their own place / Interpretation layer /
  Notes-adjacent". Not crammed into the Notes List+detail layout (which fills), so the
  section gets its own scroll space.
- New thin **`DocumentInterpretationsTab`** hosts the existing
  `DocumentInterpretationsSection` in a `ScrollView`, reading `entityService` from the
  environment the inspector already provides.
- Reworded the KG-tab help text ("...claims and provenance", was "...and interpretations").

Files: `InspectorTab.swift`, `DocumentInspector.swift`,
`DocumentInspector/DocumentInterpretationsTab.swift` (new),
`DocumentInspectorArtifactsTab+KGSection.swift`, `project.pbxproj` (new view → app
target via `add-swift-file.rb`).

**Safety of the enum-case add:** the only exhaustive switches on `InspectorTab` are
`icon`/`helpText` (InspectorTab.swift) and `tabContent`/`availableTabs`
(DocumentInspector.swift) — all updated. The `.knowledgeGraph`/`.notes` matches in
ViewSettings / SidebarModeIcon / LibraryOutlineNode are *different* enums (verified).

**Follow-up (#2470 step 2):** formalize the ontology-vs-hermeneutic distinction *inside*
the KG view (group/label world-fact vs source-attributed by provenance). Same issue, so
left for a follow-up commit rather than splitting #2470.

## Gate results (from this worktree)
- No backend changes → ruff/pytest/mkdocs N/A this batch (all Swift).
- **swiftlint: clean** on all 4 changed Swift files.
- Swift build = manager's Xcode gate. In-editor SourceKit "No such module
  FicheroAPIClient" / "cannot find type" are isolation false positives.
- `#2470` is pure view composition — no unit-testable logic, so swiftlint-only is
  correct (no test added by design, per "tests where logic").

## Verified-done (manager: close)
- **#2536** — `performSave` already coalesces: an in-flight save sets `pendingResave`
  and the running loop re-saves the newest `draftText` (`ArtifactPanel.swift:379-416`),
  exactly the fix the issue asked for. **Gap:** no regression test. It's not safe for a
  no-build worker to add one — the coalescing state is 6+ `@State` vars intertwined with
  the `lastSavedEncoded`/`lastLoadedRaw` cursor-seed-suppression of #2478; extracting a
  testable coordinator blind risks that cursor/seeding behaviour. **Recommend a
  build-capable worker extract an `AutoSaveCoordinator` + add the race test.**
- **#2661** — `cb87fa8e` "keep library clicks in place" (reachable from HEAD).
- **#2455** — `89ecf5eb` "slide list detail in from the right" (reachable from HEAD).

## Design-blocked / deferred
- **#2696** Content-pane default attributes — issue says "needs a small design pass
  first" (which interesting artefacts to surface). Needs Daniel.
- **#2255** PencilKit→OCR — labelled `needs-design`.
- **#2458** annotation controls on every reader — backend CRUD (bbox / highlight /
  promote-to-claim / crop-to-region) already exists in `routes/annotations.py`; the
  remaining work is per-reader SwiftUI rendering + controls (PDF/image/txt/docx/md),
  which is substantial and build/visual-gated. Hand to a build-capable worker.

## Ask
- Close #2536 / #2661 / #2455 (done on main; GitHub state lags).
- For continued throughput, point me at a milestone with **backend (ruff/pytest)** or
  build-unblocked work — #94's clean surface is now #2470 (done) plus verify/close.
