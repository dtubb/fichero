# KG Enrichment, RDF & Linked Data — Design Spec (#4641 · #4624)

> Design-led (Testing Constitution). The Fichero creative director owns this intent;
> tests enforce it; code makes them pass. **Status: DRAFT — awaiting approval before
> tests/code.** Tags: [OK] built today · [MISSING] not built · [PARTIAL] backend/service
> exists, not surfaced or not validated.

## Intent (the design)

Fichero's knowledge graph is **RDF under the hood and part of the Web of Data**: entities
and claims can be **enriched** from shared authorities (SPARQL/gazetteers/Wikidata),
**predicted** from the library's own graph (PyKEEN), and **exchanged** as validated
JSON-LD — and every one of those capabilities exists across the whole spine:
**backend → UX → AI (MCP) + CLI → tests → export.** A capability that works in the
backend but isn't surfaced, or isn't tested at every layer, is not done.

## What already exists (inventory — build ON this, don't replace)
- **SPARQL endpoints in Settings** [OK] — `KnowledgeSettingsView` manages the SPARQL
  endpoints the enrichment queries (Wikidata default, user-addable, no silent fallback).
- **SPARQL / RDF graph** [OK] — rdflib-backed; `KGQueryConsoleView` runs live SPARQL
  (`kg_sparql`); the graph rebuilds to DuckDB for external tooling.
- **Wikidata enrichment** [OK backend/service] — `EntityService+Enrichment` preview →
  import selected statements as **authority-sourced claims** (gated by the external-
  enrichment switch; a 403 surfaces when disabled). CLI: import-wikidata-statements.
- **PyKEEN link prediction** [OK backend/service] — train a link-prediction model on the
  library's claims; `EntityService+KnowledgeGraph` predict / stored / verify;
  `HeuristicReviewSheet` reviews predicted links → import as claims. CLI: train-pykeen.
- **Authority linking** [OK] — `EntityStore+Authority` (sameAs to authority ids).
- **Gazetteer geo** [OK backend] — offline gazetteer + opt-in Nominatim (`media/geo.py`).
- **W3C Web Annotation export** [OK] — `/api/documents/{id}/annotations…` (JSON-LD for
  ANNOTATIONS via the IIIF route; anchors map to W3C `refinedBy`).
- **Structured export** [OK] — JSONL + Parquet + Markdown/DOCX/XLSX/Eleventy
  (`export_service.py`).

## The gaps (what this spec adds)

### A. JSON-LD for the KG (entities/claims) — export + import, VALIDATED
- `kg.jsonld.export` [MISSING] — export entities + claims as **JSON-LD** with a real
  `@context` (schema.org / Linked Art / CIDOC-CRM mapping). The exporter has JSONL/Parquet
  but **no JSON-LD** for the KG today (only annotations are JSON-LD, via IIIF).
- `kg.jsonld.export.validated` [MISSING] — the export is **validated against its spec**
  before it's handed over: JSON-LD expands/compacts cleanly against the `@context`, and
  (where a shape is declared) passes **SHACL/ShEx**. A malformed export never ships — it
  raises (prefer-raise), never a silent half-file.
- `kg.jsonld.import` [MISSING] — import JSON-LD back (round-trip), mapping external terms
  onto Fichero's entity/claim model; imported statements are **authority/provenance-
  tagged** (created_by = the source), never silently merged as first-party.
- `kg.jsonld.roundtrip` [MISSING] — export → import → export is stable (the invariant test).

### B. Enrichment sources — unified in Settings
- `kg.enrich.sources.settings` [PARTIAL] — Settings has SPARQL endpoints; extend to a
  unified **Enrichment Sources** area: Wikidata, GeoNames, Getty (TGN/AAT), VIAF, Pleiades,
  gazetteers — each a togglable, configurable source (endpoint/key), with the external-
  enrichment master switch. (Which sources beyond Wikidata/gazetteer: creative-director
  input — "not sure where else": propose VIAF/GeoNames/Getty/Pleiades.)
- `kg.enrich.per-type` [MISSING] — a source applies to the right entity types (places →
  GeoNames/Pleiades; persons/works → VIAF/Wikidata; concepts → Getty AAT).
- `kg.enrich.provenance` — every enriched value is authority-sourced + provenance-tagged
  (rides #4636), never indistinguishable from hand/AI values.

### C. Surface the enrichment/prediction UX everywhere
- `kg.enrich.ux` [PARTIAL] — Wikidata enrich preview/import + PyKEEN predictions have
  services + a review sheet; ensure they're reachable from the **entity inspector and the
  KG tables** (an "Enrich…" / "Suggested links" affordance), not only the Ontology browser.
- `kg.enrich.mcp-cli` [PARTIAL] — expose enrich-preview/import + predict via MCP + CLI so
  an agent can enrich (some CLI exists: wikidata import, pykeen train).

## D. Testing matrix — Swift + UX + backend, per capability (creative-director mandate)

Every capability above is delivered with tests at **all three layers**, or it is not done:

| Capability | Backend (pytest) | Swift (unit) | UX (XCUITest / RenderPreview) |
|---|---|---|---|
| jsonld.export.validated | serialize + validate against @context/SHACL; malformed raises | service maps envelope; pure format assertions | export action reachable, shows result/error |
| jsonld.import.roundtrip | import maps terms + provenance-tags; round-trip stable | service decodes; pure mapping rules | import affordance + honest error |
| enrich (Wikidata/authority) | preview/import endpoints; gated by switch; 403 when off | EntityService enrich preview/import decode | Enrich… affordance + review + apply in inspector/table |
| pykeen predictions | train/predict/stored/verify; bounded resource | prediction decode + verify mapping | predictions review + accept/reject |
| enrichment sources settings | persist/read sources; validation | settings store round-trip | add/remove/toggle a source, no silent fallback |
| sparql console | query runs; truncation honest | store decode | console runs a query, shows rows/error |

Cross-surface invariant (HARD-GATE): the SAME enrichment/prediction reachable + consistent
from backend, MCP/CLI, and the app; and a validated JSON-LD export re-imports to the same
graph.

## Open questions for the creative director
- Which enrichment sources to ship first beyond Wikidata + gazetteer (VIAF / GeoNames /
  Getty / Pleiades)?
- JSON-LD `@context`: schema.org, Linked Art, or CIDOC-CRM as the primary mapping (or all,
  selectable)?
- Validation strength: JSON-LD expand/compact only, or also SHACL shapes (and who authors
  the shapes)?
- Does JSON-LD import create a separate "imported" provenance layer distinct from Wikidata-
  enrichment claims?

Ties: #4641 (authority/Web of Data), #4640 (exporter — add JSON-LD beside JSONL), #4636
(provenance for enriched/imported values), #4624 (KG tables surface the affordances),
`archival-data-model-plan.md` P8 (authority/linked data).
