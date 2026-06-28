
## UI Reform — Inspector & Annotation (#94), batch 2 — 2026-06-28, f_fichero_claude_swiftui

### #2697 — Folder vs children ownership ambiguity — DONE
Commit 550e7531, authored Claude.
- Root: #2521 already added the current/children scope toggle + "Includes children" row badge; the residual confusion was the DEFAULT (includeChildren=true).
- Fix: flipped shared `inspector.scope.includeChildren` @AppStorage default true→false in BOTH consumers (DocumentInspectorArtifactsTab+KGSection = entities, DisplayAttributesStrip = attributes). Folder/PDF now shows OWN records by default; children opt-in + badged. Artefacts already own-scoped (#721).
- Guard test (KnowledgeGraphInspectorSectionTests): both declarations pinned to same false default (one key, must agree).
- Broader ownership visual-hierarchy redesign = design-gated, left for Daniel.

### #2696 — Content-pane top attributes default — DONE
Commit c7a3a893, authored Claude.
- Fix: default `inspector.attributeStrip.kg` ""→"entities" so the strip surfaces entities; gated the entities row on entityCount>0 so it appears "as added", not "Entities —" on empty pages. Claims stay opt-in; filter menu unchanged. @AppStorage declared-default takes effect for all who haven't customised the KG menu (incl. Daniel).
- Guard test added (entities default + count gate).
- Per-kind People/Places rows + trimming fixed-attr defaults = larger design pass, left for Daniel.

### Pre-existing test-suite breakage (separate commit e512f7b6)
- build-for-testing surfaced pre-existing FicheroTests compile breaks on main again (my prior Workflow repairs WERE merged). Fixed: ChatWithDocsRoutingTests stale `route.sidebarShowsChat` assertion (field removed from ChatWithDocsRoute; no-swap behaviour guarded by sibling test).
- REMAINING pre-existing break beyond scope: SpatialScene3DTests reads fileprivate `persistedDragEndPosition` (test/source access mismatch). Recommend a dedicated test-suite-repair task; stopped the whack-a-mole there.

Verification: each issue app-build green (isolated xcodebuild, scratch DD, CODE_SIGNING_ALLOWED=NO); my source + test files compile with ZERO diagnostics. Suite not RUN (no-test-on-this-machine rule); build-for-testing used to compile-verify. NOT pushed.

## UI Reform — Inspector & Annotation (#94): #2458 annotation controls — SLICE 1 DONE
2026-06-28, f_fichero_claude_swiftui. Commit b50f3984, authored Claude.

#2458 is broad; did Slice 1 well and stopped (per dispatch). Slice 1 = shared annotation control (highlight + note) + render saved annotations, wired into the text/markdown reader (PageContentPane), page-scoped (#2396).
- NEW: AnnotationToolbar (shared bottom bar, reusable across readers), AnnotatableTextView (AppKit NSViewRepresentable: renders highlights at char spans + reports UTF-16 selection; iOS render-only fallback; #if-guarded), AnnotationHighlight (pure range calc).
- EXTENDED (additive): AnnotationService.addNote + AnnotationStore.addNote gain charStart/charEnd → AnnotationCreateRequest (backend already supported char_start/char_end). No new store, no hand-rolled URLSession; typed client only.
- PageContentPane: loads page annotations via AnnotationStore, renders saved highlights, creates highlight (from selection) + note (popover composer) annotations. Claim-source highlight path preserved. Annotation methods in same-file extension to stay under type-body limit.
- Tests: AnnotationHighlightTests (7 cases). swiftlint clean.
- Verification: app build green (isolated xcodebuild, scratch DD, CODE_SIGNING_ALLOWED=NO); my source + test compile with ZERO diagnostics. Suite not RUN (no-test-on-this-machine); only test-target blocker is the PRE-EXISTING SpatialScene3DTests fileprivate break (still unfixed on main — recommend dedicated test-suite-repair task). NOT pushed.

### STOPPED HERE. Remaining:
- Slice 2: PDF (PDFKit highlight/note — PDFPageView already makes PDFAnnotation highlights, extend) + image bounding-box overlay editor (bbox normalized rect + page id) + render saved boxes. Reuse AnnotationToolbar.
- Slice 3: docx reader text-range highlight/note (reuse AnnotatableTextView).
- Plumbing (AnnotationToolbar, AnnotationHighlight, addNote charStart/charEnd/bbox) already in place for both.

### #2458 SLICE 2 — image bounding-box annotations — DONE (PDF = Slice 2b remaining)
Commit 7f067402, authored Claude.
- Implemented the reader-toolbar annotation stub on the IMAGE reader (ZoomableImagePreview.requestAnnotation, previously a #2458-owned stub). Highlight/Note arm a region-draw overlay → normalized bbox persisted via AnnotationStore/AnnotationService (typed; no new store, no URLSession). Bookmark = whole-image marker. Saved boxes render back over the image.
- NEW: BoundingBoxGeometry (pure, unit-tested: normalized↔view-rect via visible window + drag→box clamp/corner-order), BoundingBoxOverlay (reusable SwiftUI draw/render layer). Tests: BoundingBoxGeometryTests (8 cases).
- Reuses existing ReaderToolbar onAnnotate hook (#2423) — no parallel toolbar.
- Verification: app build green (isolated xcodebuild, scratch DD, no signing); my source + test compile ZERO diagnostics. Test target only blocked by PRE-EXISTING SpatialScene3DTests fileprivate break (still unfixed on main; dedicated repair task recommended). Suite not RUN (no-test-on-this-machine). NOT pushed.
- NOTE: bbox pixel alignment under zoom/letterbox needs device visual-verification (math is tested; live viewport mapping unverifiable headless).

### STOPPED HERE (Slice 2b + Slice 3 remaining):
- Slice 2b — PDF page regions: render saved regions as native PDFAnnotations in PDFPageView (PDFKit handles page coords; reuse existing claim-source PDFAnnotation pattern ~PDFPageView L490/789) + creation via PDFKit selection. Needs PDFPageView page↔view geometry + device visual check.
- Slice 3 — docx reader text-range highlight/note (reuse AnnotatableTextView).
