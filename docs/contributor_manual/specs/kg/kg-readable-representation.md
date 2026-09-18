# KG Readable Representation — narrative biographies from claims — Design Spec (#TBD)

> Milestone: kg-readable-representation
>
> Design-led (Testing Constitution). **Status: APPROVED — 2026-09-10.**
> Tags: [OK] built · [PARTIAL] exists, extend · [MISSING] not built.
>
> **Scope boundary:** this specs HOW the readable representation is BUILT — a deterministic,
> background, backend NLG pipeline over the existing KG. It is NOT the document inspector
> (`kg-entity-inspector.md`), which is the display *interface*; that surface consumes what this
> produces. Two hard constraints: (1) **NO LLM generation anywhere in the path** — rendering is
> 100% deterministic from stored claims (the current `narrative_v1` LLM prompt "makes it up" and
> is the thing being replaced); (2) **any language**, not just Spanish/English.

## Why this spec exists

The KG is truth-bearing but reads like a database: dot-separated triples, review tables, and
(the least useful view) a hairball graph. A reader — a historian, the person whose life the
records describe — wants **readable English**: a biography ordered the way a writer would order
it (chronologically, or grouped by source), with every statement still carrying its evidence.
The goal is *programmatic but writerly* prose that never fabricates and never hides uncertainty.

This is a **backend text-generation** concern (claims + sources → ordered prose), which makes it
deterministic and **fully unit-testable without a GUI** — the right first target while the app
build is blocked. It iterates on what already exists; it does not replace it.

## What already exists (iterate, don't replace)

- `fichero-server/src/fichero_server/knowledge/paragraph.py` — deterministic claim→prose with
  `ParagraphStyle` (`narrative` / `list` / `footnoted`), superscript citation markers,
  `_claim_sentence`, `_group_claims` (merges mergeable claims), and subject/verb/object ordering
  via `knowledge/_common.py` (`order_statement_parts`, `render_statement`).
- `resources/prompts/catalogue/narrative_v1.md` — the LLM narrative prompt (the polish layer).
- `api/routes/entity/inspector.py`, `entity/entities.py` — entity-scoped read surfaces.
- Swift `Models/ClaimLine.swift` — the app's clause rendering (recent fix: trim run-on person
  spans / entity display names read naturally — commits 444dfc6c0, 9eeef2114).

## Theoretical grounding (this is an old, respectable practice)

Historians have rendered archives as readable text for two centuries; the genres have unfashionable
names but each is a **deterministic text rendering of a graph**, and Fichero can generate them all:
- **regest / calendar** — one dated paragraph per document, in order.
- **prosopographical entry** — a person's assertions gathered; **a biography is this done well**.
- **gazetteer entry** — a place's assertions gathered.
- **index nominum / concordance** — name/term → attestations.

The rigorous model underneath is **Bradley & Short's factoid model**: you never store "facts about
a person," you store **assertions a source makes** — each with date, place, role, citation. That is
*already what the extraction pipeline produces* (a `KnowledgeClaim` is a factoid: subject/verb/
object + source anchor + confidence), which is why this is cheap for Fichero — the data is right.
Precedents: Gramps narrative reports (GEDCOM→sentences+citations, decades old); Lsjbot (millions of
template articles — shows both the scale AND the flatness you get if you stop at templates); Abstract
Wikipedia + Grammatical Framework (Wikidata→multilingual via functions/lexemes — the serious bar).

## Intent (the design)

Given an entity (or a set), render a **biography** (or any genre above): readable prose composed
from its claims/factoids, under a chosen **ordering** and **grouping**, with citation markers
linking every statement to its source anchor, and with **uncertainty shown, not hidden**
(low-confidence or contradicted claims are marked, hedged, or sectioned — never silently asserted).
Composition is **100% deterministic** — no LLM in the path, ever — computed in the **background**
(like embeddings) and stored, not generated on demand in a web request. The rendered prose is in
**the language of the SVO/claim itself** — i.e. the language of the source the factoid was
extracted from (a claim from a Spanish document renders Spanish, a French source French); the
representation is multilingual *because the sources are*, so realisation must be language-aware
per claim, not a fixed language pair.

## Behaviors

- `kg.read.order.chronological` [PARTIAL, unwired] — claims ordered by their event/
  attestation date (undated claims sectioned at the end, not dropped), so a life reads
  front to back. The function exists and is unit-pinned, but `order_claims`
  (`fichero-server/src/fichero_server/knowledge/readable.py:89`) has ZERO callers outside
  itself/its own tests — nothing in the API routes wires it to a request, so the ordering
  is not reachable by a reader today. Pinned:
  `fichero-server/tests/unit/knowledge/test_readable_representation.py`
  (`test_chronological_orders_by_time_start`, `_puts_undated_last_and_stable`,
  `_falls_back_to_date_values_when_no_time_start`, `_uses_earliest_of_multiple_date_values`).
- `kg.read.order.by-source` [PARTIAL, unwired] — claims grouped by source document
  (fondo → legajo → expediente order), so a reader can follow one record at a time. Same
  gap as `order.chronological`: `order_claims` has no caller outside its own tests, so
  this mode is not wired to the biography route either. Pinned:
  `test_readable_representation.py` (`test_by_source_groups_by_document_then_offset`,
  `_puts_sourceless_claims_last`).
- `kg.read.biography` [PARTIAL] — an entity-scoped multi-claim life narrative (extends
  `paragraph.py` from paragraph to biography: sectioning, connective prose, dedup across claims).
- `kg.read.genre.regest` [MISSING] — one dated paragraph per document, in order (calendar of docs).
- `kg.read.genre.gazetteer` [MISSING] — a place's assertions gathered as an entry.
- `kg.read.genre.index-concordance` [MISSING] — name/term → its attestations, sorted.
- `kg.read.confidence-visible` [MISSING] — certainty surfaces as **hedge words + corroboration**
  (ruling 2): hedge words tuned to confidence, PLUS a triangulation signal — how many independent
  sources assert the factoid and whether any contradict — and always the linked sources. The
  point is to show the render is evidence, not an oracle; a bare confidence dot/number can mislead
  (reads as an invented score), so corroboration is the primary device. Six-Degrees lesson:
  inferred edges must show their confidence. Never render a single-source low-confidence claim as
  flat fact.
- `kg.read.provenance-linked` [OK, extend] — every statement keeps its citation marker → source
  anchor (paragraph.py already does markers; ensure biography-scale keeps them 1:1).
- `kg.read.cite-to-segment` [MISSING] — a citation resolves not just to a document/page but to the
  **page SEGMENT** (the bbox/region the claim was extracted from), so a click lands the reader on
  the exact spot in the source. The `SourceAnchor` already carries region data — the marker must
  round-trip to it.
- `kg.read.expose-kg-on-hover` [MISSING] — hover/click on a statement reveals **what the KG knows**
  behind it — location, dates, roles, confidence, the raw SVO — rendered readably (not raw JSON),
  as the bridge from prose back to structure back to source.
- `kg.read.audit-history` [MISSING] — expose the factoid's HISTORY, not just its current state:
  the original extracted names before canonicalisation, how entities were merged (`merged_into_id`),
  the `curation_state` (blessed / rejected / merged) and who/when (`created_by`, `created_at`,
  `attribution_chain`). Much of this is already stored — the render surfaces it readably so a
  reader can see how a factoid came to read the way it does, not just trust it.
- `kg.read.generation-provenance` [MISSING] — the render is no-LLM, but the underlying CLAIM was
  extracted by a model+prompt+run; that generation provenance (which model, which prompt version,
  which run) is exposed alongside the source, so a reader sees not just *where* the factoid came
  from but *how it was made*. Ties to run-scope provenance logging.
- `kg.read.no-llm` [MISSING, hard] — NO generative model anywhere in the path. Every sentence is
  produced by deterministic rules/templates/grammar from stored claims; a guard test asserts the
  render module imports/calls no LLM client and that output is a pure function of its claim input.
- `kg.read.language-of-svo` [PARTIAL] — each sentence renders in the language of its claim/SVO
  (the source's language); connective/structuring prose follows the entity's dominant claim
  language. Never machine-translate a claim into another language (that would be fabrication).
  Spanish and English realisation are proven: `test_realises_single_claim_in_spanish`,
  `test_realises_aggregated_count_and_places_in_english`,
  `test_unknown_language_falls_back_to_english_glue`.
  Pinned: fichero-server/tests/unit/knowledge/test_readable_representation.py::test_realises_single_claim_in_spanish,
  fichero-server/tests/unit/knowledge/test_readable_representation.py::test_realises_aggregated_count_and_places_in_english,
  fichero-server/tests/unit/knowledge/test_readable_representation.py::test_unknown_language_falls_back_to_english_glue.
  UNtested: a third language requires only a new lexicon table (no code change) — this
  extensibility claim itself has no test proving a third language "just works" without code.
- `kg.read.background` [MISSING] — the representation is computed in the background and stored
  (auto-throttled, like embeddings — the machine stays usable), not synthesized per web request.

## Build: the Reiter & Dale NLG pipeline (six small, testable Python stages)

The classic NLG pipeline decomposes into six stages, and **each is a small pure function with its
own unit test** — which is exactly why this whole feature is headless-testable:
1. **Content determination** — which factoids belong in this entry (by entity, date range, genre).
2. **Document structuring** — order/section them: chronological, by life-stage, or by theme
   (family / property / litigation). (= `kg.read.order.*`)
3. **Aggregation** — collapse repetition: "seven witness appearances" → one sentence with a count
   and a place distribution. (extends `_group_claims`)
4. **Lexicalisation** — each (event-type, role) pair → a verb phrase, in **the claim's language**
   via a per-language lexicon table (add a language by adding a table, not code).
5. **Referring expressions** — full name on first mention, surname after, pronoun within a paragraph
   (pronoun/agreement rules are per-language).
6. **Realisation** — agreement + morphology, per language. Library landscape (researched 2026-09-10,
   for a Python backend):
   - **Default (ponytail): Jinja2 + per-language lexicon/rule tables** — deterministic, zero new
     deps, exactly how `paragraph.py` already works. **The active language(s) come from the
     project/collection setting (ruling 3), not a hardcoded list** — each language is a data table
     loaded on demand; the current corpus seeds Spanish, but nothing in code assumes it. Lsjbot
     proves this scales (and warns of flatness — mitigated by aggregation + referring-expression
     variation, stages 3 & 5).
   - **Any-language escalation: Grammatical Framework** via the `pgf` Python runtime — one abstract
     tree → concrete grammars per language; this is what **Abstract Wikipedia** uses. The principled
     answer when a language's morphology outgrows rule tables. Heavy (write grammars) — adopt only
     when it earns its keep.
   - **pyrealb** — native-Python (no bridge), realizes EN+FR deterministically; a light step if EN/FR
     realisation is needed before committing to GF.
   - **SimpleNLG-ES** (Java, via server/bridge) — mature Spanish realiser if the ES rule tables prove
     too weak before GF is worth it.
   NEVER translate a claim across languages — render each in its own (the `_en` fields are a
   pre-existing extraction-time translation, usable for an English rendering, not a license to
   translate other languages).

`paragraph.py` already implements a thin slice of stages 3–6 for a single paragraph; this spec
extends it stage by stage to entry/biography scale, each stage landed test-first.

**Prior art to build on (RDF/linked-data crowd — researched 2026-09-10):** the semantic-web
community verbalizes graphs to text with **LD2NL / SPARQL2NL / SemWeb2NL** (rule+template RDF→text),
whose pipeline (lexicalization → single-triple realization → clustering → ordering → grouping)
*mirrors Reiter-Dale* — independent confirmation the deterministic path is sound. **CIDOC-CRM** is
the ISO ontology the cultural-heritage crowd uses for exactly this factoid substrate (events,
actors, places, times); our factoids map to it, so they can be imported from / exported to an RDF
server as linked open data (cf. Enslaved.org). The readable render must work over a factoid whether
it came from the extraction pipeline OR an RDF import — same substrate, same rendering.
**CIDOC-CRM import/export itself is LATER — it belongs to the import/export engine, not this spec.**
This spec keeps the DH deterministic approach (working well: stages 1-3 shipped, 12 tests green);
CIDOC-CRM I/O is a separate future milestone.

## Test matrix (BACKEND-heavy — this is why it's the right headless target)

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (py) | y | ordering (chronological/by-source), grouping, hedging by confidence | `fichero-server/tests/unit/knowledge/test_readable_representation.py` |
| Backend (pytest) | y | the render endpoint returns ordered prose + markers for a seeded entity | `fichero-server/tests/…` |
| No-LLM guard (py) | y | render module calls no LLM client; output is a pure function of its claims | same |
| Multilingual (py) | y | a claim renders in ITS language; adding a language = adding a lexicon table | same |
| Availability (Swift) | y | the reader surface wires the readable render | `fichero/Tests/Unit/**` |
| Snapshot (Swift) | y | a biography renders legibly (chronological + by-source states) | `fichero/Tests/Unit/**` |
| Click-around (XCUITest) | y | open an entity → read its biography → click a citation → its source | `fichero/Tests/UI/**` |

Hard-gate: `kg.read.no-llm` (integrity — the AI-as-instrument north star; no fabrication) and
`kg.read.provenance-linked` (every statement traceable to its source).

## Related vision — NOT this spec (future, separate specs)

The user's DH survey maps future **visualization** surfaces; each is its own spec when taken up.
Captured here so the research isn't lost, deliberately out of scope for the readable-text spec:
- **Finding-aid graphs** (ego networks, confidence-scored edges) — Six Degrees of Francis Bacon,
  Linked Jazz, CBDB. Grape (Swift d3-force port) or sigma.js in the new SwiftUI `WebView`.
- **Time axis** — storyline/arc/attestation timelines; Digital Panopticon life-courses; Swift
  Charts rule/bar marks; deck.gl TripsLayer for movement.
- **Map + graph** — Chocó terrain (Copernicus/SRTM DEM), HydroRIVERS, Codazzi/Comisión
  Corográfica sheets georeferenced via Allmaps (IIIF), HGIS de las Indias jurisdictions; MapLibre
  GL (web, shareable) embedded via `WebView`, native `Map(.mapStyle(.hybrid(elevation:)))` for
  the light in-app view.
- **Matrices** — reorderable co-occurrence heatmaps (Swift Charts `RectangleMark`); hierarchical
  edge bundling onto fondo→legajo→expediente.
- **Embedding space** — Chart3D (macOS 26) or Nomic-Atlas-style zoomable map of the sqlite-vec
  vectors.
- **RealityKit space-time cube** — Chocó map on the floor, time up, trajectories threading mines
  and towns (Hägerstrand); exports USDZ/glTF for sharing. Earns 3D only when the third axis means
  something.
- **Architecture principle** (from the survey): Python owns layout (networkx/igraph/Graphviz/UMAP
  → x,y,z,t in SQLite); the app draws coordinates (SwiftUI Canvas); the SAME coordinates feed a
  web front end (FastAPI) so the Mac view and the shareable link never drift.

## Cross-surface & authoring (the invariant to hold — audit tracked separately)

The factoid substrate is rich (audited 2026-09-10: who-asserts, date, place, role, citation,
Toulmin, confidence, language, generation-provenance all present). The open concern is whether
every dimension we can STORE is also: (a) visible in the UX (KG tables / inspector), (b)
**authorable by BOTH a person (manual) and the extraction pipeline (LLM)** — never LLM-only, and
(c) tested end-to-end (backend ↔ MCP ↔ CLI ↔ UX — the Constitution's hard-gate invariant). This
readable rendering is a READ view of that substrate; the authoring/visibility audit belongs to
`kg-tables.md` / `kg-entity-inspector.md`. Tracked, not assumed.

**Idea (Abstract Wikipedia / GF):** multilingual NLG organized into abstraction levels lets code
be shared across languages and splits labour between programmers (grammars) and authors (content);
a **Controlled Natural Language** puts a human in the loop to author/correct factoids in
constrained prose that round-trips to structure. A candidate future authoring path — deterministic,
no-LLM, and the same abstract representation the render reads.

## Rulings (creative director, 2026-09-12)

1. **Default ordering = chronological, changeable.** A reader lands on the chronological
   reading; a control switches to by-source. Either way **every statement always shows its
   source and date** — a click on any statement opens its provenance (source anchor →
   `kg.read.cite-to-segment`). Ordering is a lens over the same evidence, never a filter that
   hides it. (Resolves `kg.read.order.chronological` as the default; `by-source` is the toggle.)

2. **Confidence reads as hedge words AND triangulation — the point is "this is not magic."**
   Default to hedge words in the prose ("is said to have", "probably"), but the surface must make
   clear the render is evidence, not an oracle. A bare confidence *dot/number can mislead* (it
   reads as a made-up score), so express certainty primarily through **corroboration /
   triangulation** — how many independent sources assert the same factoid, and whether any
   contradict — not just the stored per-claim confidence. So `kg.read.confidence-visible`
   surfaces: (a) hedge words tuned to confidence, (b) the corroboration count ("three sources
   agree", "only one source, uncorroborated", "sources disagree"), and (c) always the linked
   sources themselves. A separate "less certain / disputed" section is allowed but is not the
   primary device. Never render a single low-confidence, single-source claim as flat fact.

3. **Realisation language is GENERIC and chosen at onboarding — no hardcoded language list.**
   This is a Python-backend concern and must not bake in Spanish/English. The active
   language(s) are a **user setting picked at onboarding, per project — and settable per
   collection**. The per-language lexicon/rule tables are data (a table per language), loaded for
   whatever language(s) the project/collection declares; adding a language is adding a data table,
   never code (see stage 4/6 below). Connective/structuring prose follows the entity's dominant
   *claim* language, but the set of languages the pipeline realises is driven by that
   project/collection setting, not by a fixed pair. (Claims themselves always render in their own
   language regardless — `kg.read.language-of-svo`.) The current corpus is Spanish-first, but that
   is a *setting value*, not a code assumption — the design ships generic and seeds Spanish.
