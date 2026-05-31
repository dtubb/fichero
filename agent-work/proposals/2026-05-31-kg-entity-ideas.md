# KG Entity Ideas — Investigation (2026-05-31)

Answers Daniel's three questions from 2026-05-31 session.
Code investigation only — no edits made.

---

## FINDING 1 (PRIORITY): Entity Browser — Exists but is COMPLETELY orphaned

### Verdict: NOT REACHABLE. Navigation regression, not a missing feature.

**What exists:**
- `OntologyBrowser` is a substantial, fully implemented SwiftUI view at
  `fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/OntologyBrowser.swift` (~1700 lines).
- It has its own `NavigationHistoryManager` model (back/forward), entity list + detail,
  force-directed graph, kind filter chips, claim summary cards — the full clickable entity browser.
- Unit tests exist: `fichero-tests/OntologyBrowserFilterTests.swift`.

**What's broken:**
- `OntologyBrowser()` is instantiated in exactly **one** place in the entire codebase:
  the `#Preview("Browser")` block at the bottom of its own file (line 1092).
- It is called by **zero** production code paths — not in `ContentView+Navigation.swift`,
  not in `ContentView+ViewBuilders.swift`, not anywhere in `SidebarView`.
- `SidebarMode` has no `kg` / `ontology` / `entities` case. The available modes are:
  `library`, `search`, `chat`, `workflows`, `automation`, `activity`, `mindPalace`, `research`.
- `AppViewMode` (the center-column router) also has no KG entity browser case.
- `SidebarModeBar` iterates over feature-flagged modes — there is no KG flag to flip.

**Root cause:** The `OntologyBrowser` was built (evidenced by the tests being wired to it at
issue #498) but the sidebar entry and center-column routing case were never added — or were
removed at some point during the sidebar refactor.

**Exact gap:**
1. No `SidebarMode.kg` (or equivalent) case.
2. No `SidebarModeIcon(mode: .kg, …)` entry in `SidebarModeBar`.
3. No `case .kg` in `AppViewMode`.
4. No branch in `ContentView+Navigation.swift` `contentView` switch to render `OntologyBrowser()`.
5. No `handleSidebarModeChange()` branch for the KG mode.

**Recommended fix (minimal, ~50 lines across 5 files):**
1. Add `case kg` to `SidebarMode` enum in `ViewSettings.swift`.
2. Add `SidebarModeIcon(mode: .kg, …)` to `SidebarModeBar` (behind `featureManager.isKGEnabled`
   or unconditionally, since KG extraction already ships).
3. Add `case kg` to `AppViewMode` in `SidebarViewTypes.swift`.
4. Add a branch in `ContentView+Navigation.swift` `contentView` switch to render `OntologyBrowser()`.
5. Add a `case .kg` branch in `ContentViewModifiers.swift` `handleSidebarModeChange`.
6. Add label/icon/shortcutNumber for `.kg` in `ViewSettings.swift` `SidebarMode` computed properties.

**Issue action:** Reopen / update **#498** ("Wire: Ontology Browser"). It is open, P1, milestone
"KG & Hermeneutics", status "ready-for-test" — but nothing is actually wired to show it to Daniel.
The body already describes exactly what it should do. Add a checklist item:
"OntologyBrowser() rendered from sidebar nav (SidebarMode.kg)".

Milestone: KG & Hermeneutics.

---

## FINDING 2: Entity Bio from SVO — CLI exists; no API endpoint; no Swift UI

### Current state:
- **CLI only:** `fichero entity biography <entity-id>` exists at
  `fichero-engine/src/fichero/cli/commands/entity.py:119`.
  It assembles entity metadata + associated documents + co-occurrence neighbours from existing
  API calls (`get_entity`, `entity_documents`, `entity_co_occurrence`) and formats them as
  markdown/text/json. It is NOT an LLM-generated narrative — it is a structured dump.
- **No API endpoint:** There is no `GET /api/entities/{id}/biography` or equivalent route.
  The hermeneutics router (`/api/hermeneutics`) has interpretive frameworks and circle-state but
  no entity narrative synthesis.
- **No SwiftUI surface:** `EntityDigestView` exists at
  `fichero/fichero/Views/KnowledgeGraph/EntityDigestView.swift` — its docstring says it
  "prioritizes readability and a 'published' feel over curation tools" — but it is also
  **not called from any production code path**. It appears to have been a second orphaned view.
- **No LLM bio:** No backend function generates a natural-language biography synthesising SVO
  claims and cross-doc excerpts via LLM.

### What's actually needed for Daniel's idea:
1. A `GET /api/entities/{entity_id}/biography` endpoint that collects: entity metadata,
   all SVO claims (as structured subject→predicate→object triples), source excerpts
   (`source_excerpt` field already on `KnowledgeClaim`), co-occurring entities, and document list.
2. Optionally an LLM pass that narrates those facts into a paragraph bio (could reuse the
   `/api/hermeneutics/interpretations` LLM path).
3. Wire `EntityDigestView` (already exists, already orphaned) as the UI for the bio —
   or surface it in `OntologyBrowser`'s entity detail panel.

### Proposed issue:
**Title:** "Entity biography: `/api/entities/{id}/biography` endpoint + EntityDigestView wire-up"
**Milestone:** KG & Hermeneutics
**Scope:**
- Backend: new route that aggregates entity + claims + excerpts + co-occurrence into
  a structured bio payload (no LLM required for v1 — structured data only).
- SwiftUI: render `EntityDigestView` from inside `OntologyBrowser` entity detail panel.
- Stretch: LLM narrative pass (separate sub-task).

---

## FINDING 3: Programmatic Hermeneutics / Triangulation / Provenance / Certainty

### What already exists in the backend (no UI):

**Triangulation / corroboration (#900):**
- `KnowledgeClaim` has `corroboration_count: int` and `corroborating_source_ids: list[str]`
  (in `knowledge_models.py:1764`).
- `_entity_writer.py` computes these at extraction time: `_find_corroborating_claim` +
  `_merge_corroborating_claim` (lines 611–693). When a new claim matches an existing SVO triple
  from a different document, `corroboration_count` is incremented and `confidence_source` is set
  to `"corroboration"`.
- A `kg_triangulation` route exists (`/api/kg/triangulation`) with a
  "Triangulated triples for one entity" endpoint.
- **Gap:** #900 is OPEN. The data model and extraction-time merging exist; the open question
  is a global aggregation query and a UI surface showing "6 sources agree → triangulated".

**Source authority (#903):**
- `SourceAuthority` enum exists in `models.py:94` (`primary/secondary/tertiary/unknown`).
- `Document` has `source_authority: SourceAuthority = SourceAuthority.unknown` (line 190).
- Weight map defined at module level (line 111).
- **Gap:** #903 is OPEN. Authority is stored but not yet plumbed into weighted `support_count`
  computation, and there is no UI to set/display a document's authority tier.

**Quotation kind / certainty (#1123):**
- `QuotationKind` enum exists; `KnowledgeClaim.quotation_kind` and `confidence_source` and
  `evidential_confidence_source` are all present in `knowledge_models.py:1634–1770`.
- `_detect_quotation_kind` in `_entity_writer.py:1107` auto-tags claims as verbatim/paraphrase/
  summary at extraction time.
- **No SwiftUI surface:** claim-level `quotation_kind` / `confidence_source` are returned in the
  API (they are in `KnowledgeClaim`) but not displayed in the `OntologyBrowser` claim cards or
  the inspector KG tab.

**Hermeneutics router (#922):**
- Hermeneutics router is LIVE at `/api/hermeneutics` and `/api/kg/interpretations`
  (registered in `main.py:852–854`). It has 20+ endpoints: frameworks, interpretations,
  patterns, hermeneutic circle state, LLM suggestions.
- Issue #922 is CLOSED ("decided future of hermeneutics router") — the router was temporarily
  unregistered overnight and then re-registered. It is currently active.
- **No SwiftUI consumer:** zero Swift files call `/api/hermeneutics` endpoints.

### Mapping to issues:

| Concept | Backend status | UI status | Issue |
|---|---|---|---|
| Triangulation / corroboration | Extraction-time merging done; global query gap | No UI | #900 OPEN — still valid, focus on UI surface |
| Source authority weighting | Enum + field exist; weighting not computed | No UI | #903 OPEN — still valid |
| Quotation kind / certainty | Fully tagged at extraction | Not shown in OntologyBrowser claims | No specific issue — file new |
| Hermeneutic circle / frameworks | Router live, full CRUD | No SwiftUI consumer | #922 CLOSED — reopen or file follow-on |

### Proposed new issue:
**Title:** "Surface claim provenance/certainty in OntologyBrowser claim cards"
**Milestone:** KG & Hermeneutics
**Scope:** In the `OntologyBrowser` `ClaimSummaryCard`, display `quotation_kind` badge
(verbatim / paraphrase / summary), `confidence_source` tag, and `corroboration_count`
indicator ("3 sources"). Data is already in the API response — this is pure SwiftUI.

---

## Summary action list

1. **Reopen #498 + assign to next KG sprint.** Fix is ~50 lines across 5 files: add
   `SidebarMode.kg`, sidebar icon, `AppViewMode.kg`, content routing branch, and
   `handleSidebarModeChange` branch. `OntologyBrowser()` already exists and works in preview.
   This is the only thing blocking Daniel from clicking entities.

2. **File new issue: entity biography endpoint + `EntityDigestView` wire-up.** Backend
   assembles structured bio from existing endpoints; `EntityDigestView` (already built,
   already orphaned) renders it inside `OntologyBrowser` entity detail. Milestone: KG & Hermeneutics.

3. **File new issue: surface claim provenance in `OntologyBrowser` cards.** `quotation_kind`,
   `confidence_source`, and `corroboration_count` are already in the API response. Pure SwiftUI
   display work. Milestone: KG & Hermeneutics.

4. **#900 and #903** remain valid and open. No new issues needed; add to the KG sprint queue
   once entity browser (#498) is reachable.

5. **#922** (hermeneutics router): already closed/resolved. The router is live. Consider a
   follow-on issue scoped to "first Swift consumer of `/api/hermeneutics/interpretations`"
   when the browser is reachable and Daniel can actually see entity detail.
