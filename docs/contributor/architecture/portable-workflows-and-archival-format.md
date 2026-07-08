(AI generated. Not reviewed.)

# Portable Workflows + Archival Interchange Format

Status: **design** (2026-06-04). Source of truth for the import/export + supercomputer
architecture. Issues: #1643–#1648 + the additions below.

## The idea in one line

Fichero workflows are **LangGraph/LangChain DAGs** — portable Python. So we can
**export a workflow as a runnable project**, run the *same code* anywhere (e.g. a
supercomputer loading Qwen2-VL instead of Apple on-device), have it **write its own
DuckDB** (Fichero schema) and/or **standard archival files (IIIF + W3C annotations)**,
and **import that back** into a Fichero library. Plus first-class **export** of the
knowledge graph (RDF/JSON-LD/W3C). No reimplementation, no invented format.

```
Fichero library
   │  export workflow project (LangGraph + inputs + model config)
   ▼
Run anywhere (cluster / supercomputer)        ── same LangGraph code, model = Qwen2-VL via LangChain
   │  writes: DuckDB (Fichero schema)  AND/OR  IIIF manifests + W3C annotation pages
   ▼
Import our format  ───────────────────────────▶  back into a Fichero library
   │
   ▼
Export (any time): RDF / JSON-LD / W3C annotations / IIIF
```

## Two layers, two standards (do not conflate)

1. **Source / archival layer** — image + transcription + descriptive metadata + structure.
   Format: **IIIF Presentation 3.0** (JSON-LD). Fichero already serves IIIF (`/api/iiif`).
   - image = `painting` annotation on a Canvas
   - transcription = `supplementing` `TextualBody` annotation
   - metadata = `label` / `metadata[]` (Dublin Core terms) / `navDate` / `rights` / `seeAlso`
   - folder = `Collection`, document = `Manifest`

2. **Knowledge layer** — entities, claims, quotes, catalogue, attribution, disputes, confidence.
   Format: **RDF** (Fichero already builds it in `kg/triples.py`: entities = `skos:Concept`,
   claims = reified `rdf:Statement` with SVO predicates + `#1123` attribution/quotation fields).

3. **The bridge: W3C Web Annotation** — *anchoring only*. An annotation says **where** a
   thing is (`target` = Canvas `#xywh=` region or text span) and links to the RDF claim
   (`body.source` = claim URI). **SVO / confidence / dispute / attribution live in RDF, not
   in the annotation.** W3C anchors; RDF structures.

## Bounding boxes (so we can highlight)

Both engines give boxes — we just need to keep them:
- **Apple Vision** (`vision_base.py`): `VNRecognizeTextRequest` → `observation.boundingBox`
  (line) + `candidate.boundingBox(for: range)` (word). Today only `.string()` is kept (#1644).
- **Qwen2-VL** (cluster): grounding VLM — emits bboxes + transcription + entities directly.

Geometry → W3C annotations (`#xywh`) → `Annotation.bbox` / `claim.bbox`. Enables
reveal-region-on-image across canvas + WebKit + inspector (#1643).

## Regions, derivation, two-page scans, maps (#1647)

One primitive covers all of it: **a document/annotation is a region of a source image.**
Model already has it: `Document.derived_from`, `Document.bbox`, `DocType.chunk`,
`Annotation.bbox` ([x,y,w,h] fractions).

- A scanned **two-page opening** (IMG_003) → import the **original** + the split
  **left/right** pages (IMG_003_part_1/2), each with `derived_from = IMG_003` and `bbox =`
  its crop region (geometry is in the corpus `split_manifest`). UI reads left/right; "reveal
  in original" highlights the region.
- A **map section** = a `chunk`/annotation with a `bbox` on the map image. Same primitive.

## The portable workflow project (#1648 — reframed: LangGraph, DuckDB)

Fichero exports a self-contained, runnable project from a workflow:

```
project/
  workflow/graph.py        # the actual LangGraph DAG (same code Fichero runs)
  workflow/prompts.json     # the node prompts
  model.json                # {"provider":"qwen2-vl","model":"Qwen/Qwen2-VL-72B-Instruct", ...}
  inputs/manifest.jsonl     # images to process (refs or copies)
  run.py                    # builds the graph, sets the LangChain model provider, loops inputs
  requirements.txt / env/   # reproducible environment (or a container)
  out/                      # written by the run:
     library.duckdb         #   Fichero-schema DuckDB (Documents/Entities/Claims/Artifacts)
     iiif/<id>.json         #   AND/OR IIIF manifests + W3C annotation pages
  OUTPUT_CONTRACT.md        # what the run must produce
```

Key points:
- **Same code.** The graph is Fichero's LangGraph workflow, not a port. Only the **LangChain
  model provider** is swapped (Apple on-device → Qwen2-VL via vLLM/transformers → OpenAI).
  This is what makes "run our workflows on another computer" literally true.
- **Writes a DuckDB** in the Fichero schema (or canonical IIIF+W3C files). The cluster owns no
  Fichero engine — it just produces data.
- **Round-trips** via the importer below.

## Importers (#1646 + additions)

1. **Old custom-fichero format → IIIF + W3C** (the "import our old projects" converter).
   Input: the legacy `canonical-output` / processed-corpus assets (transcripts +
   `llm_catalogue` entities/claims/quotes + background_removed images + metadata). Output:
   IIIF manifests + W3C annotation pages. **Reuses precomputed extraction — no re-run.**
2. **IIIF + W3C importer** → Fichero docs + `page_content` + `claim.bbox` + entities.
3. **Cluster-output importer** → merge the project's `out/library.duckdb` (or its IIIF+W3C)
   into a Fichero library. (Same code path as #2 when the cluster emits IIIF+W3C; a DuckDB
   merge path when it emits DuckDB.)

## Exporters (#1645)

Over the rdflib graph that already exists (`kg/triples.py`):
- `GET /api/kg/export?format=turtle|jsonld|ntriples` → the SVO/confidence/attribution graph.
- `GET /api/kg/export?format=w3c-annotations` → claims/quotes/entities as anchors (body →
  RDF claim, target → source doc + `bbox`).
- Documents → IIIF (already served).

## Does this capture everything we have? (materials coverage)

| Material we hold | Where it lives in the format |
|---|---|
| Original scan image | IIIF Canvas (painting annotation) |
| Cleaned / background-removed image | Canvas image; `derived_from` for splits |
| Transcription (clean text) | `supplementing` TextualBody annotation → `page_content` |
| Text bounding boxes | W3C annotations `#xywh` → `Annotation.bbox` |
| Descriptive metadata (title/date/source/rights/identifier) | IIIF `metadata[]` (Dublin Core), `navDate`, `rights`, `seeAlso` |
| Entities (people/places/orgs/…) | RDF `skos:Concept` + W3C `tagging` anchor |
| Claims (SVO) | RDF reified `rdf:Statement` (+ W3C anchor) |
| Quotes | claim w/ `quotation_kind`/`speaker` → annotation w/ quoted body |
| Catalogue entry (per-doc extraction) | artifact + RDF statements |
| Attribution chain / sources | RDF (PROV-O) + `source_supports` |
| Confidence / dispute | RDF statement properties |
| Page/folder structure, order | IIIF Collection/Range, `sort_order`, `structure` |
| Processing provenance (bg-removal params, sizes…) | IIIF annotation/metadata + Fichero `metadata{}` |

## Is it extensible? (more entities, quotes, future extractions)

**Yes — additive, no migration**, because every layer uses *open containers*:
- **Entity types** → user-extensible registry (#874) — add a type, no schema change.
- **New claim/quote kinds** → new SVO predicates / `quotation_kind` values; RDF is open.
- **New extraction outputs** (sentiment, marginalia, places-mentioned, …) → new
  **`artifact_type`** and/or new **annotation `motivation`** + body; `metadata{}` is free-form.
- **New standards** → the IIIF/W3C/RDF stack is designed for extension (`@context`, custom
  motivations, additional vocabularies).

So deciding later to extract "more entities, or quotes, or other stuff" means a new workflow
node + a new artifact/annotation type — the format and the DuckDB schema's open fields absorb
it without breaking existing data.

## Issue map

- #1643 UI reveal region (canvas + WebKit + inspector)
- #1644 Apple Vision: capture bounding boxes
- #1645 KG export endpoints (RDF / JSON-LD / W3C annotations)
- #1646 IIIF + W3C importer
- #1647 `derived_from` + `bbox` (two-page scans, maps)
- #1648 Portable LangGraph workflow project (same code, Qwen2-VL, writes DuckDB)
- **NEW** Old-custom-fichero-format → IIIF + W3C converter (import our existing projects)
- **NEW** Cluster-output importer (DuckDB / IIIF+W3C → Fichero library)
- **NEW** Extensibility guarantees (entity-type registry + open artifact/annotation/metadata)
