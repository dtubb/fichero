# KG Readable Representation — narrative biographies from claims — Design Spec (#TBD)

> Design-led (Testing Constitution). **Status: DRAFT — awaiting creative-director approval.**
> (A DRAFT needs no Milestone yet; declare one on approval — see TEST-TEMPLATE.md.)
> Tags: [OK] built · [PARTIAL] exists, extend · [MISSING] not built.

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
Deterministic composition is the floor (testable, always available offline); an optional LLM polish
pass (narrative_v1) may smooth prose but may not introduce any claim the deterministic layer
didn't license. Output is **bilingual** (Spanish + English) from one abstract representation.

## Behaviors

- `kg.read.order.chronological` [MISSING] — claims ordered by their event/attestation date
  (undated claims sectioned at the end, not dropped), so a life reads front to back.
- `kg.read.order.by-source` [MISSING] — claims grouped by source document (fondo → legajo →
  expediente order), so a reader can follow one record at a time.
- `kg.read.biography` [PARTIAL] — an entity-scoped multi-claim life narrative (extends
  `paragraph.py` from paragraph to biography: sectioning, connective prose, dedup across claims).
- `kg.read.genre.regest` [MISSING] — one dated paragraph per document, in order (calendar of docs).
- `kg.read.genre.gazetteer` [MISSING] — a place's assertions gathered as an entry.
- `kg.read.genre.index-concordance` [MISSING] — name/term → its attestations, sorted.
- `kg.read.confidence-visible` [MISSING] — each claim's confidence surfaces in the prose
  (hedge words / a marker / a separate "less certain" section), the Six-Degrees lesson: inferred
  edges must show their confidence. Never render a low-confidence claim as flat fact.
- `kg.read.provenance-linked` [OK, extend] — every statement keeps its citation marker → source
  anchor (paragraph.py already does markers; ensure biography-scale keeps them 1:1).
- `kg.read.no-fabrication` [MISSING, hard] — the LLM polish layer may reorder/smooth but MUST NOT
  add a claim absent from the deterministic input; a guard test diffs claim-set in vs out.

## Build: the Reiter & Dale NLG pipeline (six small, testable Python stages)

The classic NLG pipeline decomposes into six stages, and **each is a small pure function with its
own unit test** — which is exactly why this whole feature is headless-testable:
1. **Content determination** — which factoids belong in this entry (by entity, date range, genre).
2. **Document structuring** — order/section them: chronological, by life-stage, or by theme
   (family / property / litigation). (= `kg.read.order.*`)
3. **Aggregation** — collapse repetition: "seven witness appearances" → one sentence with a count
   and a place distribution. (extends `_group_claims`)
4. **Lexicalisation** — each (event-type, role) pair → a verb phrase, in Spanish AND English.
5. **Referring expressions** — full name on first mention, surname after, pronoun within a paragraph.
6. **Realisation** — agreement + morphology. Jinja2 goes far; **RosaeNLG** handles Spanish agreement
   (browser/node), **SimpleNLG-ES** is the Java realiser for grammar guarantees, Grammatical
   Framework is the heavyweight bilingual option. Start with Jinja2 + deterministic rules; adopt a
   realiser only when Spanish gender/number agreement actually bites (ponytail: don't add it early).

`paragraph.py` already implements a thin slice of stages 3–6 for a single paragraph; this spec
extends it stage by stage to entry/biography scale, each stage landed test-first.

## Test matrix (BACKEND-heavy — this is why it's the right headless target)

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (py) | y | ordering (chronological/by-source), grouping, hedging by confidence | `fichero-server/tests/unit/knowledge/test_readable_representation.py` |
| Backend (pytest) | y | the render endpoint returns ordered prose + markers for a seeded entity | `fichero-server/tests/…` |
| No-fabrication guard (py) | y | LLM-polished output introduces no new claim vs deterministic input | same |
| Availability (Swift) | y | the reader surface wires the readable render | `fichero/Tests/Unit/**` |
| Snapshot (Swift) | y | a biography renders legibly (chronological + by-source states) | `fichero/Tests/Unit/**` |
| Click-around (XCUITest) | y | open an entity → read its biography → click a citation → its source | `fichero/Tests/UI/**` |

Hard-gate: `kg.read.no-fabrication` (integrity — the AI-as-instrument north star) and
`kg.read.provenance-linked` (every statement traceable).

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

## Open questions for the creative director
1. Default ordering for a biography — chronological, or by-source? (Both are behaviors; which is
   the default a reader lands on?)
2. How should confidence read in prose — hedge words, a visible marker, or a separate section?
3. Is the LLM polish layer on by default, or is deterministic prose the shipped default with
   polish opt-in? (Integrity leans deterministic-default.)
