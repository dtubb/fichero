# STATE.md — Fichero

## 2026-06-06 (PM) — Manager session: consistency sweep + IIIF integration

**Branch:** `0.0.2` at `9450c148`, pushed. `main` integrated via PR #1706 (= 0.0.2).
All Swift merges build-gated green via Xcode MCP (`BuildProject`, tab windowtab1).

**Shipped this session (each merged + MCP-build-verified + pushed + issue closed). 0.0.2 now at 16fec8f6:**
- #1701 — 3 hand-written URLSession sites → generated OpenAPI client (DocumentPickerSheet/batches, ComparisonDetailView/model-comparison, LocalModelsSettingsView/local-models).
- #1699 — extracted shared `FicheroWebView`; de-duped WKWebView wrappers (left DocumentKGWebPane's GuardedWKWebView intact — genuinely different).
- #1687 — removed user-facing 30/50 list caps (show ALL, Finder-style); kept recent-N widgets/chips/toggles.
- #1683 — **IIIF/W3C importer integrated** (iiif_import.py + import-iiif CLI). Resolved 3 manifest_import conflicts to feat's page-scoping; fixed a double transcript-write bug (added `write_transcript_artifacts=False` on IIIF→manifest). 568 backend tests green; db.py/knowledge_models additions are no-migration auto-column-add safe.
- #1685 — Finder "Open / Open in New Tab / Open in New Window" context menus + Cmd-click (library/sidebar/entity/claim); new shared `OpenAffordances.swift`; native macOS tabs via addTabbedWindow.
- #1475 — Model Comparison UI made reachable (guard in ContentViewModifiers .chat case; re-applied fresh — the ms/researcher branch was too stale to merge).

**Branch backlog cleared (worktrees + branches):** retired as already-on-0.0.2 / superseded: manifest-folder, manifest-copy-images, webkit-1641 (codex's GuardedWKWebView), apple-stage1-ner-empty (#1633 — already landed, closed). **#1590** (image viewer reflects edited rendition) HELD — its stale branch touches codex's image files Daniel is testing; re-implement fresh after he verifies. ms/researcher worktree is the stale #1475 branch — superseded, do not merge.

**ModelComparisonService migrated** (#1666, cb27f92a, build-green) — all 10 endpoints → generated ops; compare-node fix revealed a systemic class → filed **#1710** (no LibraryPathMiddleware on the generated client; library header hand-passed per call site → silent-422 risk). Adopted rule: fix→sweep→file (memory: fix-then-sweep-for-siblings).

**#1666 URLSession audit done** — KEEP (SSE/binary/WKWebView/lifecycle/transport) vs MIGRATE classified. Concrete migration backlog filed:
- **#1711** — migrate + DE-DUP ActionsService & ActionLibraryService (duplicate /api/actions code paths) → generated client.
- **#1712** — migrate WorkflowExecutionService (7 calls).
- **#1713** — migrate + consolidate IntegrationsService(+AppSpecific).
- **#1714** — Tier-2 stragglers (WorkflowService reinstall-defaults, WorkflowDiagramPreview code JSON, WorkflowStream REST parts).
- Tier-3 (SearchService keywords, Artifact list) blocked on backend OpenAPI exposure.

**#1712 WorkflowExecutionService migrated** (6956d5e5, build-green) — build-gate caught pause/cancel as app-wide (reject the header) vs the other 5 library-scoped; fed back to #1710 as evidence.

**STRONG RECOMMENDATION — land #1710 (LibraryPathMiddleware) NEXT, hands-on.** Every service migration keeps tripping on "which ops take the library header" (compareNode forgot a required one; pause/cancel got a rejected one). A middleware that injects the header by endpoint (app-wide skip-list, mirroring legacy APIClient configureRequest:132-143) makes #1711/#1713/#1714 trivial (no header args at all) and removes the silent-422 class. Do it carefully (add middleware + wire into FicheroClient + a contract test; then optionally strip manual `xFicheroLibraryPath:` args), build-gate via MCP. THEN the remaining migrations.

**Migration queue after #1710:** #1713 (Integrations consolidation) → #1711 (Actions de-dup, bigger) → #1714 (Tier-2 stragglers). Then the rest of the audit plan: #1690 unified knowledge component, #1692 multi-select (notes+entity lists), #1694 exclude-from-search/KG, #1686 entity-as-library, #1703/#1704 folder reorg + file splits, #1700/#1702 reactivity. HOLD #1707 PDF + ContentView-editing chrome until Daniel tests codex's image/layout.

**Filed:** #1707 (PDFs don't render like folders — consistent render path), #1708 (Marshall importer EPIC), #1709 (4 pre-existing Swift test failures), plus the UX-consistency plan #1684–#1705.

**Known issues:**
- #1709: 4 Swift tests fail (AnnotationService wiring, FeatureManager v001 defaults, ImageEditOp display, KGSurfaceTab ordering) — pre-existing, not from this session's merges. Build is green.
- `verify_all.sh` pytest gate hung at 0% CPU (~40min) under the live :8765 backend — environmental (CrossLanguageGate vs Daniel's --reload backend), not a code failure. Backend tests pass when run directly.

**Next session — start here (steady, one at a time, MCP build-gate each):**
- Assess + integrate the remaining 1-ahead branches: **fix/apple-stage1-ner-empty (#1633 — HIGH: feeds #1662 0-SVO Marshall blocker)**, feat/manifest-folder-and-local-metadata, feat/manifest-copy-images, ms/researcher (#1475). Likely-superseded (verify then retire): agent-a0c2a1ba (image-viewer), fix/webkit-reading-surface-1641 (codex did GuardedWKWebView).
- Continue UX-consistency issues: #1690 (unified knowledge edit/display component), #1685 (open in new tab/window context menus), #1684 (Cmd+'/Cmd+Shift+' nav), #1692 (multi-select sidebar/notes/entities), #1694 (exclude-from-search/KG).
- HOLD until Daniel tests codex's image/layout fixes: #1707 (PDF render path) + chrome issues that edit ContentView.
- Marshall epic #1708 children: #1673/#1674/#1675/#1676/#1677/#1678/#1662.

---

## 2026-06-06 — Session ended after Marshall SwiftUI layout/image fixes (codex)

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
