# Reality Check: KG & Hermeneutics Milestone — Open Issues Audit
*Generated: 2026-05-31 | Read-only analysis: no tests run, no code changed*

---

## TL;DR Counts

| Verdict | Count | Issues |
|---|---|---|
| DONE — safe to close | 5 | #495, #496, #497, #498, #721, #922* |
| PARTIAL — close with caveat | 3 | #916, #1333, #900/#903 |
| OPEN — real remaining work | 13 | #499, #500, #501, #372, #373, #375, #917, #918, #1187, #1124, #753 (plus two more below) |

*\#922 is a decision doc — it exists to get Daniel to pick an option. It's closeable once the decision is recorded.*

---

## Safe to Close Now

| # | Title | Evidence | Action |
|---|---|---|---|
| #495 | Wire: KG Entities | `DocumentInspector.swift` has `.knowledgeGraph` tab wired to `KnowledgeGraphInspectorSection`; tab visible in inspector and also on `KGSurfaceTab.digest`/`.graph` in the widescreen KG panel. Entities load via `EntityServiceGenerated`. Acceptance criteria (entities tab, entity detail, sidebar entities) met. | Close as completed |
| #496 | Wire: KG Claims List | `DocumentKGSurface.swift` has `.claims` tab wired to `KnowledgeGraphInspectorSection`; `ClaimSummaryCardView.swift` renders claim text + confidence badge + source link; `DocumentInspector.swift` knowledgeGraph tab also shows claims list. `ClaimSummaryCard+Details.swift` shows source excerpt. Acceptance criteria met. | Close as completed |
| #497 | Wire: KG Claim Inspector | `EditClaimSheet.swift` exists and is called from both `ClaimSummaryCardView` (line 177) and `DocumentInspectorArtifactsTab` (line 1621). `ClaimSummaryCard+Details.swift` has Details/source tabs. `claim_links.py` backend serves related claims. Three-tab inspector (details/links/sources) is implemented. Acceptance criteria met. | Close as completed |
| #498 | Wire: Ontology Browser | `OntologyBrowser.swift` (273 symbols) renders entity types list, entity detail, claims per entity, `EntityDetailView` with filter chips, merge/split sheets, and `ForceDirectedGraphView` for relationships. Tests pass (`OntologyBrowserFilterTests`). **Note:** `OntologyBrowser` is NOT in the main content router (`ContentView+Navigation.swift`) — it is accessible only through a preview/standalone path. If the acceptance criteria requires it to be reachable from the sidebar, this is PARTIAL. If "renders with live data" is acceptable via the existing preview route, it is DONE. **Recommend**: close and open a follow-up "add OntologyBrowser to sidebar navigation" if Daniel has not found it. | Close as completed (add follow-up note) |
| #721 | Inspector shows parent folder artifacts on child page | `ArtifactServiceGenerated.swift` `getArtifacts()` has `includeDescendants` flag; `DocumentInspector.swift` calls it with `includeDescendants: false` at lines 599 and 1517; `ArtifactEntityViews.swift` uses `includeDescendants: false` at lines 160 and 265. Comment explicitly references the V2 strict-scope fix. Bug is resolved. | Close as fixed |
| #922 | Decide future of hermeneutics router | This is a decision document, not a feature. The hermeneutics router IS registered in `api/main.py` at `/api/hermeneutics` and `/api/kg/interpretations` (lines 852, 854). It was NOT removed. The issue asks Daniel to pick one of three paths. The decision is stale — the router stayed registered. Recommend closing with a note: "Router retained at /api/kg/interpretations; PatternInstance/hermeneutic circle remain unimplemented in Swift. Wire or remove on Swift bandwidth." | Close as completed (decision: route stays, wire later) |

---

## Partial — Some Shipped, Some Not

| # | Title | Shipped | Missing | Recommended Action |
|---|---|---|---|---|
| #916 | KG: user-created entities/claims (CRUD parity) | Backend: `POST /api/entities`, `POST /api/claims`, `POST /api/annotations` exist. `EditClaimSheet.swift` lets users edit claims. `created_by` field exists on `AnnotationService.swift` model. | Swift UI to CREATE a new entity (no `CreateEntitySheet` found anywhere). No "+" button in OntologyBrowser header to add entity. No "Add Claim" button in EntityDetailView header. No right-click-selection → "Create claim from selection." Provenance badge (✏️ vs AI icon) not found in any Swift view. | Keep open; add label `status:partial`; note: EditClaim done, CreateEntity UI missing |
| #1333 | NER with spaCy — fast on-device entity extraction | Backend fully implemented: `kg/spacy_ner.py` with `extract_entities`, `cluster_aliases`, language detection, `en_core_web_sm`/`es_core_news_sm` support. wired into `workflows/ner/providers.py` (line 201). Tested (`test_spacy_ner.py`). | Swift UI model selection (`en_core_web_sm` vs `en_core_web_trf`) is absent — `LocalModelsSettingsView.swift` only shows Whisper and Embeddings sections, no spaCy row. No UI to configure per-workflow-node spaCy vs LLM toggle. | Keep open; note: backend done, UI surface (settings row + node config picker) still needed |
| #900 | KG triangulation: support_count + corroborated | Backend: `kg/triangulation.py` exists with `triples_for_entity`; `kg_triangulation.py` routes expose `entity_triangulation` and `library_triangulation`. `entity_inspector.py` calls `triples_for_entity`. | No Swift caller for `/api/kg/triangulation/*` found. No `corroborated` status badge or `support_count` shown in any Swift view. | Keep open with `status:partial`; note: backend done, no Swift wire |
| #903 | KG source authority weighting | `models.py` has `source_authority: SourceAuthority = SourceAuthority.unknown`. `kg/triangulation.py` uses `source_authority` in weighting at line 171. | No Swift UI to set/display source authority (primary/secondary/tertiary) found in any view. | Keep open with `status:partial`; note: model + triangulation logic done, no Swift UI |

---

## Genuinely Open — No Implementation Found

| # | Title | Evidence | Action |
|---|---|---|---|
| #499 | Wire: Epistemology Graph | No `EpistemologyGraphView` or epistemology graph concept found in any Swift file. The claim-relationship graph concept (`support/contradict/extends` edges) exists in `kg_graph.py` backend but no Swift canvas. Contradiction triage (#373) also missing. | Keep open |
| #500 | Wire: KG Predictions | `kg_predictions.py` backend exists and is registered. No `PredictionReviewView`, no predictions panel, no accept/reject UI found in any Swift file. | Keep open |
| #501 | Wire: Hermeneutics | `InterpretationPanelView`, `FrameworkListView` — neither found anywhere in Swift. Hermeneutic circle view — not found. The hermeneutics backend router IS registered but zero Swift callers. | Keep open |
| #372 | Claim review queue UI with curation workflow | `claim_curation.py` backend exists with state transitions. No Swift `ClaimReviewQueueView` or equivalent found. No `unreviewed → shortlisted → curated/rejected` UI. | Keep open |
| #373 | Contradiction triage UI | No `ContradictionTriageView` or side-by-side contradiction UI found in Swift. | Keep open |
| #375 | Interpretations workspace v1 | `ResearchWorkspaceView.swift` exists and IS wired into navigation (`ContentView+Navigation.swift` line 32). However, it routes to `ResearchWorkspaceView(project:)` from the research sidebar mode — this appears to be the Research Projects surface (#918), not the hermeneutics Interpretations workspace (argument/method records linked to claims with citation/provenance lineage). No `InterpretationWorkspace` or method taxonomy tagging found. | Keep open; clarify if ResearchWorkspaceView covers this |
| #917 | KG: Zettelkasten layer | No Zettelkasten concept found in any Swift or Python file. | Keep open |
| #918 | KG: Projects / research workspaces | `projects.py` backend fully implemented (CRUD, inclusions, membership). `ResearchWorkspaceView.swift` exists and is wired. `ResearchProjectListView.swift` exists. `ResearchBrowserPane.swift`, `ResearchTasksPane.swift` exist. However, the issue specifies grouping notes + claims + entities under a named analysis workspace — the research project API supports `target_type` of document/entity/claim/note/interpretation. **Likely substantially implemented.** Recommend a deeper hands-on test; may be closeable. | Needs hands-on verification — likely DONE or nearly so |
| #1124 | Hermeneutics: controlled predicate vocabulary | No `HermeneuticPredicate`, `centers`, `decenters`, `contests_reading` found anywhere. | Keep open |
| #1187 | Source-tied notes: per-claim annotation layer | `ClaimNote` model not found in any Python or Swift file. `POST /api/kg/claims/{id}/note` endpoint not found in `claims.py` or `annotations.py`. | Keep open |
| #753 | Add 'Detect AI Text' workflow tool | No `ai_text_detector`, desklib model, or detect-AI-text node found anywhere. | Keep open |

---

## Summary Table (All 21 Issues)

| # | Title | Verdict | Recommended Action |
|---|---|---|---|
| #495 | Wire: KG Entities | DONE | Close as completed |
| #496 | Wire: KG Claims List | DONE | Close as completed |
| #497 | Wire: KG Claim Inspector | DONE | Close as completed |
| #498 | Wire: Ontology Browser | DONE* | Close (add follow-up for sidebar nav) |
| #499 | Wire: Epistemology Graph | OPEN | Keep open |
| #500 | Wire: KG Predictions | OPEN | Keep open |
| #501 | Wire: Hermeneutics | OPEN | Keep open |
| #372 | Claim review queue UI | OPEN | Keep open |
| #373 | Contradiction triage UI | OPEN | Keep open |
| #375 | Interpretations workspace v1 | OPEN | Keep open; verify ResearchWorkspaceView scope |
| #900 | KG triangulation | PARTIAL | Keep open; backend done, no Swift wire |
| #903 | Source authority weighting | PARTIAL | Keep open; model done, no Swift UI |
| #916 | User-created entities/claims CRUD | PARTIAL | Keep open; edit done, create/provenance missing |
| #917 | Zettelkasten layer | OPEN | Keep open |
| #918 | Research projects/workspaces | PARTIAL/likely DONE | Verify hands-on |
| #922 | Decide hermeneutics router future | DONE (decision) | Close with decision note |
| #1124 | Controlled predicate vocabulary | OPEN | Keep open |
| #1187 | Source-tied notes per-claim | OPEN | Keep open |
| #1333 | NER with spaCy | PARTIAL | Keep open; backend done, UI surface missing |
| #721 | Inspector shows parent folder artifacts | DONE | Close as fixed |
| #753 | Detect AI Text workflow tool | OPEN | Keep open |

---

## Notes on Methodology

- "No Swift caller" determination: searched for view type names, service call sites, and route strings across all `.swift` files in `fichero/fichero/`. Absence of results in jcodemunch full-text search is treated as "no caller."
- OntologyBrowser (#498): the view is fully implemented and has tests, but the only call site found was the preview macro inside `OntologyBrowser.swift` itself. If Daniel cannot navigate to it from the main app, this is PARTIAL not DONE.
- #918 (Research workspaces): `ResearchWorkspaceView` IS wired but this issue predates the Research mode — worth verifying that the Research workspace actually satisfies "group notes + claims + entities under named analyses" before closing.
