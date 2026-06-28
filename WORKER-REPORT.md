
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
