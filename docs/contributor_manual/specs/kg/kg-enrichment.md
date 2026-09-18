# KG Enrichment, RDF & Linked Data — Design Spec (#4641 · #4624)

> Milestone: kg-enrichment
> Manual: TBD — the user manual needs an "Enriching your knowledge graph" section: pulling matches
> from shared authorities (Wikidata/gazetteers), what a suggested link is before you accept it,
> and how to export your graph as standards RDF so other tools can read it.
>
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
  Pinned: fichero-server/tests/unit/kg/test_wikidata_enrich_routes.py::test_sparql_endpoints_default_when_unset,
  fichero-server/tests/unit/kg/test_wikidata_enrich_routes.py::test_sparql_endpoints_malformed_falls_back_to_default,
  fichero-server/tests/unit/kg/test_wikidata_enrich_routes.py::test_put_sparql_endpoints_keeps_default_and_persists,
  fichero-server/tests/unit/kg/test_wikidata_enrich_routes.py::test_put_sparql_endpoints_rejects_unknown_selection.
- **SPARQL / RDF graph** [OK] — rdflib-backed; `KGQueryConsoleView` runs live SPARQL
  (`kg_sparql`); the graph rebuilds to DuckDB for external tooling.
- **Wikidata enrichment** [OK backend/service] — `EntityService+Enrichment` preview →
  import selected statements as **authority-sourced claims** (gated by the external-
  enrichment switch; a 403 surfaces when disabled). CLI: import-wikidata-statements.
  Pinned: fichero-server/tests/unit/kg/test_wikidata_enrich_routes.py::test_preview_is_opt_in,
  fichero-server/tests/unit/kg/test_wikidata_enrich_routes.py::test_import_marks_claims_wikidata_sourced,
  fichero/Tests/Unit/general/Transport/EntityServiceTransportTests.swift::testEnrichPreviewRoutesThroughTransport,
  fichero/Tests/Unit/general/Transport/EntityServiceTransportTests.swift::testEnrichImportRoutesThroughTransport.
- **PyKEEN link prediction** [OK backend/service] — train a link-prediction model on the
  library's claims; `EntityService+KnowledgeGraph` predict / stored / verify;
  `HeuristicReviewSheet` reviews predicted links → import as claims. CLI: train-pykeen.
  Pinned: fichero-server/tests/unit/kg/test_pykeen_predictor.py::test_skips_training_below_minimum_corpus
  (corpus-size guard).
- **Authority linking** [OK] — `EntityStore+Authority` (sameAs to authority ids).
- **Gazetteer geo** [OK backend] — offline gazetteer + opt-in Nominatim (`media/geo.py`).
- **W3C Web Annotation export** [OK] — `/api/documents/{id}/annotations…` (JSON-LD for
  ANNOTATIONS via the IIIF route; anchors map to W3C `refinedBy`).
- **Structured export** [OK] — JSONL + Parquet + Markdown/DOCX/XLSX/Eleventy
  (`export_service.py`).

## The gaps (what this spec adds)

### A. JSON-LD for the KG (entities/claims) — export + import, VALIDATED
- `kg.jsonld.export` **[OK]** (31e1a2f61) — export entities + claims as **JSON-LD** with a
  real, named, selectable `@context`. Corrected history: #4753's premise was wrong — the
  route (`GET /api/kg/export/rdf?format=json-ld`) already existed and already produced
  JSON-LD before this fix; what was actually missing was a CURATED context (it used
  rdflib's auto-generated one, whatever prefixes happened to be bound) rather than a real,
  documented profile. That's what landed: a named `schema-org` context
  (`knowledge.jsonld_context.JSONLD_CONTEXTS`), selectable via `?context=`, an unknown
  profile rejected (422) rather than silently falling back. Linked Art / CIDOC-CRM profiles
  are deliberately NOT advertised yet — tracked separately (needs the maintainer's domain review before
  anyone implements them, not an engineering gap). Pinned:
  `test_jsonld_export.py::test_export_entities_claims_as_jsonld_with_context`,
  `::test_jsonld_context_is_selectable_and_named`,
  `::test_jsonld_export_empty_graph_is_valid`,
  `::test_export_round_trips_for_every_non_jsonld_format` (the other three formats —
  nt/turtle/xml — had near-zero coverage before this pass),
  `::test_jsonld_export_round_trips_to_isomorphic_graph`.
- `kg.rdf-export-visible` — **[GAP]** (#4827) the RDF/JSON-LD export exists and is now tested,
  but nothing in the app reaches it — no menu item, no Settings action, no button calls
  `GET /api/kg/export/rdf`. An engine capability with no client entry point.
- `kg.jsonld.export.validated` **[OK]** (31e1a2f61) — the export is validated before being
  handed over: it round-trips (serialize → reparse) cleanly, and a malformed export never
  ships — it raises (500, prefer-raise), never a silent half-file. Pinned:
  `test_jsonld_export.py::test_malformed_export_raises_never_ships`,
  `::test_validate_jsonld_export_raises_http_exception_directly`. **SHACL/ShEx remains
  unbuilt** — no shape is declared for the KG yet; this is its own honest gap, not folded
  into the [OK] above (no shape to validate against isn't the same claim as "the JSON-LD
  itself round-trips cleanly").
- `kg.jsonld.import` [MISSING] (#4755) — import JSON-LD back (round-trip), mapping external terms
  onto Fichero's entity/claim model; imported statements are **authority/provenance-
  tagged** (created_by = the source), never silently merged as first-party.
- `kg.jsonld.roundtrip` [MISSING] (#4756) — export → import → export is stable (the invariant
  test). Scope note: `test_jsonld_export_round_trips_to_isomorphic_graph` (cited above) proves
  only the SERIALIZE half of this invariant — reparsing Fichero's own JSON-LD reconstructs
  the same graph structurally. It does not cover the IMPORT half at all (no Fichero-side
  importer exists yet, `kg.jsonld.import` above), nor a real export→import→re-export cycle.

### B. Enrichment sources — unified in Settings, ALL selectable
- `kg.enrich.sources.settings` [PARTIAL] (#4757) — Settings has SPARQL endpoints; extend to a
  unified **Enrichment Sources** area where **every source below is individually
  togglable + configurable** (endpoint/API key where needed), under the external-
  enrichment master switch. Ruling (creative director, 2026-09-09): **all selectable.**

#### The authority-source catalogue (what each is, why it's here)

**The hub**
- **Wikidata** — free, universal, structured knowledge base (QIDs). Covers people, places,
  works, organizations, concepts, dates. It cross-links to almost every other authority
  below (a Wikidata item carries its VIAF/GeoNames/Getty ids), so it's the natural **default
  hub**: enrich from Wikidata, then follow its `sameAs` links out to the specialists.
  *Already built.* Best general default.

**People, organizations, works (name authorities)**
- **VIAF** (Virtual International Authority File) — aggregates the name-authority files of
  national libraries worldwide into one id per person/corporate-body/work. The standard for
  disambiguating a *named person* ("which Juan Pérez?"). Free.
- **LoC / LCNAF + LCSH** (Library of Congress Name & Subject Authorities) — US library
  standard for names and subject headings. Strong for published works and topical subjects.
- **GND** (Gemeinsame Normdatei, German National Library) — persons/works/subjects/places;
  the strongest authority for German-speaking and much European material.
- **ISNI** — International Standard Name Identifier for public identities (persons/orgs);
  bridges the publishing and library worlds.

**Places (gazetteers)**
- **GeoNames** — the go-to gazetteer for **modern** places worldwide: coordinates,
  administrative hierarchy, alternate names, population. Free (needs a username/key).
- **Pleiades** — the authoritative gazetteer of the **ancient** Greco-Roman world; essential
  for classics/ancient-history material where modern gazetteers have nothing.
- **Getty TGN** (Thesaurus of Geographic Names) — places both current and **historical**,
  with art-historical depth (former names, historical polities) — good for the gap between
  "ancient" and "modern".
- **Nominatim / OpenStreetMap** — free geocoding for coordinates; *already used* in
  `media/geo.py` as the online fallback behind the offline gazetteer.

**Concepts, materials, makers, periods (thesauri)**
- **Getty AAT** (Art & Architecture Thesaurus) — controlled vocabulary for object types,
  materials, techniques, styles — for describing *what a thing is*.
- **Getty ULAN** (Union List of Artist Names) — artists/makers/studios.
- **PeriodO** — a gazetteer of **historical periods** (named time-spans with definitions);
  a time authority to complement the place authorities.

**Domain-specific (opt-in, for specialist collections)**
- **Nomisma** — numismatics (coins/mints/denominations) — for numismatic archives.
- **WorldCat / OCLC** — works and editions (bibliographic).

**Recommended defaults for Fichero's historical-archive use** (all still selectable):
Wikidata (hub, on) · VIAF (persons) · GeoNames (modern places) · Pleiades (ancient places) ·
Getty TGN (historical places) · Getty AAT (concepts) · PeriodO (periods) · Nominatim (geo
fallback, already on). The rest ship off-by-default, one toggle away.

- `kg.enrich.per-type` [MISSING] (#4758) — a source is offered for the entity types it serves
  (places → GeoNames/Pleiades/TGN; persons/orgs → VIAF/LoC/GND/ISNI; concepts → Getty AAT;
  periods → PeriodO), so the UI never suggests a nonsensical lookup.
- `kg.enrich.provenance` — every enriched value is authority-sourced + provenance-tagged
  with WHICH source (rides #4636), never indistinguishable from hand/AI values; a value can
  carry several `sameAs` ids at once (Wikidata + VIAF + GeoNames).

### C. Surface the enrichment/prediction UX everywhere
- `kg.enrich.ux` [PARTIAL] (#4759, → #4828) — Wikidata enrich preview/import + PyKEEN predictions have
  services + a review sheet; ensure they're reachable from the **entity inspector and the
  KG tables** (an "Enrich…" / "Suggested links" affordance), not only the Ontology browser.
  Confirmed unreachable (2026-09-18, → #4828, kg-tables milestone): `WikidataEnrichmentSheet`
  and `HeuristicReviewSheet` both lost their only entry point with the KG browser, KEPT not
  deleted. **Coupled to `kg/kg-entity-inspector.md`'s `kg.entity.authority-link-create`:** the
  Wikidata enrichment sheet's own comment says it builds on the authority link, so the two
  should re-mount together, not independently of each other.
- `kg.enrich.mcp-cli` [PARTIAL] (#4760) — expose enrich-preview/import + predict via MCP + CLI so
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

## Rulings + open questions

**Ruled (creative director, 2026-09-09):**
- **Sources: ALL selectable** — ship the full catalogue above, each individually
  togglable; the "recommended defaults" set is on out of the box, the rest one toggle away.
- **`@context`: selectable too** — offer schema.org / Linked Art / CIDOC-CRM as selectable
  export mappings (not a single hard-coded one), same spirit as the sources.

**Still open:**
- Validation strength: JSON-LD expand/compact only, or also SHACL shapes (and who authors
  the shapes)? *(Recommend: expand/compact always; SHACL where a shape is declared.)*
- Does JSON-LD import create a separate "imported" provenance layer distinct from Wikidata-
  enrichment claims? *(Recommend: yes — import provenance = the file/source, distinct from
  live-authority enrichment.)*

Ties: #4641 (authority/Web of Data), #4640 (exporter — add JSON-LD beside JSONL), #4636
(provenance for enriched/imported values), #4624 (KG tables surface the affordances),
`archival-data-model-plan.md` P8 (authority/linked data).
