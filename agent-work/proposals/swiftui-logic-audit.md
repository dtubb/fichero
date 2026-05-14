# SwiftUI KG-logic audit — move logic to the backend (Phase B)

**Date:** 2026-05-14
**Author:** autonomous loop (Phase B, iteration 2)
**Scope:** the KG / document-inspector SwiftUI surface
**Principle:** the backend owns logic (computation, aggregation, dedup, scoping,
summarization, filtering). SwiftUI only *renders* what the backend returns.
(See MEMORY `feedback_kg_logic_in_backend`.)

---

## Headline finding

The KG entity data reaches the UI through **two different, inconsistent paths**:

| Surface | Endpoint(s) it calls | Client-side work it does |
|---|---|---|
| Library **list view** rows | `getArtifacts(forDocumentId:)` | parses `artifact.data["items"]`, extracts names/keywords/dates → lozenges |
| **KG inspector tab** | `listClaims(sourceDocumentId:)` **+** per-entity `getEntity(id)` (O(n) calls) | dedups by canonical name, detects `mergedIntoId`, groups claims into kind buckets, filters hidden kinds |
| **Ontology browser** | `listEntities(query:)` | filters by kind client-side, counts by kind for charts |

Three surfaces, three data sources, three client-side aggregation paths — so they
**disagree** (#1068) and the inspector is slow (O(n) `getEntity` calls). Every
issue in the cluster traces back to this: there is no single canonical
"knowledge for this document/scope" endpoint.

---

## Findings (file → misplaced logic → issue → backend replacement)

### 1. `KnowledgeGraphInspectorSection` — `DocumentInspectorArtifactsTab.swift:639–837`
- **Misplaced:** dedup by canonical name (`seenKey` set), `mergedIntoId` skip, claim→kind bucketing, hidden-kind filtering (lines 674–729). Load path makes `listClaims(...limit:500)` then **loops `getEntity(id)` per unique entity** (805–837).
- **Issue:** #1068.
- **Backend replacement:** `GET /api/documents/{id}/knowledge-graph?include_children={bool}` → returns `{ entities_by_kind, claims }`, already deduped / merge-resolved / grouped. One call, no per-entity fan-out.

### 2. `ArtifactEntitiesView` — `LibraryView+ColumnConfig.swift:176–372`
- **Misplaced:** `extractNames()` / `extractKeywords()` / `extractDates()` pull structured fields out of raw artifact JSON (329–346). Different data source from the inspector → the two never agree.
- **Issue:** #1068 (both surfaces must consume the *same* canonical endpoint).
- **Backend replacement:** same `GET /api/documents/{id}/knowledge-graph` endpoint, a lightweight projection (`?fields=lozenges`) for the list row.

### 3. `EntityDetailView` — `EntityDetailView.swift:6–582`
- **Misplaced:** two-axis claim filtering (epistemic status + claim type) recomputed every render (44–62); **SVO-triple → prose biography composition** with pronouns + inline citations (102–163); filter-chip value sets derived client-side (507–518).
- **Issue:** #1050 (entity header = claim #1, not a real summary), #1030 (raw verb/object repr).
- **Backend replacement:** `GET /api/entities/{id}` returns a pre-composed `summary` / `biography` field + claims already filtered server-side. Prose synthesis is backend work (ties to #989).

### 4. `OntologyBrowser` — `OntologyBrowser.swift:15–582`
- **Misplaced:** `filterEntities()` applies hidden-kinds client-side (76–91); `listEntities(query:)` has free-text search but **no `?entity_type=` / `?scope=` server param** (481–517).
- **Issue:** #1047 (folder scope), #1071 (scoped aggregation + filter/search).
- **Backend replacement:** `GET /api/entities?kinds=...&query=...&scope={document|folder|library}` — filtering and scoping server-side.

### 5. `EntityKindChartView` / `ForceDirectedGraphView` — `OntologyBrowser.swift:895–1529`
- **Misplaced:** client-side count-by-kind bucketing (1457–1466); `hiddenKinds` filtered locally before the layout engine (1111–1122). (`fetchNeighborhood` traversal is correctly server-side — leave it.)
- **Issue:** #902-adjacent; low priority.
- **Backend replacement:** `count_by_kind` as a field on the entities response; `?exclude_kinds=` param on the neighborhood call.

### 6. `ClaimSummaryCard` — `ClaimSummaryCardView.swift:6–399`
- **Misplaced:** SVO extraction with metadata-dict fallback (26–42, duplicated from EntityDetailView); empty-content heuristic — "is `claim.text` a bare noun fragment?" (51–56).
- **Issue:** #1030 (raw verb/object repr), #1029-adjacent (content quality).
- **Backend replacement:** claims arrive with SVO already resolved + a `content_quality` flag; no client-side heuristic.

---

## Proposed backend endpoints

1. **`GET /api/documents/{id}/knowledge-graph`** — the canonical one. Params:
   `include_children` (PDF/folder aggregation — #1069), optional `fields` projection
   for the lightweight list-row case. Returns deduped, merge-resolved,
   kind-grouped entities + their claims. **Replaces findings 1 + 2.**
2. **`GET /api/entities/{id}`** extended — add a server-composed `summary` and
   filtered-claims support. **Replaces finding 3** (#1050).
3. **`GET /api/entities`** extended — `kinds`, `scope`, `count_by_kind`.
   **Replaces findings 4 + 5** (#1071).
4. Claims responses carry resolved SVO + `content_quality`. **Replaces finding 6** (#1030).

---

## Recommended implementation sequence

1. **#1068 first** — build `GET /api/documents/{id}/knowledge-graph` (with
   `include_children` covering **#1069**). This is the keystone: it kills the
   two-endpoints-disagree problem and the O(n) `getEntity` fan-out. Backend +
   pytest only; the SwiftUI rewiring is a thin follow-up.
2. **#1047** — fold the folder catalogue narrative into the same endpoint's
   response when the target is a folder.
3. **#1050** — extend `GET /api/entities/{id}` with the server-composed summary.
4. **#1030 / #1071 / charts** — claims SVO + `content_quality`, `GET /api/entities`
   scoping params. Lower priority.

Each step is backend-first (pytest-verifiable); SwiftUI changes are render-only
follow-ups (Phase C). ~6 files / ~1500 lines of client-side logic retire as the
endpoints land.
