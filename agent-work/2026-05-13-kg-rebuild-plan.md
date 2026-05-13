# KG Surface Rebuild — Code Review + Plan (2026-05-13)

Context: I shipped a KG viz (force-directed graph, chart, RAG inspector panels) earlier today; Daniel tested it and filed 7 bugs (#976–#982). This document is the code review + plan for the rebuild.

## Code-review findings

### Data model — what the schema actually is

**`KnowledgeClaim` is NOT a Neo4j SPO triple.** The actual fields:

| Field | Use |
|---|---|
| `text` | Prose claim sentence (extractor-emitted) |
| `entityIds: [String]` | Bag of mentioned entities — no subject/object roles |
| `sourceDocumentId`, `sourcePageLabel`, `sourceCharStart/End`, `sourceBbox`, `sourceExcerpt` | Rich provenance for "back to source" |
| `grounds, warrant, backing, qualifier, rebuttal` | Toulmin argumentation structure |
| `claimType` (Fact/Analysis/Interpretation/Argument/Historiography/Theory) | Knowledge kind |
| `epistemicStatus` (Confirmed/Tentative/Rejected) | Curation state |
| `timeStart, timeEnd, timePrecision` | When the claim's referent is anchored |
| `confidence`, `predictedConfidence`, `predictedBy`, `prediction` | Extractor metadata |

**Correction (Daniel pushed back, rightly):** the backend extractor DOES produce SVO. Verified in `extractors.py:1375-1456`:

```python
meta["subject"] = canonical   # entity name
meta["verb"]    = verb        # predicate
meta["object"]  = obj         # object phrase
claim_text = f"{canonical} {predicate}."   # composed sentence
```

The triple is stashed in `claim.metadata` (the free-form `additionalProperties` dict). It's NOT promoted to top-level model fields, but it IS retrievable. The SwiftUI side just isn't reading it today.

**So the fix is frontend-only for the MVP:** read `claim.metadata["subject" / "verb" / "object"]` in the Swift card / graph code, render Neo4j-style edges `subject —[verb]→ object`. No backend changes required.

**Optional follow-up:** promote subject/verb/object to first-class top-level fields on `KnowledgeClaim` (Pydantic + OpenAPI). Benefits: type-safe Swift codegen, queryable in DuckDB without JSON unpacking, easier filtering. Trade-off: schema migration + extractor write-path change + OpenAPI regeneration. Defer until the frontend proves the model works.

The data DOES support the **"back to source"** flow perfectly: `sourceDocumentId + sourcePageLabel + sourceCharStart/End + sourceBbox` is everything needed to open a doc and highlight the exact span.

### `ClaimSummaryCardView.swift` (185 lines)

What it does today:
- Renders `claim.text` + (when distinct) `claim.sourceExcerpt` in italic
- Two pills: `claimType` + `epistemicStatus`
- Expand-on-tap fetches contradictions + evidence-chain
- Tap-excerpt → posts a NotificationCenter event to run a library text search
- Context menu → delete claim

What it's missing per the bugs:
- **No source-document name** (#978 + #979). All the data is there (`sourceDocumentId`, `sourcePageLabel`) — just no UI for it.
- **No "open source" affordance**. Tapping the excerpt searches, doesn't navigate.
- Why "Carlos: served as" looks truncated: the extractor's `claim.text` is sometimes incomplete. **Not a UI bug.** Either the LLM produced a fragment, or the SVO-style extractor wrote subject+predicate without the object. Backend issue, file separately.

### `EntityDetailView.swift` (413 lines) + Status/Kind chips

The "Status: Confirmed | Tentative | Rejected" and "Kind: Fact | …" rows in #979's screenshots live here (not on the card). They render as horizontal chip rows. Need to confirm:
- Are they wired to filter `entityClaims`? If not, they're a dead control.
- Without counts or a clear "ALL / SELECTED" mode, they look like a legend.

### `OntologyBrowser.swift` (1407 lines)

Hosts the entity list, the three-mode picker (List/Graph/Chart), and the `ForceDirectedGraphView` struct (which I folded in because the PBXGroup isn't synchronized).

Problems:
- Redundant "Knowledge Graph" toolbar text (#981)
- `entityListSidebar` has `.frame(minWidth: 220, maxWidth: 320)`. The maxWidth cap is too low at wide windows but the contents don't fill width either — list rows anchor left and leave gap to the right (#981).
- HSplitView weight wrong in Graph/Chart modes (#980)
- `ForceDirectedGraphView` (~360 lines inside the file):
  - **Crash hypothesis:** simulation runs 4s @ 60Hz → 240 ticks. Each tick is O(N²) repulsion + O(E) springs. For N=~150 entities (Daniel's "Shifting Livelihoods") that's 22,500 pairs × 240 ticks = 5.4M force calcs on the main thread → beachball.
  - **NaN risk:** when two nodes start at the same position (e.g., two entities indexed at the same angle bucket) the `force / distSq` term blows up. `max(distSq, 25)` floor mitigates but doesn't eliminate. Crash is likely Canvas tripping on NaN positions.
  - **Why a circle:** initial seed places entities evenly on a 180pt radius circle. With sparse co-occurrence edges (the Shifting Livelihoods corpus has 31 people + few inter-people claims), spring forces don't pull clusters → circle stays a circle.
  - **Why labels overlap:** every node draws its name unconditionally below the dot. No collision avoidance, no zoom-aware fading, no hover.

### Inspector landscape

`DocumentInspector.swift` is 1005 lines + 4 subfiles. Today I added two sections to the Info tab:
- `RelatedClaimsPanel` (KG-RAG via `/api/kg/claim-search/{id}/similar`) — works
- `CitationGraphPanel` (inbound/outbound via `/api/citations/graph/...`) — works

The architectural ask (#982) wants:
- A KG tab in DocumentInspector showing claims FROM this document (different from "similar claims" — these are the doc's own extracted claims)
- The center pane to remain a source preview as the user navigates KG; the Ontology Browser should be the right inspector, not the center
- "Center = source, Inspector = KG tools"

This is the right direction. Most of today's KG center-pane work becomes the right-side inspector content.

---

## Plan — phased delivery

### Phase 1 — Stop bleeding (this session)

Small focused fixes that make the existing surface usable without rebuilding:

| # | Fix | Issue | Est |
|---|---|---|---|
| 1 | Drop "Knowledge Graph" toolbar header | #981 | 2 min |
| 2 | Add source-doc citation line to ClaimSummaryCard | #978 + #979 | 20 min |
| 3 | Fix entity-list HSplitView width (fill, idealWidth, persist split) | #980 + #981 | 15 min |
| 4 | Guard Graph mode against large entity sets (show "filter first" instead of crashing) | #976 partial | 15 min |
| 5 | Default-collapse the verbatim excerpt on claim card (Daniel: text duplicated, too tall) | #979 | 10 min |
| 6 | Render `entity.description` on the detail header (was missing for Carlos) | #978 | 10 min |

### Phase 2 — Source-anchored navigation (next session)

Make the "always show preview, get back to source" architecture #982 calls for:

| # | Fix | Issue | Est |
|---|---|---|---|
| 7 | Add a "Claims" tab to DocumentInspector showing claims where `source_document_id == this.doc.id` | #982 + #979 | 1 hr |
| 8 | "Open source" affordance on claim card → jumps to source doc + page; uses sourceCharStart/End or sourceBbox for highlight when present | #982 | 1 hr |
| 9 | Move the kind/status chips from a dead row into a real filter bar on the Claims list | #979 | 30 min |

### Phase 3 — Visualization redesign (next session+)

| # | Fix | Issue | Est |
|---|---|---|---|
| 10 | Replace force-directed view with a **focus-neighborhood layout** (Tinderbox hyperbolic / Neo4j Explore): pick a focus entity, render its first-degree neighbors radially, edges labeled with claim-text excerpts. | #976 + #977 | 2–4 hrs |
| 11 | Predicate / kind filter checkboxes (per Tinderbox screenshot) | #976 | 30 min |
| 12 | Hover/click name reveal; default-hide labels except for selected + top-N degree | #977 | 1 hr |
| 13 | Move all of this into a right-inspector container (per #982) | #982 | 1 hr |

### Phase 4 — Backend follow-ups

| # | Fix | Issue | Est |
|---|---|---|---|
| 14 | Backend: investigate why some claim.text values are truncated ("Carlos: served as") — likely SVO extractor prompt | new bug | TBD |
| 15 | Backend: derive a "primary predicate" hint per claim (verb between mentioned entityIds, when extractable) to feed the graph view's edge labels | new feature | TBD |

---

## What I'll do now

Phase 1 in this session. Commit each fix individually. Update the bug issues with cross-links as I go.

Phases 2–4 carry into next session — too much for one chunk.
