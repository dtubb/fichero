# Archival Data Model — Development Plan

> Manual: TBD — the user manual needs a "How Fichero stores what it reads" section: what a
> segment is, how a page's regions/lines/words relate, and why that shape lets a claim point back
> at the exact ink it came from. Written for a researcher, not a developer.
>
> **Status: DRAFT for discussion** (Fichero creative director, 2026-09-08 night).
> This consolidates the segment/archival design captured across issues #4635–#4642
> and #1755 into ONE staged plan to develop and then talk through. Design-led
> (Testing Constitution): nothing here is built until the creative director approves
> the slice. Epic index: **#4639**.

---

## 1. The two models and the one hinge

Everything below serves a **dead-simple user model** on top of a **rich data model**.
They never leak into each other; the **Profile** is the only translator.

### User model (what a person touches)
`Document → Page → Profile → Transcription (in an Edition) → Entity/Claim → Source → Credit → Tags`.
A small vocabulary. Depth is disclosed only when a scholar reaches for it (progressive
disclosure): a casual user does import → transcribe → read → search and never sees a
segment, an RDF triple, or a provenance chain.

### Data model (what is stored)
One primitive — the **Segment** — and every record hangs off it. Every record
(Segment, Transcription, Representation, Claim, Entity, Annotation, Zone, Tag) carries
the **same four invariant slots**:

| Slot | Meaning |
|------|---------|
| **anchor** | WHERE — geometry/time on which medium, + layer + reading order |
| **language + script** | WHAT system — coverage tier, direction |
| **provenance + version + credit** | HOW it got here — actor (model/human), reasoning, restorable history |
| **export map** | HOW it leaves — mapping to ALTO/PageXML/TEI/JSON-LD/Linked Art/… |

A new format or challenge is a new value in one slot, **not** new schema.

### The hinge: Profile
`medieval-manuscript · damaged-archive · papyrus · printed-book · modern-typescript · …`
One choice loads the right **segmenter + runtime/model + edition + transcription
guideline + condition-handling**. The user picks (or Fichero detects) the profile; the
deep machinery configures itself. This is how the whole model reaches the user without
exposing its complexity.

---

## 2. The delivery contract (non-negotiable)

A capability is **DONE only across the whole spine**:

> **backend → inspector/front-end → AI (MCP) + CLI → tested → exportable**

- Backend row alone = not done.
- UX without MCP/CLI = not done.
- Untested (esp. the cross-surface invariant) = not done.
- Not exportable = not done.

Every phase below is a **vertical slice** that crosses the whole spine for a small piece,
never a horizontal layer that builds backend-only breadth. The acceptance test for each
capability is the **do-it / represent-it / save-it** trio plus MCP/CLI + export.

---

## 3. The primitive: Segment (spatial AND temporal)

A **Segment** is any addressable slice of any medium — this is **W3C Media Fragments**:

- **spatial** (image / PDF): polygon / `#xywh=x,y,w,h`
- **temporal** (audio / video): time span / `#t=start,end`
- **both** (video): region + time
- **geographic** (georeferenced map, #1755): lat/lon + warp transform

Granularity ladder: `stroke → glyph → character → word → line → region → page-part → page`.
Surface for creating/editing a segment = the **Preview (source) pane** (#168): the polygon
is drawn and adjusted **on the media**. The inspector shows a segment's metadata/versions.

Existing infra to build ON (not replace): `_segment_image` crop, the Kraken segmenter
that persists baseline geometry, recombine/contact-sheet.

---

## 4. The layers (all are versioned collections at the segment grain)

A segment holds **many, each versioned append-only**:

- **Transcription[]** — `{ text, language, script, edition, version, provenance }`.
  Language/script live HERE, not only on the segment (bilingual gloss = 2 transcriptions;
  graphemic vs normalized = 2 transcriptions). Editions: diplomatic / normalized /
  graphemic / graphetic (#4638).
- **Representation[]** — `{ kind, version, provenance }`, kind ∈ `image-crop · text ·
  tokens · image-vector · text-vector · glyph-rep(no-Unicode) · layout-features`.
  The consumer chooses which it wants (an AI asks image+text; an index asks vectors; an
  exporter asks text→ALTO).
- **Provenance/Rationale** — per version: the **model's reasoning** AND the **human's
  rationale**, not just the value. This makes plausible-readings-side-by-side possible and
  IS the training corpus (#4636, #4642).
- **Linguistic annotation** — token spans within a transcription: POS, lemma, morphology,
  dependency (CoNLL-U/UD). NER (entities) is the same mechanism (#4637).
- **Zones** — logical grouping ABOVE the page: a page typed as letter/response/deposition;
  a set of pages spanning multiple documents (a legal case); with **relationships**
  (reply-to, continues, part-of). Reading-order / correspondence layer (#4639).
- **Tags** — arbitrary labels (free or controlled-vocabulary) on any object at any grain
  (SKOS / W3C Web Annotation).

---

## 5. Staged development plan

Each phase is a vertical slice. **P0 proves the spine cheaply on existing data before any
new schema.** Later phases add breadth only after the pattern holds and is approved.

### P0 — Segment Representations read model (the proof slice)
*Spec: `segment-representations.md`. Milestone spread: Inspector-Knowledge-Engine #55 (backend),
Inspector-Knowledge #151 (inspector), Client-MCP #52 (MCP/CLI), Testing #267, Exporter #14.*
- **backend**: `segment.read.representations` → `image-crop` (via `_segment_image`) + `text`
  (existing transcription); read-only, honest-absence, no new schema.
- **inspector**: a segment shows its crop + text, anchored (reuse F5 `ClaimSourceRequest`).
- **MCP + CLI**: `segment.get(reps=image+text)` — hand an AI segments + images in one call.
- **tests**: rep-roundtrip + **cross-surface HARD-GATE** (same segment → same anchor/text
  from backend, MCP, CLI) + resource-safety.
- **export**: one segment's transcription → **ALTO** (or PageXML) with geometry intact.

### P1 — Segment editing on the Preview pane
- Draw/adjust the polygon on the image/PDF in the Preview pane; persist geometry as an
  audited, reversible action; changes update in place. (Builds on #168 bbox work.)

### P2 — Transcriptions as versioned collection + editions
- Promote transcription to a first-class versioned record with language/script/edition;
  show the version stack; **plausible-readings side-by-side**; capture reasoning on each
  version (P4 dep). Editions picker (diplomatic/normalized/…). (#4638)

### P3 — Representation vectors
- `image-vector` / `text-vector` representations, versioned by embedding model; feed the
  search index. Resource-safety bounded (Search-Engine #186). (#4634 load-testing rides here.)

### P4 — Provenance, versions, rationale (cross-cutting)
- The full restorable history + the **reasoning field** (model + human) on every version,
  shown on the page and easy to edit. Actor roles extensible (extractor/editor/reviewer/
  end-user). This is #4636 — a candidate its-own-milestone; every layer rides it.

### P5 — Zones + relationships
- Logical groupings above the page (letter→response; case across documents) with
  relationships; see/edit on the Preview pane; query via MCP/CLI; export TEI correspDesc /
  METS structMap / IIIF ranges. (#4639)

### P6 — Linguistic annotation (POS) + Tags
- Token spans + labels within a transcription (CoNLL-U/UD); general tagging (SKOS) across
  objects. (#4637 + the tags thread.)

### P7 — Language/script coverage + no-Unicode path
- loove coverage tiers; CLDR/Glottolog/UCD/UDHR; fonts-by-character; Unicode-space viz;
  the extreme case — a script with no encoding/no fonts works image-anchored with custom
  glyph representations and contributes toward encoding. (#4637)

### P8 — Authority linking + Web of Data
- `sameAs` sets to VIAF/Wikidata/GeoNames/Pleiades/Getty; dereferenceable URIs; SPARQL
  endpoint (make rdflib visible); JSON-LD/Linked Art; PROV/CIDOC-CRM. (#4641)

### P9 — Exporter Manager + folder sync + contribute
- One export path for all the slots/formats; index a folder / keep it in sync; package a
  repo; contribute data upstream; **training-corpus export** (feeds P10). (#4640)

### P10 — Distilled paleography VLM
- The versioned (image-crop → text → reasoning) corpus + human review → distill a small
  local "thinking" VLM (MLX) that emits its reasoning. (#4642)

### P11 — Georeference
- Old-map-on-new-map as a geographic anchor kind + warp transform; export GDAL/GeoTIFF/
  IIIF-georef/Linked-Art-place. (#1755)

---

## 6. Standards map (the export slot, by layer)

| Layer | Standards |
|-------|-----------|
| Anchor (spatial/temporal) | W3C Media Fragments, W3C Web Annotation selectors |
| Segmentation / geometry | ALTO, PageXML, hOCR, abbyyXML (Kraken outputs) |
| Transcription / editions | TEI, CATMuS guidelines, Leiden (papyri), ZOLO, MEI (music) |
| Linguistics | CoNLL-U / Universal Dependencies |
| Claims (RDF) | RDF/SPARQL, JSON-LD, Linked Art, CIDOC-CRM |
| Provenance | W3C PROV |
| Zones / structure | TEI msDesc/correspDesc, METS structMap, IIIF ranges/collections |
| Tags | SKOS, W3C Web Annotation |
| Authority | VIAF, Wikidata, LoC, GeoNames, Pleiades, Getty (TGN/AAT) |
| Package / interchange | IIIF, METS, BagIt |
| Georeference | GDAL world-file, GeoTIFF, IIIF-georef |

---

## 7. Open questions to talk through
- **Profile detection** — user-picked only, or auto-detected from the page? Editable after?
- **Where representations physically live** — derivative files (like `_segment_image`), a
  table, or both (file payload + metadata row)?
- **Is Transcription first-class now** (P2) or does P0 read the existing transcription text
  and defer the multi-edition table?
- **Store responsibility** — DuckDB (relational) vs LanceDB (vectors) vs rdflib/SPARQL
  (graph): which store owns which slot, and how they stay in sync (ties Exporter #4640)?
- **New milestones?** — "Segments & Anchors" and/or "Provenance, Versions & Credit", or
  keep everything under the existing surface milestones? (Decomposition on #4639.)
- **P0 export target** — ALTO or PageXML first?

---

## 8. Milestone decomposition
Design lane lives in **Historical Text (#265)**; each phase's build issues land in the
surface milestone that owns their spine segment — Inspector-Knowledge #151/#55, Client-MCP
#52, Search-Engine #186, Importer #188, Preview-Image-Editing #168, Exporter #14,
Settings-Models #20, Testing #267. Full mapping + the two proposed new milestones are on
**#4639** (awaiting the creative director's ack — no milestones created yet).
