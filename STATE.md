## SESSION HANDOFF — 2026-06-11 ~10:55 (infra march + roadmap planned; continue Phase 1)
**0.0.2 @ `de7d35ed`, pushed, clean (no worktrees/lanes; tmux only `seed`). Engine restarted production-style on the new code (single process; model-cache verified: embedder loads 1×, not per-page).**

### docs/ROADMAP.md is now the authoritative 4-phase plan (READ IT FIRST)
**Everything filed into a milestone; work milestones properly, in order:**
1. **INFRASTRUCTURE (doing now)** — EPIC #2021 multi-user → **#2023 actor-from-session (NEXT)** → #2043 tamper-evident log → #2025 ambient-authority → #2024 ACL/sharing → #2048 bind → #2026 Tailscale; + #2045 SSE-hardening, #2046 backups, #1935 observable-one-path, #2055 client-reuse, **Trash #2075**.
2. **MAC-ASSED APP** — EPIC #2030 (shell #2031 → zoned toolbar #2032 → styling/#2041 Liquid Glass) + #2020/#2052/#2053/#2042.
3. **WORKFLOW & AI INFERENCE** — EPIC #2056 (batch #2057, profiles #2058, local-MLX #2066, scale #2062, Apple Vision #2060, image-edit backend #2061, local-only #2063).
4. **RESEARCHER/AI/AGENT** — EPIC #2067 (Workspace≡RAG-chat≡Agent; agent IS a principal; Pi #2071 on mlx-lm-server; reuses #2022/#2023/#2024/#2015 — no parallel agent system).
- **Cross-cutting PRIVACY GUARANTEE (#2063):** nothing goes online without explicit user consent; default-private; local-only setting + indicator.

### Shipped this session (Phase-1 infra):
- ✅ **#2050 model-cache** (embeddings/whisper/pykeen load once; reviewed) · ✅ **#2044 workers=1** · ✅ **#2051 Settings-crash** · ✅ **#2022 user-accounts BACKEND COMPLETE** (accounts.py scrypt + User/Session + /api/auth/* + owner admin + session middleware, behind `FICHERO_MULTIUSER` OFF, **security-reviewed APPROVE + hardened**). Commits through `de7d35ed`.

### Two things WAITING ON DANIEL:
- **#2049 embedding pooling** — pin `fastembed==0.5.1` (rec) vs re-embed real Marshall vectors. His call.
- Click-verify (docs/MORNING-TEST.md): Settings ⌘, opens (#2051); buttons+⌘Z; App Intents; Track-B; #2009/#1973.

### In flight when handing off: a background triage agent is assigning milestones to ~55 genuinely-orphaned OLD issues (#1666–#2006). (New issues #2020–#2075 already milestoned; gh issue list shows search-lag false-negatives — verify with `gh issue view`.) Check its result; finish any it flagged.

### NEXT CONCRETE STEP: dispatch **#2023** (derive ActionContext.actor from request.state.user — the seam exists: auth.py sets request.state.user; ~100 ActionContext call sites need to read it). Backend worker (codex), feature-flag-safe, full-suite + review gate. Then continue Phase 1 down the list.

### MANAGER MODE: workers implement, manager integrates + code-reviews. Worktrees only ~/code/fichero-worktrees; one Xcode build at a time; never push red; ≤1 pytest. codex weekly quota <10% (use claude lanes if codex dies). Daniel cleared the engine — manager MAY restart + run full suite.

---
## SESSION HANDOFF — 2026-06-11 ~08:50 (#1848 frontend remainder COMPLETE + Track B Phase 2 DONE)
**0.0.2 @ `d92c1c96`, pushed, clean (no worktrees/lanes; only tmux `seed`). All frontend lanes Xcode compile-verified green.**

### What's DONE (this morning, integrated + pushed):
- **fe-buttons (`0e88a506`)** — claim delete/patch, document delete, annotation delete, note delete/update buttons now route through `POST /api/actions/invoke` (audited + ⌘Z-undoable), same `ActionLibraryService.invokeAction` pattern as the merge exhibit. (Manager fixed 1 worker bug: missing `@EnvironmentObject windowState` on `InlineClaimEditor`.)
- **App Intents / Shortcuts `a8b7c1f1` — #2017 CLOSED** — `fichero/fichero/Intents/{FicheroActionIntents,FicheroShortcuts}.swift`: curated AppIntents (Merge Entities, Create Note, Delete Document, Run Workflow, Create Annotation) over /api/actions/invoke. (Manager fixed worker's Swift6 errors: `static let` metadata; `@Parameter` w/o wrappedValue; `Encodable & Sendable` generic; `[AppShortcut]` builder.)
- **Track B Phase 2 (`d92c1c96`) — #2010 + #2011 CLOSED** — annotations + notes as List + detachable detail: `FocusedAnnotation/FocusedNote`, `AnnotationListView/DetailView`, `NoteListView/DetailView`, `AnnotationsInspectorPane/NotesInspectorPane`, tear-off WindowGroups in FicheroApp.swift; `DocumentInspectorAnnotationsTab`/`DocumentNotesTab`/`NotesBrowserView` reworked in place. Copied the #2003/#2004/#2005 artifact pattern. Built green first try.
- MORNING-TEST.md updated with click-tests for all three.

### Workers were CODEX (gpt-5.4-mini, `--dangerously-bypass-approvals-and-sandbox` YOLO) in ~/code/fichero-worktrees/. codex weekly quota was <10% all morning but lanes completed. Manager runs the ONLY Xcode build (compile-only, tabIdentifier windowtab1) — that gate caught every Swift6 error the pytest-less/build-less workers couldn't.

### OPEN / NEXT:
- **openapi.json is STALE vs backend** (the live uvicorn regen shows `source_document_id` optional from #2019 + ~48 new endpoints). When the verify openapi-regen lands, **EntitySourceGroupsView.swift:181 + EntityDetailView+Biography.swift:87 need optional-unwrap fixes** (they break when the client regenerates the optional field). Surfaced, not yet committed (verify owns the regen).
- New backlog filed this morning (all `needs-design` where structural): **#2020** entity-panel provenance (List→Table "Found in"); **EPIC #2021** + #2022–#2029 multi-user/permissions/Tailscale/audits; **EPIC #2030** + #2031–#2041 Mac window structure (persistent shell + zoned toolbar) + Liquid Glass.

### AWAITING DANIEL (visual/runtime — docs/MORNING-TEST.md is the click-list):
converted delete/patch buttons + **⌘Z undo**; **App Intents in Shortcuts.app**; **Track B annotations/notes** list+detail+tear-off; plus prior: #2009 Interpretations live, #2003/4/5 Track B, #1973 beachball, #2006 frame-warning.

---
## SESSION HANDOFF — 2026-06-11 ~06:40 (#1848 backend DONE + frontend exhibit-A/⌘Z; frontend remainder queued)
**0.0.2 @ `ae4e7213`, pushed, clean (no worktrees/lanes). Full unit suite green (4478 passed; #2012 flake xfail-quarantined). Xcode compile-green.**

### What's DONE (this overnight run) — see [[one-audited-action-layer-shipped]]
- **#1848 one audited action layer — BACKEND COMPLETE.** #2013 keystone (registry+ActionAudit+`invoke` chokepoint) + #2014 sweep = **115 audited actions / 14 domains** (the ENTIRE engine write surface; each wraps the proven `*_impl`, iterate-not-replace). Every mutation → `registry.invoke` → snapshot before → execute → ActionAudit(actor/before/after) → emit_change. ~280 thorough tests. **#2013/#2014/#2015/#2016/#2018/#2019 CLOSED.**
  - #2015 undo: `POST /api/actions/audit/{id}/undo` applies any undoable action's inverse + `inverse_of` chain (redo/undo-of-undo) + `GET /api/actions/audit` log.
  - #2016 chat tools: `fichero/actions/chat_tools.py` → 109 tool defs from `registry.all()` + dispatcher + tests. (Live-agent wiring = #1847 follow-up; POST /api/chat has no tool-list yet.)
  - #2018: 5 missing actions (annotation duplicate/merge/relink, search reindex, workflow.run).
- **Frontend exhibit-A:** entity-merge button now calls `POST /api/actions/invoke {name:'entity.merge', params:EntityMergeRequest}` via new `ActionInvokeService.swift` + `LastAction{auditId}` holder. (merge bug structurally fixed.)
- **Frontend ⌘Z (#2015):** `FocusedCommandButtons.swift` + `ActionInvokeService.undoAction` — ⌘Z undoes the last audited action (single-level MVP; multi-level = follow-up).
- Also: manual claims (#2019, KnowledgeClaim.source_document_id optional); guardrail-scanner regex fix; #2012 flake quarantined (xfail).

### NEXT — open frontend work Daniel asked to do (no lanes running; dispatch fresh):
1. **Route the REST of the mutation buttons through `/api/actions/invoke`** (claim delete/patch, document delete, annotation delete, etc.) — same `ActionInvokeService.invokeAction` pattern as the merge button; capture audit_id into LastAction for ⌘Z.
2. **#2017 App Intents** — generate App Intents/Shortcuts for a CURATED set of high-value actions (merge, create note, run workflow, …) calling /api/actions/invoke (115 is too many to expose all).
3. **Track B #2010 annotations + #2011 notes** — copy the #2003 pattern (Focused<X>.shared + <X>ListView + <X>DetailView + <X>InspectorPane + tear-off WindowGroup) onto AnnotationStore/NoteStore (both already on the substrate). Pure UI, independent of the action layer.
Frontend gate = swiftlint + `mcp__xcode__BuildProject` COMPILE only (NEVER xcodebuild test — GUI windows). Register new .swift via `ruby scripts/add-swift-file.rb`. Log GUI checks to docs/MORNING-TEST.md.

### AWAITING DANIEL (visual/runtime — docs/MORNING-TEST.md is the click-list):
merge-still-works+audit (exhibit A); **⌘Z un-merges**; #2009 Interpretations live; #2003/#2004/#2005 Track B list+detail; #1973 beachball; #2006 frame-warning.

### Conventions (don't relearn): backend lane → worktree-test → cherry-pick → ruff → import-smoke → test_check_duplicate_paths.py (allowlist for renamed *_impl) → FULL `pytest -q -rf` (NEVER tail; grep ALL '^FAILED') → push. Workers can't run pytest → EXPECT their tests to fail first run, fix test-side as integrator. RAM: ≤1 pytest; kill stray worker pytest on fichero-worktrees paths. Worktrees only under ~/code/fichero-worktrees; `git worktree remove --force`; NEVER rm ~/code siblings. codex weekly quota low → claude lanes.

---
## SESSION HANDOFF — 2026-06-11 ~01:35 (#2014 DONE — entire engine write surface audited)
**0.0.2 @ `395532d3`, pushed, full suite green (4423 passed; #2012 flake xfail-quarantined).**

**#1848 steps 1-2 SHIPPED overnight.** #2013 keystone (registry+audit+invoke) + #2014 sweep = **109 audited actions across 14 domains** (claim16/provider11/ontology12/workflow10/biblio9/document8/batch8/imageedit7/annotation5/savedsearch6/conversation4/note4/import4/actionlib3 + entity.merge/unmerge). Every engine mutation → registry.invoke → ActionAudit(actor/before/after) → emit_change. ~280 thorough tests. #2014 CLOSED. See [[one-audited-action-layer-shipped]] + docs/architecture/action_layer.md.
Side wins: manual claims (#2019, KnowledgeClaim.source_document_id optional), guardrail scanner fixes, #2012 flake quarantined.

**IN FLIGHT (downstream #1848):** dn-undo (#2015 generalized undo + audit-log endpoint), dn-chat (#2016 chat tools from registry #1847), dn-missing (#2018 the 5 missing actions). Integrate via the proven method (worktree-test → cherry-pick → -rf gate).

**STILL FRONTEND/Daniel:** #2017 App Intents; #2015 ⌘Z UndoManager wiring; route UI buttons (merge first) through /api/actions/invoke; Track B #2003/#2004/#2005 visual, #2010/#2011; #2009 Interpretations live; #1973 beachball; #2006 frame-warning. docs/MORNING-TEST.md has the click-list.

---
# STATE.md — Fichero

## SESSION HANDOFF — 2026-06-10 ~7:33pm (#1848 KEYSTONE landed; domain sweep #2014 next)
**0.0.2 @ `68fe6e13`, pushed. Full suite green (the 2 fails were a test patching emit_change at the wrong target — fixed).**

**#1848 action layer — Daniel APPROVED, and said do it RIGHT: rewrite all 28 hand-rolled ops onto typed+audited actions, test-first.** Doc: docs/architecture/action_layer.md.

**#2013 keystone — DONE + closed.** `fichero/actions/` ActionRegistry + `@action` + `registry.invoke()` chokepoint (validate→execute→ActionAudit(db.save)→emit_change) + ActionAudit table (via _ensure_table, no migration) + POST /api/actions/invoke + GET /api/actions/registry + POST /api/actions/audit/{id}/undo. Pilot: **entity.merge + entity.unmerge WRAP the proven merge_entities_impl/undo_entity_operation_impl** (extracted from the route — not re-derived). **Registry API contract is pinned in the #2013 close comment — #2014 workers copy it verbatim.**
Manager fixes on integration: lazy emit_change import (module-load cycle); test patches emit_change at the source module.

**NEXT — #2014 domain sweep (test-first, one domain per worker):** merge already done → the **28 hand-rolled ops** (19 ArtifactServiceGenerated + 8 image-editing) onto typed+audited actions → then thread the ~67 typed ones through invoke. Each: capture behavior in a test first → refactor → stays green → assert effect + audit row. Then #2015 undo+⌘Z, #2016 chat tools, #2017 App Intents, #2018 the 5 missing actions.
**Daniel may want to review the registry API (in #2013 comment) before #2014 fans out — ASK before dispatching.**

**AWAITING DANIEL (visual/runtime):** #2009 Interpretations live-update; #2003/#2004/#2005 Track B UI; #1973 beachball; #2006 frame-warning. Flake #2012.

---
## SESSION HANDOFF — 2026-06-10 ~4:25pm (#2000 DONE; observable layer complete; #1848 next, plan-first)
**0.0.2 @ `60ebe739`, pushed, clean. Full suite 4074 passed / 1 flake (#2012).**

**#2000 hermeneutics-observable — DONE + closed.** SVO + metadata were already-observable facets (ClaimStore / DocumentStore). Hermeneutics is now a live observable domain: routes emit `interpretation.*` (#2008) + InterpretationStore on the substrate makes the Interpretations panel live-update (#2009 — **OPEN, awaits Daniel visual**). Bonus: closed the emit-coverage guardrail blind spot AND fixed a migration-induced scanner regression (the #1995 store migration switched Swift stores to singular `changeDomain`, dropping 6 domains from coverage; scanner regex now matches both shapes → 75→**87 routes**, 0 gaps).

**FLAKE caught:** the full suite showed 1 failure — `test_extract_all_mock_emits_workflow_change_events` — which **passes 3/3 in isolation** (intermittent KnowledgeEntity validation under full-suite ordering; NOT from this work). Filed **#2012**. Lesson: read the FULL summary line (`N passed, M failed`) before declaring green — I misread once and pushed early; verified after that it was a pre-existing flake, code is correct.

**Track B Phase 2 queued:** annotations #2010 + notes #2011 (same list+detachable-detail recipe).

**NEXT: #1848 (one audited action layer) — PLAN-FIRST (EPIC).** Daniel: do #2000 then #1848. Scope it (don't blind-dispatch): inventory mutating UI actions → action registry + audit record (actor/action/target/before/after/run_id, reuse provenance #1832) + undo-from-inverse + ⌘Z UndoManager → split into ordered sub-issues → post plan on #1848 → STOP for Daniel approval before coding. Undo pillar already added to #1848.

**AWAITING DANIEL (visual/runtime):** #2009 Interpretations live-update; #2003/#2004/#2005 Track B UI; #1973 beachball; #2006 frame-warning.

---
## SESSION HANDOFF — 2026-06-10 ~2:40pm (TRACK B PHASE 1 COMPLETE — list+detachable-detail UI)
**0.0.2 @ `1bb64ce0`, pushed, clean (no worktrees/lanes). Full Xcode build green.**

**Track B Phase 1 — DONE.** Artifacts (#2003), citations (#2004), references (#2005) all now use ONE pattern: a `Focused<Domain>.shared` selection holder (mirrors KGFocusState.shared) → `<Domain>ListView` (click selects) → `<Domain>DetailView` (reuses existing rendering) → `<Domain>InspectorPane`, plus a `WindowGroup`/`openWindow` **tear-off window** that follows selection (context-menu → Open in Window). Replaces the stacked-text-boxes presentation. Each fed by its live observable store (Artifact/Citation/Reference). All build-verified, swiftlint clean.
**Left OPEN — await Daniel's VISUAL check** (UI changes): #2003 #2004 #2005.

**Also this session:** observable infra fully done (substrate + 8 stores migrated + extraction emits); SSE endpoint tested (#test_changes_stream_endpoint — the one backend gap).

**NEXT OPTIONS for Daniel:** (1) **#2000** — fold SVO / hermeneutic-statement / metadata onto the same list+detachable-detail pattern (decide first-class-vs-shared). (2) **EPIC #1848 — one audited action layer** (the bigger infra lever; single typed mutation surface → who-changed-what/undo/agentic-chat; twin of the observable layer). (3) Observable seams: optimistic updates + X-Fichero-Origin-Window self-echo dedup; non-route db.save emit guard.
**AWAITING DANIEL (visual/runtime):** #2003/#2004/#2005 UI; #1973 beachball; #2006 frame-warning; #2007 guardrail-tests.

---
## SESSION HANDOFF — 2026-06-10 ~2:15pm (Track B artifacts landed; SSE tested; cite/ref in flight)
**0.0.2 @ `3e03e852` (+ cite/ref lane in flight). Full Xcode build green.**

- **#2003 artifacts List + detachable detail — LANDED** (`3e03e852`, build green). FocusedArtifact.shared (mirrors KGFocusState.shared) → ArtifactListView (click selects) + ArtifactDetailView (wraps existing ArtifactPanel render) + ArtifactsInspectorPane + a WindowGroup tear-off scene (context-menu Open in Window, default follow-selection). Replaces stacked text boxes. **Left OPEN — awaits Daniel's visual check.**
- **SSE endpoint tested — LANDED** (`7925502c`): test_changes_stream_endpoint.py covers open-frame/delivery/scoping/unsubscribe-on-disconnect (4 pass, keepalive skipped — needs a route timeout seam, low priority). The one untested piece of the observable backend; rest was already covered.
- **IN FLIGHT:** #2004 citations + #2005 references — claude lane `trackb-cite-ref`, copying the #2003 FocusedItem+List+Detail+Pane+window pattern onto CitationStore/ReferenceStore.

**AWAITING DANIEL (visual):** #2003 artifacts UI; also #1973 beachball, #2006 frame-warning, #2007 guardrail-tests.

---
## SESSION HANDOFF — 2026-06-10 ~1:55pm (observable infra DONE; Track B UI started)
**0.0.2 @ `bff9f19d` (+ Track B in flight). Full Xcode build green.**

**Observable Data Layer infra — FULLY DONE:** substrate (ObservableDomainStore+ReloadDebouncer) + DocumentStore consumer + extraction emits (all 6 domains) + Artifact/Citation/Reference stores + **8 legacy stores migrated** onto the substrate (`bff9f19d`: 6 migrated −84 lines; SearchStore/WorkflowStore correctly left — they have no reload()/debounce). Backend: 0 emit gaps, 75/75 routes. Daniel: "backend is all done."

**TRACK B STARTED (front-end of the new infra) — the "mac-assed" detail UI (EPIC #2002):**
- IN FLIGHT: #2003 artifacts as List + detachable detail window (replaces stacked-text-boxes ArtifactPanel), on ArtifactStore. claude lane `trackb-artifacts`. Design: list → click selects → detail in popover that tears off into a draggable Window following selection (default follow, optional pin).
- NEXT: #2004 citations, #2005 references reuse the same pattern once #2003 proves it.

**NEXT INFRA (after Track B, my recommendation order):** (1) **One audited action layer (EPIC #1848)** — the missing twin of the observable layer (single typed mutation surface → who-changed-what/undo/agentic-chat). (2) Observable seams: optimistic updates + X-Fichero-Origin-Window self-echo dedup; non-route db.save emit guard (#1994 follow-up). (3) Test-coverage waves to drain #82. (4) route-sig→Swift-wrapper guard (we hit createNode + emit_change kwargs this session).

**AWAITING DANIEL:** #1973 beachball retest; #2006 frame-warning; #2007 guardrail-test follow-up.

---
## SESSION HANDOFF — 2026-06-10 ~1:05pm (TRACK A PHASE 1 COMPLETE — observable substrate)
**0.0.2 @ `0c4f1231` (pushed, clean — no worktrees/lanes). Full Xcode build green.**

**Track A (Observable Data Layer infra) Phase 1 — DONE:**
- **Substrate** `ObservableDomainStore` (protocol) + `ReloadDebouncer` (300ms) — shared change-stream boilerplate written once; concrete stores supply changeDomain/reload()/granular apply(). #1995. (Sendable-constrained for the Swift-6 debounce closure.)
- **DocumentStore** is the first consumer (granular splice-by-id; `DocumentStore+ChangeStream.swift`); registered in LibraryManager → **library table refreshes live**. #1996.
- **Extraction emits** per-document: document/entity/claim (#1994) + **artifact/citation/reference** on routes AND extraction (#1997/1998/1999, backend). `emit_change`/`ChangeEvent` extended with artifact_ids/citation_ids/reference_ids.
- **Frontend stores** ArtifactStore/CitationStore/ReferenceStore on the substrate; Citation + Reference inspector views live-wired. Artifact-view migration deferred to Track B (the stacked-boxes→list/detail redesign).
- **Guardrail-script tests** landed (9 pass, 6 skipped → #2007 to make the scripts path-injectable).

**REGRESSION LESSON (important):** the backend emit lane passed its 41 targeted change_stream tests but the FULL suite caught 15 failures it missed (emit_change rejected the new *_ids kwargs → TypeError broke artifact/citation/reference routes; + extraction tests needed expectation updates for the new document.updated/artifact.created emits). **After any route-signature/emit_change change, the full unit suite is the real gate — targeted tests miss cross-file breaks.** All fixed; last full run was 4050 passed / 1 failed, that 1 (test_mock_provider) fixed + verified green.

**NEXT (Track B — when Daniel's back):** the "mac-assed" list + **detachable popover↔window detail** UI (follows selection, draggable) — EPIC #2002; replace stacked-text-box ArtifactPanel (#2003), citations (#2004), references (#2005). Then migrate the 8 existing stores onto the substrate (de-risked follow-up). **Awaiting Daniel:** #1973 beachball runtime-retest; #2006 ContentView frame-warning; #2007 guardrail-test follow-up.

---
## SESSION HANDOFF — 2026-06-10 ~9:55am (OBSERVABLES COMPLETE + RAM-rule fix)
**0.0.2 @ `49fe12fe` (pushed, clean). Observable data layer fully wired end-to-end.**

**OBSERVABLES DONE:**
- Routes: 75/75 emit (guardrail 0 gaps; 2 compute-only POSTs permanently exempt).
- **Extraction path now emits** (#1994, `b777c795`): per-document coalesced `entity.updated`/`claim.updated` (actor=workflow) via new `workflows/tools/_workflow_change_emit.py` (best-effort try/except, `library_path=db.path.parent`, deduped ids). `_entity_writer` write/commit ordering UNTOUCHED. 2 new tests, 9 passed serially. Pure backend-internal — no routes/openapi/Swift.
- Frontend: change-stream debounce **300ms** (was 150) so extraction bursts coalesce to ~one refresh/300ms; createNode library-path regression fixed; full Xcode build green.

**RAM INCIDENT + FIX (important):** a gpt-5.4 worker ran **3 parallel background pytest** (~15GB) — the skills were telling workers to run pytest, contradicting the RAM rule. Killed the pytest PIDs, fixed **dispatch-worker + test-writer + session-start-worker skills** (fichero-skills `0bf7909`): workers NEVER run pytest, only cheap stdlib guards; MANAGER runs the suite SERIALLY (one pytest at a time). Memory `workers-write-tests-manager-runs-them` reinforced with the incident + kill-recovery.

**NEXT:** #1973 beachball — Daniel runtime-retest (click-storm during a workflow run; now extraction actually emits, so this is a real test of both the debounce AND live KG refresh). Then drain the 12 Test Coverage (#82) issues via /test-writer waves (manager runs pytest serially).

---
## SESSION HANDOFF — 2026-06-10 ~9:05am (observables CLOSED on routes + completeness audit)
**0.0.2 @ `ec8fd97c` (pushed, clean). emit-change guardrail: 0 gaps, 75/75 routes covered.**

**LANDED:** final store-backed emit coverage (`eaf2d76c`+`1f42877a`) — workflows.py CRUD + note-link/checklist emit. Guardrail closed to **0 gaps**; `estimate_workflow_cost` + `get_tool_prompt` marked **permanently EXEMPT** (compute-only POSTs, `check_emit_change_coverage.py` now has an EXEMPT set distinct from KNOWN_GAPS).

**OBSERVABLES COMPLETENESS AUDIT (done):**
- ✅ Every Swift store domain (action/annotation/claim/entity/note/research/document/workflow) has a backend emitter; every emitted type maps to a consuming store — no orphans either direction. Verb parity OK.
- ❌ **ONE gap found → #1994 (filed):** `emit_change` is ONLY in `api/routes/`. The **workflow execution path** (`_entity_writer.upsert_entity`/`save_claim`, extract_all, extract_entities_only, citations_extract, merge_dedup_only, import_artifacts, db_writer) writes entities/claims/documents during a run and **never emits** → open windows don't refresh after extraction until manual reload. This is the last piece of #1935 (the consistency rule holds for UI/CLI edits but not the extractor — the biggest producer). Confirmed unmitigated (no run-complete resync). **Higher risk: hot path, god-node-adjacent (#1121 race history) — needs a scoped lane + verify, NOT a blind dispatch.** Recommended emit boundary: one coalesced `entity.updated`/`claim.updated` per document-extraction completion (frontend debounce coalesces); `library_path = db.path.parent`.
- Follow-up idea (in #1994): the emit-coverage guardrail only sees @router handlers — a future guard could flag non-route `db.save` of KnowledgeEntity/KnowledgeClaim outside an emit.

**NEXT:** decide #1994 (extractor emit) — recommend dispatching a careful codex lane at the document-completion boundary. Beachball #1973 still awaits Daniel runtime-retest.

---
## SESSION HANDOFF — 2026-06-10 ~8:55am (test-writer wave + beachball + observables)
**0.0.2 @ `8247e948` (pushed, clean — no worktrees/lanes). Xcode BuildProject GREEN.**

**LANDED (codex+claude lanes, manager-gated, pushed):**
- **#1973 beachball FIXED** (`7d221a38`) — root cause: every change-stream event ran a wholesale store reload (full List re-render) on the main actor; a workflow-run event burst stacked ~100 reloads → main thread saturated → spinning cursor on click. Fix: `apply()` bumps the observation token instantly + a 150ms-debounced `scheduleReload()` coalesces bursts to ~1 reload (6 stores). Full Xcode BuildProject passed. **Labeled `ready-for-test` — Daniel must runtime-retest (click-storm during a workflow run) before close; NOT auto-closed.**
- **Observable emit coverage finished for document/entity/claim** (`362c533f`) — 16 more mutating routes emit; guardrail now **59/75 routes covered** (16 known gaps left = workflows.py [own stream] + note sub-resources). OpenAPI regen'd.
- **Test-writer wave 1** (`eb168bb0`) — drained #1984 kg + #1985 loaders + #1980 bibliography (43 new real-assertion tests, all pass, vacuous-guard green); those 3 modules now have **0 untested symbols**; issues closed.
- **Coverage backlog #82 seeded + scanner hardened** — 12 open `[Test Coverage]` issues remain (~3076 untested symbols, swift/Views biggest at 963). Fixed scanner bugs along the way: excl generated code, milestone-by-title, body cap, issue-URL number parse + edit guard, ratchets drained modules.

**NEXT — START HERE:**
1. Daniel: runtime-retest **#1973** (beachball) — click rapidly while a workflow runs; confirm no spinning cursor. Close if clean.
2. Next test-writer waves drain the 12 open #82 issues (biggest value: swift/Views 963, swift/Services, python/api 482, python/workflows 175). Dispatch `/test-writer` lanes; Swift tests are compile-only + batched runs.
3. Remaining emit gaps (optional): workflows.py CRUD (has its own stream) + note link/checklist sub-resources — low value, left in ratchet.

---
## SESSION HANDOFF — 2026-06-10 ~8:10am (test-infra + observable backend)
**0.0.2 @ `ea4b62b1` (pushed, clean — no worktrees/lanes). fichero-skills main @ `e4acd08` (pushed).**

**LANDED (all codex-worker, manager-gated, pushed):**
- **Observable backend emit coverage** — `emit_change` now broadcasts on **43/75** mutating routes (was 34). #1975 action+research (`7b33c1d0`), #1974 annotation+note (`cd237874`); both regen'd OpenAPI. #1976 ratcheting emit-coverage guardrail `scripts/check_emit_change_coverage.py` (`7ba1e281`, in verify_all).
- **Test infrastructure** (`ea4b62b1` + skills): `scripts/check_test_assertions.py` — vacuous-test guard (49 known-vacuous seeded, 3537 asserting; auto-runs in verify_all via the `check_*.py` glob). `scripts/scan_test_coverage_gaps.py` — backlog generator (dry-run: **2174 py + 2146 swift untested symbols**; `--file-issues` files into **"Test Coverage" milestone #82** under `type:test`, ratcheting baseline; manager-run, NOT in verify). New **`/test-writer` skill** (two-pass author+adversarial, pytest runs / Swift compile-only) + pipeline wired into dispatch-worker/session-start-worker/session-start-manager skills. Docs: `VERIFY.md`, `agent-workflow/parallel-execution.md`.

**THE TEST LOOP (now documented in skills):** IMPLEMENT (spark, author writes happy-path tests) → CODE REVIEW (`/code-review`, codex 5.4 — DIFFERENT model than author) → FIX → TEST-EXPAND (`/test-writer` adversarial pass) → TEST-SANITY (`check_test_assertions.py`) → MANAGER GATE (pytest always; Swift compile-only + batched runs). Test debt is tracked as the #82 backlog, NOT a merge blocker (drain with a 2nd worker wave).

**NEXT — START HERE:**
1. Run `python3 scripts/scan_test_coverage_gaps.py --file-issues` to seed the Test Coverage backlog (#82), then dispatch a worker wave to drain it via `/test-writer`.
2. **#1973 beachball** (spinning cursor on click) still OPEN — frontend: a change-stream consumer's `apply()` blocking the main actor. Needs a `claude` frontend lane (audit every `ChangeEventConsumer.apply` for sync I/O / full reloads; make O(1) in-place, defer refetch to a Task).
3. #1935 Observable Data Layer (shared renderer per domain type) still open — broad SwiftUI, plan before dispatch.

**DISPATCH GOTCHA (codex):** a multi-line brief paste leaves codex in composer mode — the SAME-call trailing `Enter` is absorbed as a newline. Send a SEPARATE bare `Enter` to submit; capture-pane to confirm `• Working`. Also: a long lane can exhaust codex's context before committing — the work is on disk; commit from the manager shell and cherry-pick.

---
## SESSION-END HANDOFF — 2026-06-10 ~6:45am (for incoming manager)
**0.0.2 @ `5e2f2064` + this handoff commit (pushed after session-end). Tree clean except `.session-end-complete` during wrap-up. No active worker worktrees/lanes.**

**LANDED THIS SESSION (all pushed to `0.0.2`):** #1924 choose-next selector skill (`701b990e`) · #1921 OpenAPI client parity guardrail (`742da854`) · #1851 DocumentStore `ObservableObject`→`@Observable` + typed environment across 16 consumers (`f121533b`, Daniel BuildProject pass) · #1967 WorkflowExecutionObserver propagation into presented sheets/popovers (`015ce6d6`) · #1919 gardener helper (`5e2f2064`) · future feature #1972 filed (image keywords, ratings, thumbs up/down).

**VERIFY BASELINE:** Daniel reported Xcode BuildProject passed after #1851. Manager focused checks passed for each integrated lane. Final `python3 scripts/gardener.py --tier standard --json` ran the standard gate through `verify_all (standard): ALL PASS`; backend unit suite result was `3979 passed, 21 skipped, 21 xfailed` in 10:31. Swift/tooling guardrails also passed. Gardener surfaced stale baseline cleanup opportunities: 59 no-emoji known entries clean, 3 observer known entries clean, 111 UI-wiring allowlist entries clean, and 3 endpoint-usage known gaps clean.

**CURRENT FOCUS:** Roadmap Tier 2 / Observable Data Layer remains the priority. #1935 is the main open Observable Data Layer issue: single code path per endpoint/store + one shared renderer per domain type. Treat it as broad/high-blast SwiftUI work; dispatch only after a scoped plan/file partition.

**OPEN UI / RUNTIME TO RE-TEST:** #1963 library click/marquee select and #1964 Info tab may be fixed by the DocumentStore migration; Daniel should runtime-test before closing. Still open: #1962 selection-everywhere EPIC · #1965 artifacts→List/editor · #1966 duplicate EntityLozenge IDs · #1968 tabs-between-sidebars · #1969 semantic fonts · #1970 Source Annotations click/full-size · #1971 standard controls · #1972 future image keyword/rating curation.

**NEXT SESSION — START HERE:**
1. Confirm repo is clean and no worktrees are active: `git status --short --branch && git worktree list`.
2. Run `python3 scripts/gardener.py --tier standard` or `python3 scripts/choose_next.py --json` to pick the next roadmap slice.
3. Runtime-test #1963/#1964 against the integrated DocumentStore migration; close if fixed, otherwise file/dispatch a narrow follow-up.
4. Plan #1935 before coding; split by domain renderer/store surface to avoid overlapping SwiftUI files.
5. Keep worker policy: tmux + external `~/code/fichero-worktrees/<name>`, Spark first, jcodemunch first, manager verifies before integrate.

---
### (archived)
## SESSION-END HANDOFF — 2026-06-09 ~4:10pm (for incoming CODEX manager)
**0.0.2 @ `9955e0a0` (pushed, clean — no worktrees, no lanes running).** All implementation = codex; manager gates (Xcode FULL build / pytest / run-script) before cherry-pick.

**LANDED today (verified+pushed):** #1948 line-insensitive guardrail keys · #1957 doc:-prefix+skip-unresolvable (404 fix) · #1917/#1958 versioned thumbnail cache+perf_span · #1911 WorkflowStore→@Observable+change-stream · #1925 4 completeness-matrix guardrails (endpoint×{store,cli}, undo, CRUD, action-surface) · #289/#1398 transcription-fidelity prompts (preserve uncertainty/diacritics/illegible markers) · #1960 Source Annotations→native List · #1961 granular in-place EntityStore updates (no wholesale rerender) · #1851 observer-pattern audit guardrail (115 legacy files seeded, RATCHETS down) · pruned 50 stale orphan branches → check_unmerged_work green.

**NEXT KEYSTONE (brief saved /tmp/documentstore-observable.txt):** DocumentStore ObservableObject→@Observable + @Environment (god-node, 16 consumers). Stalled this session on a codex 'Update available!' prompt — produced nothing, deferred clean. Template = WorkflowStore migration (already in codebase). Gotchas: @ObservationIgnored on lazy/service/cancellables props; SidebarObservers `.$collections.sink`→re-arming `observeDocumentStore` (mirror observeWorkflowStore); `$documentStore` bindings→@Bindable; LibraryWindow:47 .environmentObject→.environment. LIKELY FIXES #1964 (Info tab not loading — it uses @EnvironmentObject documentStore) + #1963 (library can't select). Then grind the rest of the observer sweep store-by-store (serial — shared registry); guardrail scripts/check_observer_pattern.py tracks the 115.

**OPEN BUGS FROM RUNTIME TESTING (filed):** #1967 CRASH (WorkflowExecutionObserver @Environment not propagated into sheets/popovers — audit all presented views; URGENT) · #1964 Info tab not loading · #1963 library click+marquee select · #1961 entities single-click (granular fix landed; re-test — if still dead it's the row .simultaneousGesture count:2 swallowing taps) · #1966 ForEach dup-ID (EntityLozenge keys on name) · #1970 Source Annotations single-click+full-size.

**NEW HARD RULES (memory):** `no-wholesale-list-rerender` (mutate one item in place, never full-reload on single edit; stable identity; no gestures fighting List(selection:)) · `semantic-system-fonts` (all text = semantic macOS styles .title/.headline/.body…, NO .system(size:); scales with system text size; standard controls; List-vs-Table per fit; tabs between sidebars Xcode-style).

**DIRECTION EPICs:** #1962 Finder-style selection everywhere (single-click select+multi+marquee, double-click/Enter opens) · #1969 semantic fonts everywhere · #1971 standard-controls audit (icon/list/table) · #1965 artifacts→List+editor+batch-delete · #1968 tabs between sidebars · #1851 observer sweep.

**📋 READY FOR DANIEL TO TEST:** #1943 artifacts · #1953 thumbnails · #1960 Source Annotations List · #1961 entities granular updates (re-test single-click).

---
### (archived earlier handoffs)
## RESET HANDOFF — 2026-06-09 ~2:35pm (CODEX-ONLY; grind mode)
**0.0.2 @ `5976191b` (pushed).** Manager runs lean; ALL implementation is codex.
**LANDED since 2:15pm:** #1925 action-surface matrix guardrail · #289/#1398 transcription-fidelity re-apply (preserve uncertainty/diacritics/illegible markers, 108 tests green) · #1960 Source Annotations → native List (FULL build green).
**RUNTIME FINDINGS (Daniel testing #1943):** entities-list click/select unreliable = WHOLE-LIST RE-RENDER on every edit — root-caused: EntityStore rename/setCuration/merge/delete all `await reload()` (replaces whole array → rebuilds rows → resets selection). Fix in flight (fe/entity-granular-update #1961: granular in-place updates). NEW HARD RULE in memory `no-wholesale-list-rerender`.
**OBSERVER SWEEP (Daniel: 'review all views for observer pattern'):** audit of 343 views: 76 @EnvironmentObject, 33 LibraryManager-direct, 28 .environmentObject, 11 @StateObject=Service(), 8 client.api-in-view, 7 ObservableObject view-models, 2 Combine $publisher. Grinding down store-by-store (serial — shared registry). Building ratcheting guardrail now.
**IN FLIGHT:** tmux fichero-workers:entity-granular (#1961 click fix, ~/code/fichero-worktrees/entity-granular) + :observer-guardrail (scripts/ ratchet #1851, ~/code/fichero-worktrees/observer-guardrail).
**READY FOR DANIEL TO TEST:** #1943 artifacts · #1953 thumbnails · #1960 Source Annotations List · #1961 entities-click (after it lands).
---
### (prior handoff 2:15pm)
## RESET HANDOFF — 2026-06-09 ~2:15pm (CODEX-ONLY; Claude weekly budget low)
**0.0.2 @ `a361fa9a` (pushed).** Manager runs lean; ALL implementation is codex.
**LANDED since 1:20pm:** #1911 WorkflowStore ObservableObject→@Observable + change-stream + 14 consumers + 2 views (FULL Xcode build green; fixed 2 codex misses: @ObservationIgnored lazy service, SidebarObservers `$workflows`→withObservationTracking) · #1925 3 completeness-matrix guardrails (endpoint×{store,cli}, undo, CRUD) · pruned 49 stale orphan worktree-agent/* branches.
**ORPHAN BRANCH NEEDS DANIEL:** `codex/1386-transcription-prompt-quality` (May 31) — 11 commits already shipped (image tools), 12 unmerged = transcription-FIDELITY (#289/#1386/#1387/#1388/#1398: preserve diacritics/uncertainty/illegible markers + quality-gate marker count). RELEVANT to archival transcription. NOT cherry-picked (predates #1802 multi-provider prompts → would conflict) — being RE-APPLIED fresh in lane be/transcription-fidelity.
**IN FLIGHT (2 disjoint lanes):** tmux fichero-workers:transcription (be/transcription-fidelity, engine prompts) + :action-matrix (tooling/action-completeness, scripts/ — action×{menu,context,toolbar,keyboard} matrix #1925).
---
### (prior handoff 1:20pm)
**INTEGRATED this turn (worktrees removed, branches deleted, issues closed):**
- #1948 line-insensitive guardrail keys (content-signature hashes) — `425a96f5`
- #1957 doc:-prefix tolerance + skip-unresolvable-children (404 thrash fix) — `fae19cea`
- #1917/#1958 versioned thumbnail cache + perf_span instrumentation — `68a38752` (hand-merged 3 conflicting fns: list_documents/get_children/get_thumbnail wrapped doc-notfound's logic in perf_span)
**LESSON (Daniel's Q):** profiling + doc-notfound BOTH touched documents.py/storage.py → cherry-pick conflicts I had to hand-resolve with Opus tokens. **Rule: parallelize across DISJOINT file-sets/milestones; serialize lanes that share files.** line-insensitive (tooling-only) merged clean; the two backend lanes did not.
**WORKER PATTERN (memory `parallel-worker-orchestration`):** codex via **tmux + send-keys + Enter** (NOT `codex exec` — flaky); persistent per-milestone, resume via send-keys; **NEVER broad-`pkill codex`** (kills Daniel's own windows); external worktrees only.
**📋 READY FOR DANIEL TO TEST:** #1943 (artifacts list/save + batch) · #1953 (thumbnails — may need cache clear).
**NEXT:** roadmap tier order — Tier 0 ratchets (guardrails→0), Tier 4 Mac polish (#1950 multi-select, #1951 status/selection color, #1952 glass sidebars), Tier 6 profiling. Wake-loop ~30-40min to conserve Claude.



## 2026-06-08 (overnight) — autonomous Mac-assed run (Claude in charge)

**Mode:** Daniel out for the night; I run the loop — dispatch worker batches (claude=frontend, codex-style=backend), build/test-verify each, integrate, dispatch next. Workers in their own worktrees; I build via Xcode MCP + run heavy pytest (one heavy backend lane at a time).

**Landed tonight (each manager-verified — build/test/lint green — pushed to 0.0.2):**
- `071c9042` inspector tabs → native List + two-step attributes; `3c77cb9f` single-click-select/double-click-open + 2 review HIGHs
- `8bde477c` backend `list_entities` doc-scoped hot path 316→45ms (~7×, `query_in` parameterized IN)
- `5e5b708a` EntityDetailView modernize (native List, no emoji, hide raw hash, Liquid Glass, split) + in-place rename
- `1d3ac1ee` URLSession/print cleanup (DocumentPicker OSLog; LocalModels/WorkspaceItem already migrated)
- `f9e7a85a` entity dedup #1811 — accent-fold + normalized-key short-circuit (Pena/Peña, San Pablo/San Pabloo)
- Decisions in `appkit_interop.md`: List-vs-Table, no swipe, edit-via-navigation; `SWIFTUI_PRINCIPLES.md`: Observation-first + data-layer; audit doc `mac_assed_audit_2026.md`.
- **Closed:** #1811 #1849 #1853 #1860 #1864 #1865 #1877 #1879 #1880. **Filed:** audit #1875 (+29: #1877–1905), guardrails #1876, features #1867–1874, over-merge #1907, +EPICs.

**Hard design rules (in `appkit_interop.md` / `SWIFTUI_PRINCIPLES.md`):**
- Inspector items = `List` (multi-select, hierarchy, drag-reorder); `Table` only for the multi-column library browser. AppKit NSOutlineView only if List can't reach.
- **No swipe actions** (not Mac) → context menu + toolbar + keyboard.
- **Editing is navigation, not modal** — inline rename / push-detail-with-Back, never sheets.
- Single-click select, double-click open everywhere.
- Existing view-local `ObservableObject` → `@Observable` IS in scope; god-objects staged.
- Golden Gate only; no `if #available`.

**~14 batches landed by ~11pm (all build/test-verified):** swipe-removal, embedding over-merge gate, native-List/No-Selection (Activity/AIProviders/MCP/KG-viz), native-List/Grid (FilesNode/OutputLog/ModelComparison/Agents), **the observable data-layer keystone** — spec `observable_data_layer.md`, backend change-stream shell (`/api/changes/stream` + emit on entities/claims/documents), and `EntityStore`+`LibraryChangeStream` with the inspector migrated to observe it (multi-window merge/rename refresh), db-access guardrail (#1876 backend). Caught + fixed one broken integration (guardrail false-positive on generated code) — nothing broken left on 0.0.2.

**Process notes:** jcodemunch index is STALE — workers verify-by-reading-disk; workers must run pytest from their WORKTREE (not the main venv — that scans a stale tree). Manager build/test-verifies every batch before integrating.

**Session ended ~6:45am 2026-06-09 (context full → compact).** ~16 batches landed + verified on `0.0.2` (tip `81ddf8dd`). Both guardrails enforce (#1876 closed). Worker model: **parallel** agents in isolated worktrees (Opus/Sonnet via Agent tool; **codex via `codex -C <worktree> exec --full-auto "<prompt>"`** for backend; run several at once, merge each back) → manager build/test-verifies → cherry-picks to 0.0.2 → cleans worktree. **Give each worker 3–10 RELATED issues** (so they use their full context), then review — don't dribble 1 issue at a time.

**IN FLIGHT (integrate FIRST next session):** a **codex** worker on **#1909** (db.conn→typed db.py sweep) in worktree `.claude/worktrees/codex-1909`, branch `codex/db-conn-1909`, log `/tmp/codex-1909.log`. When done: review its diff, run `pytest test_db_access_guardrail.py + route tests`, `ruff`, cherry-pick to 0.0.2, remove the worktree.

**Next queued (data-layer order from the spec `observable_data_layer.md`):** **ClaimStore** (mirror EntityStore, subscribe to `claim.*` events) → then **retire the NotificationCenter bus** (#1862) once ClaimStore + EntityDetailView are migrated; EntityStore document-keyed buckets for multi-window (#1908); migrate the remaining `@StateObject service` views (the frontend guardrail's 17 KNOWN_VIOLATIONS) to stores; then claim dedup #1805, e5 prefixes #1795 (needs re-embed), undo #1832, citations tab #1850, feature set #1867-1874.

**Hard rules for next session:** build/test-verify EVERY worker batch before integrating (caught 2 broken integrations tonight); workers run pytest from THEIR worktree (not main venv — scans stale tree); jcodemunch index is STALE so verify-by-reading-disk; never run `xcodebuild test`/`verify_all.sh` on Daniel's machine (use Xcode MCP `BuildProject` + `swiftlint`); no swipe / no modal-edit / List-not-Table / single-click-select-double-click-open.

**Source-of-truth EPICs:** #1859 (Mac-assed/2026 audit S1–S9), #1838 (Mac-assed), #1851 (observers-everywhere), #1863 (backend change-stream, multi-window), #1832 (undo). Audit doc: `docs/architecture/swiftui/mac_assed_audit_2026.md`.

**Next batches queued:** S1 local-path fixes (#1860/#1861), S2 NotificationCenter→@Observable (#1862), S3 @Observable migrations, citations tab (#1850), No-Selection chrome (#1854), horizontal layout (#1856), observers wiring (#1851/#1857), then undo (#1832).

---

## 2026-06-08 (PM) — Demo + multi-provider extraction session

**Branch:** `0.0.2` at `c29fa52f`, pushed.

### This Week's Focus
Marshall import QUALITY + multi-provider extraction + search/embedding quality. Demo to Andy **landed** today on the 20-page English `Marshall20Entities` library.

### Just Landed
- **Multi-provider extraction FIXED + merged** (`c29fa52f`, full unit suite green 3921 passed): OpenAI (function_calling, recommended default), OpenRouter (httpx hook strips `parallel_tool_calls`/`disable_parallel_tool_use` → both OpenAI + Bedrock-Claude routes), Apple (`include_schema_in_prompt` — no more empty `{}`). Closed #1802/#1821/#1822/#1823.
- Earlier today: `f607c7d6` extraction schema fixes (verb/object optional, strict=False, thin-kept), `#1799` fail-fast, demo UI fixes (tab order, sidebar, Delete, blank-image, timeline+map, entity-detail mentions).

### Blocked / Watch
- Search results unimpressive → e5 prefixes missing (#1795), whole-page embedding (#1833), no KG-fusion ranking (#1824).
- Entity dedup is the top visible KG-quality gap (#1811, Daniel raised 3×).

### Product target (decided 2026-06-08, post-WWDC26)
- **macOS 26 "Golden Gate" ONLY** (Apple-Silicon), no back-deployment. **Target release ≈ Sept 1, 2026.**
- **Adopt the 2026 Apple stack freely** as the Mac-assed foundation: SwiftUI 2026 (List/Grid/Section reordering, swipe-on-any-view, toolbar visibility-priority/auto-minimizing, AsyncImage caching, lazy `@State` Observable), "Use SwiftUI with AppKit" interop (NSHostingView+Observation+gestures) for the fidelity bridges, swift-collections (OrderedSet/Dict), Xcode 27 Instruments for profiling (#1815), Foundation Models 2026 + Core AI for on-device extraction (#1836). Decision: `docs/architecture/swiftui/appkit_interop.md` (2026 addendum). Memory: `golden-gate-only-target-sept-2026`.

### Operating model (changed 2026-06-08)
- **Dated releases, no versions.** No 0.0.3, no per-version branch/worktree, no two-ahead gate. Work the current branch; cut a dated release when ready.
- **One milestone at a time:** groom it (issues all there + complete) → work to done → next. Features are NOT release-gated; the active lane is whatever milestone is in focus.
- **Lean execution:** ONE heavy lane at a time; **workers WRITE tests, only the manager RUNS them** (15GB RAM spike lesson; one engine on :8765).

### Next Session — Start Here
1. **First milestone in focus: Mac-assed / Window Chrome & Toolbars** (EPIC #1838, decision doc `docs/architecture/swiftui/appkit_interop.md`). Groom it, then start with the document-inspector fidelity pass (#1839) — which is also where the merge-action gets wired correctly.
2. **Cross-cutting enabler — one audited action layer** (EPIC filed today): every app capability = a typed backend action exposed once, called by UI buttons + chat agent (#1847) + App Intents (#1837) + UI-action tests, and **audit-logged (who/when/how)**. This answers the "how do we know a UI element works" + "who changed what" threads together.
3. **Live bug:** entity merge does nothing in the UI (filed today). Prime suspects: `additionalProperties` footgun in the Swift merge request, or list-not-refreshing post-merge. Two endpoints (`kg_entity_curation` live, `entities.py` dead dup) + two UI surfaces — collapse to one.
4. **Reliability thread still matters** for GHG scale (60k/800 folders): #72 import bulletproofing + #1815 profiling; run Apple on Daniel's book to confirm the merged multi-provider fix.
5. Roadmap issues **#1774–#1847**. Handoff memory: `session-handoff-2026-06-08-providers-and-search`.

---
(Older session logs archived to HISTORY.md)
