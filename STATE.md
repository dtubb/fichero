# STATE.md — Fichero

## 2026-06-06 — Session ended after Marshall SwiftUI layout/image fixes

**Branch:** `0.0.2` at `00ad0ca8` (`fix(layout): keep reading pane toggles stable`).

**Current focus:** Marshall IIIF/W3C import and staged workflow reliability. Keep the existing Catalogue workflow mostly intact; add/review staged workflows and chain them once each layer is reliable.

**What is known:**
- SMB transfer previously completed at about 29G in `_stage`, but re-check before assuming current local state.
- Live backend storage returns real JPEG bytes for `MarshallStage5-133917.fichero`: thumbnail `157x200`, display `786x1000`.
- SwiftUI fixes pushed: storage image loads key by `(document_id, image_type)` and Library/Search pane toggles are stable across Library/List, Document Canvas, Reading/WebKit, and Inspector.
- Remaining generated-client risk is tracked on #1666: raw image-editing, artifact/KG, and model-comparison URLSession paths still need migration/allowlist tests.
- 5-page/10-page imports worked previously; 20-page workflow completion/progress remains the scale gate.

**Open issue cluster:**
- #1666 generated-client/raw URL audit.
- #1669 staged Catalogue split.
- #1673 long-stage page progress/checkpoint visibility.
- #1674 imported vs extracted entity provenance layers.
- #1675 reversible merge/split audit trail.
- #1676 post-entity SVO/KVO stage.
- #1677 SwiftUI review UI for staged layers.
- #1678 ontological KG layer.
- #1680/#1681 Marshall SwiftUI storage/layout QA.

**Next session — start here:**
- Ask Daniel to test the latest `0.0.2` in Xcode with `MarshallStage5-133917.fichero`: thumbnails, center canvas image, Reading/WebKit text, and Inspector should stay stable.
- Re-check `_stage` size and SMB/copy status, then resume Marshall staged import testing at 5 → 10 → 20 pages.
- If SwiftUI still shows placeholder icons while `/api/storage/thumbnail/{id}` returns JPEG, inspect `LibraryImageView` environment service injection and `DocumentThumbnailView` branch selection.
- Continue #1666 by adding an allowlist test for raw URLSession paths, then migrate `ImageEditingServiceGenerated` or `ArtifactServiceGenerated` slices to generated OpenAPI.
- Continue staged workflow/chain work from #1669/#1673; do not modify `catalogue.json` directly.
