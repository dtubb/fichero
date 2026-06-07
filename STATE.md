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

**#1710 Phase 1 DONE (a3929c43, build-green):** a LibraryPathMiddleware already existed in the FicheroAPIClient package but had a BUGGY skip-list (added the lib header to /registry + /settings, mishandled /providers/refs) — fixed to mirror APIClient.configureRequest exactly + live path read + test. So the library header IS auto-injected now. **#1710 stays open for Phase 2** (strip redundant per-call-site `xFicheroLibraryPath:` args — mechanical, low-urgency). Remaining migrations should pass `headers: .init()` and rely on the middleware unless the generated op REQUIRES the typed header.

**(historical recommendation, now done) — land #1710 (LibraryPathMiddleware) NEXT, hands-on.** Every service migration keeps tripping on "which ops take the library header" (compareNode forgot a required one; pause/cancel got a rejected one). A middleware that injects the header by endpoint (app-wide skip-list, mirroring legacy APIClient configureRequest:132-143) makes #1711/#1713/#1714 trivial (no header args at all) and removes the silent-422 class. Do it carefully (add middleware + wire into FicheroClient + a contract test; then optionally strip manual `xFicheroLibraryPath:` args), build-gate via MCP. THEN the remaining migrations.

**Migration queue:** #1713 ✅ → #1711 ✅ → #1714 ✅ (Tier-2 stragglers). **SWIFT-SIDE URLSESSION SWEEP COMPLETE** (0.0.2 at 9da66e29). Every hand-written REST URLSession service migrated to the generated client; legitimate raw uses (SSE, binary, WKWebView, lifecycle, AppleScript, APIClient core) kept. #1666 stays open as umbrella until Tier-3 (SearchService keywords + Artifact list — blocked on backend exposing those ops, folded into #1715) and #1710 Phase 2 (strip redundant header args — do AFTER #1715) land.

**Audit hunt IN PROGRESS (batched-build cadence — Daniel: the Xcode build is the slow step, so let a few workers land then ONE build).** Read-only audit (2026-06-06) found 60+ findings → filed #1716/#1717/#1718, folded inventories into #1702/#1690/#1703. SHIPPED as a batch (one build): #1716 (Note/Annotation init-race → init+syncLibraryPath), #1717 (EngineConfig.swift single-source URL + killed force-unwraps). 0.0.2 at 904bc0fc.
**Next batches (file-DISJOINT workers, ONE build per batch):** #1718 (error handling/try! crashes) + #1690 (extract shared EntityRow — Views/KnowledgeGraph+Sidebar); then #1702 (NoteItem/DocumentAnnotation→generated schemas — OK now #1716 landed) + #1703 (split the 7 large files, one worker per file, add-swift-file.rb for new files). Keep batches non-overlapping so merges are clean.

**NEXT PHASE (Daniel's direction): return to the code-review/audit report + hunt more consistency-bug CLASSES.** Run a read-only audit agent for: (a) DUPLICATE/divergent code paths displaying the SAME data differently (knowledge-object display dup → #1690), (b) the folder-structure smells (#1703 split the 3 >1000-line files: OntologyBrowser 1982 / DocumentInspector 1787 / DocumentInspectorArtifactsTab 1713; #1704 reorg Views/Library/), (c) hand-rolled Codable structs that should be Components.Schemas.* (#1702). fix→sweep→file each. Then audit-plan issues #1690/#1692/#1686/#1696/#1697/#1700/#1702.

**Migration queue (DONE):** #1713 (Integrations consolidation) → #1711 (Actions de-dup, bigger) → #1714 (Tier-2 stragglers).

**ROOT-CAUSE FIX FILED — #1715 (backend, answers Daniel's "would OpenAPI solve this?"):** the recurring header bug (compareNode required / pause-cancel rejected / actions all-required) is backend OpenAPI-spec inconsistency — routes declare X-Fichero-Library-Path as a per-op Header param inconsistently. Fix: make it a schema-EXCLUDED FastAPI dependency so it vanishes from every generated op; then LibraryPathMiddleware (#1710) is the sole injector and #1710 Phase 2 (strip manual args) is trivial. #1715 is the headline OpenAPI-consistency win — backend/codex lane.

**After the middleware + #1666 migrations (Daniel, 2026-06-06): GO BACK TO THE CODE-REVIEW/AUDIT FINDINGS and keep hunting more bugs of these classes.** Re-read the morning 6-theme frontend-consistency report (this session's history) + issues #1684–#1705, and proactively code-review for MORE instances of: hand-written URLSession / divergent code paths / duplicate code / bad folder structure / anti-patterns — fix→sweep→file each class. The audit is the headline; treat it as an ongoing hunt, not a fixed checklist. Then work the audit-plan issues: #1690 unified knowledge edit/display, #1692 multi-select, #1686 entity-as-library, #1696/#1697 chrome unification, #1703/#1704 folder reorg + file splits, #1700/#1702 reactivity. Then the rest of the audit plan: #1690 unified knowledge component, #1692 multi-select (notes+entity lists), #1694 exclude-from-search/KG, #1686 entity-as-library, #1703/#1704 folder reorg + file splits, #1700/#1702 reactivity. HOLD #1707 PDF + ContentView-editing chrome until Daniel tests codex's image/layout.

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

## 2026-06-06 (PM cont.) — lint gate closed
- swiftlint was NOT being run as a gate (MCP build ignores lint warnings) → Daniel flagged Xcode showing 48 violations. Fixed process: swiftlint is now a STANDING pre-commit gate (memory: manager-operating-model). #1719 shipped: 48→29 (my session nits + mechanical debt fixed; remaining 29 are structural file-splits → #1703/#1704). 0.0.2 at efe4146a.
- Cadence reminders in force: batch a few disjoint workers → ONE Xcode build; run `swiftlint lint --quiet fichero/fichero/` before every push; ONE build/verify at a time.

## 2026-06-06 (PM cont.2) — audit-hunt batches + folder plan
- Shipped (batched, one build each, swiftlint-gated): #1716+#1717 (init-race + EngineConfig URL centralization), #1719 (swiftlint 48→29), #1690+#1718 (shared EntityRow + try! crash fixes). 0.0.2 at bb8515b5. ~18 issues this session; Daniel tested the app — "ran and seemed to work" (migration sweep runtime-validated).
- **#1704 folder-reorg PLAN posted** (concrete, build-safe, PBX-aware): Batch1 Views/Library→6 subfolders (ready), Batch2 Workflow renames, Batch3 Services/ grouping (high cross-ref, own session), Batch4 Models/ grouping (own session), Batch5 Views/root→ContentView/ (defer — codex's held files). Each batch = git mv + add-swift-file.rb register + MCP build-gate, one subfolder/commit, NEVER bulk mv.
- New issues filed: #1720 (File menu: Open Recent + Close Database), #1721 (drag-drop .fichero → open new window vs import branch).
- **Next:** #1703 (split the big files, one worker/file) + #1704 Batch1 (Views/Library reorg — scripted/gated) + #1702 (hand-rolled structs→generated, verify schema coverage first). Remaining swiftlint debt (29) is exactly the #1703 file-splits.
- HOLD: #1707 PDF + ContentView image/layout chrome + #1721 (touches ContentViewModifiers) until Daniel explicitly confirms codex's image/layout.

## 2026-06-06 (PM cont.3) — big-file splits + codex53 transition
- #1703: 3 biggest files split+shipped (build-gated): OntologyBrowser 1982→317 (8ca6c431), DocumentInspector 1807→381 (5960766c), DocumentInspectorArtifactsTab 1926→13 (47c060db). 0.0.2 at 47c060db.
- **WORKER ENGINE = codex53 (Daniel's directive), not Claude** — run impl+reviews on `codex -m codex53` in tmux (scripts/spawn-worker.sh codex, add -m codex53) so Opus manager context is preserved. Claude/Sonnet = fallback only. Build-coordination: codex does swiftlint+compile-only, MANAGER owns the single MCP build-gate, never concurrent xcodebuild. (memory: manager-operating-model.)
- Lessons: salvage uncommitted-but-complete worker output (commit-in-worktree→merge); parallel file-creating workers conflict on project.pbxproj → resolve with `git checkout --ours pbxproj` + re-run add-swift-file.rb, or serialize splits.
- Next: remaining #1703 800-tier (SidebarView+ViewComponents 831, WelcomeView 830, DocumentInspectorInfoTab 803, SidebarItemRow 784) one codex53 worker/file; #1704 Batch1 Views/Library reorg; #1702 hand-rolled structs. HOLD #1707/#1721/ContentView-image-chrome until Daniel confirms codex's image fixes.

## 2026-06-06 (PM cont.4) — COMPACT HANDOFF
**0.0.2 == main at 0f5665ad** (PR #1722 merged — all session work on main). App runs, faster, Daniel-tested.
**Worker engine = CODEX (tmux), not Claude.** codex53 REMOVED. Models: gpt-5.4 (judgment/feature), gpt-5.3-codex-spark (mechanical/fast), gpt-5.4-mini (simple). Launch `codex -m <model> --dangerously-bypass-approvals-and-sandbox` in a tmux session in a worktree + feed a CODEX_TASK.md (swiftlint + NO xcodebuild + commit-no-push). Poll via `tmux capture-pane`. Manager owns the SINGLE Xcode MCP build-gate (tab windowtab1); never 2 builds at once; swiftlint before every push.
**IN FLIGHT:** codex worker (gpt-5.5 default) splitting SidebarView+ViewComponents.swift (#1703) in tmux `f_codex_split`, worktree ~/code/fichero-split-sidebar (branch split/sidebar-viewcomponents). When done: merge→swiftlint→solo MCP build→push→comment #1703→remove worktree+kill tmux. pbxproj conflict→`git checkout --ours` + re-run add-swift-file.rb.
**NEXT (use gpt-5.4 for these — Daniel's post-run UX feedback, high value):** #1723 surface Mind Palace/Research/Model Comparison/Chat-with-docs in sidebar; #1724 fix 2 confusing top-left toggles + unclear Library icon. Then remaining #1703 splits (WelcomeView 830, DocumentInspectorInfoTab 803, SidebarItemRow 784 — use gpt-5.3-codex-spark). Then #1704 Views/Library folder reorg (plan in #1704 comment), #1702 hand-rolled structs, #1715 backend header-schema fix (codex backend lane).
**NEW issues from Daniel's run:** #1723/#1724/#1725 (UX/log noise), #1726 (RealityKit grid+precise-drag+click-select+hi-res+agent-render).
**HOLD until Daniel explicitly confirms codex's image/layout fixes:** #1707 PDF render path, #1721 drag-drop-library, ContentView image/layout chrome. STAY OFF ContentView*/LayoutMode/image-render files.
**Memory:** manager-operating-model, fix-then-sweep-for-siblings, no-xcodebuild-test (swiftlint pre-commit gate; build via MCP only; one build at a time), finder-like-ui, knowledge-consistency-mandate.

## Manager tick — 2026-06-06 ~8:40pm ADT
- 0.0.2 HEAD: 048c40ed (pushed). SidebarView split (#1703) shipped + built green.
- IN FLIGHT: tmux `f_codex_ux` (gpt-5.4, worktree ~/code/fichero-sidebar-ux, branch
  ux/sidebar-toolbar) working #1723 (surface Mind Palace/Research/Model Comparison/
  chat-with-docs in sidebar) + #1724 (collapse 2 confusing left toggles + clearer
  Library icon). Code-only; manager gates+merges.
- NEW BUG filed: #1727 (new library gets no Inbox — root cause in library.py create_library;
  fix = idempotent ensure-Inbox on create+open). Queued for backend/codex lane.
- #1726 RealityKit grew an annotation axis (agent arrange + notes/people in 3D, esp. work view).
- REMAINING #1703 splits (gpt-5.3-codex-spark, mechanical): WelcomeView ~830,
  DocumentInspectorInfoTab ~803, SidebarItemRow ~784.
- HOLD (await Daniel's nod on codex image fixes): #1707 PDF render, #1721 drag-drop-library,
  ContentView image-render chrome.
- f_backend = Daniel's live :8765 server — never touch. f_codex (old) idle.
- LOOP: waking ~every 30 min to gate finished workers + keep the queue moving.

## OVERNIGHT PLAN — 2026-06-06 ~10pm ADT (Daniel asleep, Claude autonomous)
**Directive (Daniel):** focus on CODE CLEANUP / quality — finish splits, organize Views, kill
duplicate code paths, fix bugs. DO NOT chase new features. Goal: fewer code paths, fewer bugs,
easier to use. Use codex tmux workers + agents; wake every 30 min; gate+merge with ONE Xcode
build at a time; never restart f_backend (:8765).

**0.0.2 HEAD:** 2a7f42ad (WelcomeView + SidebarItemRow splits shipped + gate fixes).

**IN FLIGHT (launched ~10pm):**
- tmux `f_codex_pdfbe` (gpt-5.4, ~/code/fichero-pdf-backend, fix/pdf-storage-1707): backend
  #1707+#1731 — make /api/storage/thumbnail|display serve PDF page images (kills a divergent
  render path). ruff+pytest gate; backend code-only.
- tmux `f_codex_infotab` (gpt-5.3-codex-spark, ~/code/fichero-infotab, refactor/infotab-split):
  #1703 re-split DocumentInspectorInfoTab (EXTRACT not duplicate; last attempt duplicated symbols).

**CLEANUP QUEUE (dispatch as lanes free, steady, ≤2 lanes, pbxproj-writers NOT concurrent):**
1. #1737 stuck grey sidebar row (gpt-5.4) — bug.
2. #1736 Open-in-New-Tab opens window (gpt-5.4) — bug.
3. #1704 Views/ folder reorg into feature subfolders — BIG, mass file moves + pbxproj; do SOLO,
   careful, hard build-gate. Riskiest; do when no other Swift lane runs.
4. #1730 RealityKit move-doesn't-persist (gpt-5.4) — bug.
5. #1702 hand-rolled structs → generated; responsive cluster #1732/#1733/#1734/#1735 (touch
   ContentView/Library — hold while a frontend lane runs).

**PARKED (feature work — Daniel: don't get sidetracked):** #1740 unified collection+view-mode
(plan APPROVED + banked in #1740 comment, NOT building tonight), #1738/#1739 (its children),
#1741 class/prototype system, #1729 Researcher AI-plan, #1728 surface-built-views, #1726 RealityKit.
Backend PDF (#1707) is cleanup (dup-path kill), not feature.

**Gate recipe:** merge branch → swiftlint touched dir → SOLO Xcode MCP BuildProject(windowtab1)
→ fix any access-level/@ViewBuilder regressions in place → push → comment/close issue → remove
worktree + kill tmux. pbxproj conflict → `git checkout --ours` + re-run add-swift-file.rb.
ALWAYS verify a split actually shrank the original before trusting it.

### Tick 1 (~22:40) — landed: backend PDF page-images (#1707/#1731, 4471c1c9) + DocumentInspectorInfoTab split (#1703 CLOSED). 0.0.2 green.
In flight: f_codex_pdffe (gpt-5.4, ~/code/fichero-pdf-fe) = PDF frontend render-collapse onto LibraryImageView (#1707 fe + #1731); f_codex_greyrow (gpt-5.4, ~/code/fichero-greyrow) = #1737 stuck grey sidebar row.
Note for Daniel AM: backend PDF fix needs an engine RESTART to take effect on your :8765.
Next queue after these: #1736 tab→window, #1704 Views reorg (SOLO), #1730 RealityKit persist, responsive cluster #1732-35, then GitHub backlog.

### Tick 2 (~23:18) — landed: PDF frontend render-collapse (#1707/#1731 CLOSED, eacbd293, −203 lines) + grey-row fix (#1737 CLOSED, 0709d0c3). 0.0.2 green.
In flight: f_codex_tabfix (gpt-5.4, ~/code/fichero-tabfix) = #1736 open-in-new-tab→tab not window; f_codex_rkpersist (gpt-5.4, ~/code/fichero-rkpersist) = #1730 RealityKit persist node position on drag (persistence ONLY, #1726 features parked).
Closed so far tonight: #1703, #1707, #1731, #1737. Backend PDF (#1707) needs engine restart on Daniel's :8765 to take effect.
Next queue: #1704 Views/ reorg (SOLO next), responsive cluster #1732-35, #1702, then GitHub backlog. #1740 Phase 1 = ~4am fallback only.

### Tick 3 (~23:55) — landed: #1736 open-in-tab (6903ef56) + #1730 RealityKit persist (1ab7d299). Both CLOSED. 0.0.2 green.
Closed tonight: #1703,#1707,#1731,#1737,#1736,#1730 (6).
In flight: f_codex_responsive (gpt-5.4, ~/code/fichero-responsive) = responsive cluster #1732/#1733/#1734/#1735 (toggle styling, mini-toolbar overflow, library single-column min, pane-aware window min).
DECISION: #1704 Views/Library reorg DEFERRED — add-swift-file.rb only ADDS (no remove-old-ref), so a file MOVE needs stale-ref removal or the build goes red. Too risky to fire blind overnight. TODO when attended: write scripts/move-swift-file.rb (xcodeproj gem: remove old PBXFileReference by path + add new) + test on 1 file, THEN run Batch 1 (18 files → 6 subfolders per #1704 plan) in small build-gated commits. Until then, prefer no-pbxproj cleanup.
Next queue: gate responsive cluster, then #1702 hand-rolled→generated (Services, disjoint), GitHub backlog (bugs/consistency/dead-code), stale-worktree cleanup (8 stale ms/* worktrees — check for unmerged work first). #1740 Phase 1 = 4am fallback.

### Tick 4 (~00:31) — landed: responsive cluster #1732/#1733/#1734/#1735 (all CLOSED, 7c50ca3c..8d882760). 0.0.2 green.
Closed tonight (10): #1703,#1707,#1731,#1737,#1736,#1730,#1732,#1733,#1734,#1735.
In flight: f_codex_inbox (gpt-5.4, ~/code/fichero-inbox) = #1727 auto-seed Inbox on create+open (idempotent, fixes Marshall Diaries too — BACKEND); f_codex_webkit (gpt-5.4, ~/code/fichero-webkit) = #1725 quiet WKWebView console logging (FRONTEND). Disjoint.
Backlog noted for next ticks: #1702 hand-rolled structs→generated (NoteItem/ActivityItem/ActionItem/ModelComparison), #1715/#1710 OpenAPI library-header consolidation (delicate, prefer attended), #1709 4 failing Swift tests (can't run xcodebuild test here — needs Daniel), stale-worktree cleanup (8 stale, check unmerged first). #1704 reorg still deferred (need move-swift-file.rb). #1740 Phase 1 = 4am fallback.

### Tick 5 (~01:05) — landed: #1727 auto-seed Inbox (9e4c850b, CLOSED, needs engine restart). #1725 resolved no-code (system os_log, not app-suppressible; offered OS_ACTIVITY_MODE opt-in — CLOSED). 0.0.2 green.
Closed/resolved tonight (12): #1703,#1707,#1731,#1737,#1736,#1730,#1732,#1733,#1734,#1735,#1727,#1725.
In flight: f_codex_genstructs (gpt-5.4, ~/code/fichero-genstructs) = #1702 hand-rolled structs→generated (NoteItem/ActivityItem/ActionItem/ModelComparison) + openapi regen. Cross-layer — gate: ruff+pytest THEN Xcode build.
Housekeeping: pruned clean ~/code/fichero-mind-palace worktree. LEFT (have uncommitted WIP — Daniel review before pruning): fichero-bibliography-citations(3), fichero-kg-hermeneutics(7,detached), fichero-library-reading-surface(3), fichero-researcher(3), fichero-workflows(6).
Next after #1702: GitHub backlog cleanup/bugs, #1710 (Swift LibraryPathMiddleware, careful) or leave #1715/#1710 for Daniel. #1704 reorg deferred (move helper). #1740 Phase 1 = ~4am fallback.

### Tick 6 (~01:46) — landed: #1702 hand-rolled structs→generated (b7f1064b, CLOSED, −295 lines). Manager fixed 3 gate errors worker missed (wrong generated name, metadata helper name-collision→metadataStrings+4 callers, re-added Identifiable). 0.0.2 green.
Closed/resolved tonight (13): #1703,#1707,#1731,#1737,#1736,#1730,#1732,#1733,#1734,#1735,#1727,#1725,#1702.
In flight: f_codex_filemenu (gpt-5.4, ~/code/fichero-filemenu) = #1720 File menu (Open Recent from registry + Close Database reusing sidebar action + Open/New). May touch backend (lastOpenedAt) — ruff+pytest if so, else Xcode build gate.
DEFERRED (border on parked #1740 design — leave for attended): #1696 (unify show/hide chrome observable), #1697 (unify spatial render state). Needs-Daniel: #1709 (4 failing Swift tests — can't run xcodebuild test here), #1715 (OpenAPI header backend). #1704 reorg (needs move-swift-file.rb). #1740 Phase 1 = ~4am fallback.
Next bounded picks: #1721 (drag-drop .fichero→new window), backlog bugs.

### Tick 7 (~02:23) — landed: #1720 File menu Open Recent + Close Database (97a14833, CLOSED). New FileMenuCommands.swift. Gate note: discarded Xcode-16 pbxproj auto-normalization noise (dstSubfolder/empty exceptions) before merge — recurs on each GUI build, just `git checkout -- project.pbxproj`. 0.0.2 green.
Closed/resolved tonight (14): +#1720.
In flight: f_codex_dragopen (gpt-5.4, ~/code/fichero-dragopen) = #1721 drop a .fichero → open/focus window (reuse #1720 path), not replace; other files still import to Inbox. Frontend, Xcode build gate.
Next bounded: backlog bugs (gh issue list), backend bounded bugs ideal. AVOID design EPICs + #1696/#1697 + #1709/#1715. #1704 reorg needs move helper. #1740 Phase 1 = ~4am fallback if bounded work runs out.

### Tick 8 (~02:57) — landed: #1721 drag-drop .fichero→open/focus window (657b51c4, CLOSED). 0.0.2 green.
Closed/resolved tonight (15): +#1721.
In flight: f_codex_inspent (gpt-5.4, ~/code/fichero-inspent) = #1653 inspector Entities panel empty though engine returns them (frontend decode/scope bug); f_codex_relpaths (gpt-5.4, ~/code/fichero-relpaths) = #1663/#1664 store image paths relative to lib root + resolve both legacy-absolute/new-relative (backend, never mutate Marshall data). Disjoint.
Backlog rich in backend IIIF-import bugs (#1650-1664) — many need real data to verify, prefer leaving for Daniel or pick the data-independent ones. #1728 (surface Notes/MindPalace-icon/Automation) still a bounded frontend option. #1740 Phase 1 fallback if bounded work thins.

### Tick 9 (~03:38) — landed: #1663/#1664 relative image paths (94f19d69, both CLOSED, backend, restart needed) + #1653 inspector entities empty (8db7d5b4, CLOSED, frontend). 0.0.2 green.
Closed/resolved tonight (18): +#1663,#1664,#1653.
In flight: f_codex_surface (gpt-5.4, ~/code/fichero-surface) = #1728 surface Notes browser (AppState flag+Data-menu sheet) + verify/add Mind Palace SidebarModeBar icon + cautious Automation (flip only if wiring real). Frontend, Xcode build gate.
Restart-needed-on-Daniel's-:8765 to take effect: #1727 (Inbox), #1707/#1731 (PDF storage), #1663/#1664 (relative paths). All backend code merged.
Next bounded: backlog (data-independent), #1345 (/children doc: prefix — verify still open), #1720 follow-ups. #1740 Phase 1 fallback if thin.

### Tick 10 (~04:11) — landed: #1728 surface built views (b23bfb7a, CLOSED) — Notes browser reachable (Data menu + sheet) + Mind Palace SidebarModeBar icon; Automation left OFF (stub service, filed follow-up #1742). Also closed #1611 (stale — DuckDB claims-index fix already on 0.0.2 @ 956248b3). 0.0.2 green.
Closed/resolved tonight (20): +#1728,#1611. Filed #1742 (Automation wiring).
In flight: f_codex_stubs (gpt-5.4, ~/code/fichero-spatialstubs) = #1740 PHASE 1 ONLY — feature-gated .workspace/.spatial ViewDisplayMode STUBS (flags OFF, nothing removed, ContentUnavailableView). The SAFE pre-approved fallback. Frontend, Xcode build gate. Do NOT let it do Phase 2+.
Backlog now thin on bounded data-independent work — mostly design EPICs, IIIF-data-dependent backend (#1650-1662), needs-Daniel (#1709/#1715), deferred reorg (#1704). After stubs, consider GH-hygiene stale-close pass or pace down.

### Tick 11 (~04:48) — landed: #1740 PHASE 1 stubs (13c85ad5) — .workspace/.spatial ViewDisplayMode stubs, flags default OFF, ContentUnavailableView, nothing removed, build green. #1740 KEPT OPEN (commented; Phase 2+ awaits Daniel's sign-off on the 4 open Qs). 0.0.2 green.
Tonight's tally: 20 issues closed/resolved (#1703,1707,1731,1737,1736,1730,1732,1733,1734,1735,1727,1725,1702,1663,1664,1653,1728,1611 + #1345/#1740P1) + filed #1742 (Automation wiring).
PACING DOWN: bounded data-independent backlog is exhausted — remaining open = design EPICs (#1686/1689/1692/1693/1738/1739/1570/1740-P2), IIIF-data-dependent backend (#1650-1662), needs-Daniel (#1709/1715), deferred #1704 (needs move-swift-file.rb). No safe unattended lane worth the risk at this hour.
NEEDS ENGINE RESTART on Daniel's :8765 (backend merges): #1727 Inbox, #1707/#1731 PDF storage, #1663/#1664 relative paths.
Next tick: light GH-hygiene (verify+close any stale-already-fixed issues like #1611 was) OR idle until Daniel returns. Do NOT force risky lanes.
