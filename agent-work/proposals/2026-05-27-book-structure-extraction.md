# Programmatic Structured Extraction from Books — Design Note

**Date:** 2026-05-27
**Author:** Claude (planning lane, fichero-0.0.2)
**Status:** Proposal — feeds GitHub issues #1277 / #1278 / #1279
**Scope:** Three features in the "programmatically extract structured data from a
book" vein, framed against what already ships. **No product code** — this is a
design + reuse map.

---

## Why these three together

Fichero already extracts a lot of structured data from documents, but the work
clusters at the **front matter** (reference metadata) and the **back matter as a
flat list** (bibliography import). Three gaps remain, and they share machinery:

1. **In-text citation USAGE** — how a source is *used* in the body, not just that
   it's cited. (Issue #1277)
2. **Back-of-book INDEX → topics + grounded statements** — the index is a
   hand-built topic map we currently ignore. (Issue #1278)
3. **Book STRUCTURE** — chapters / sections / subsections over the flat page
   list. (Issue #1279)

All three depend on one primitive — a **printed-page ↔ PDF `sequence` offset
resolver** — and all three write into the existing **evidential KG model**
(`KnowledgeClaim` / `KnowledgeEntity` / `DocumentCitation`). Build the resolver
once; reuse the model everywhere.

---

## What already exists (verified survey)

> Source paths are under `fichero-engine/src/fichero/`. Verified via jcodemunch
> + direct read on 2026-05-27.

### Reference (front-matter) extraction — SHIPS
- `bibliography/extractor.py`
  - `extract_from_pdf_metadata(path)` — PyMuPDF info dict (free, instant).
  - `extract_from_first_pages(pages_text, llm_config)` — LLM structured-output
    into a `_Biblio` schema (title/authors/date/publisher/journal/doi/isbn/…).
  - `extract_full(document, llm_config)` — orchestrates + merges, user-curated
    values win.
  - `_gather_cover_pages_text(document, n_pages=4)` — **the canonical page-child
    access pattern**: `db.query(Document, parent_id=doc.id)`, filter
    `doc_type.value == "page"`, sort by `sequence`, join `page_content`.
- Route: `POST /api/bibliography/document/{id}/extract?use_llm=` →
  `api/routes/bibliography.py::run_extractor`. Writes `Document.source_metadata`.

### Bibliography (back-matter list) — SHIPS, but as IMPORT not BODY-EXTRACTION
- `bibliography/importers.py` — `read_bibtex` / `read_ris` / `read_csl_json` /
  `write_bibtex` / `detect_format` (#909).
- `bibliography/doi_lookup.py` — `resolve_doi` / `resolve_isbn` (Crossref / Open
  Library, #910).
- Routes: `POST /api/bibliography/import`, `/export.bib`, `/resolve`.
- **Gap:** there is no "read the reference-list pages at the end of a scanned
  book → structured entries" extractor; import assumes you already have a
  `.bib`/`.ris`/CSL file. (Relevant to #1277's resolution target set.)

### Document→document citation graph — SHIPS
- `knowledge_models.py::DocumentCitation` (line 590): `source_document_id`,
  `target_document_id` (nullable when unresolved), `target_citation_text`,
  `page_label`, `char_start`, `char_end`, `confidence`, `detector`
  (`manual`/`regex`/`llm`/`bibtex_import`), `metadata`.
- Routes: `/api/citations/graph` CRUD + `/document/{id}/inbound` + `/outbound`
  (`api/routes/citations.py`).
- `workflows/tools/llm_prompting.py::match_to_reference` — fuzzy resolve a
  citation string to an in-library document.

### Evidential KG model — SHIPS (#1123 + #1266, just merged)
- `knowledge_models.py::KnowledgeClaim` (line 912) already carries the full
  provenance surface this work needs:
  - **Source anchor:** `source_document_id`, `source_page_label`,
    `source_excerpt`, `source_char_start/end`, `source_bbox` (PDF coords via
    `PyMuPDF page.search`).
  - **SVO:** `subject_canonical`/`predicate_verb`/`object_phrase` +
    `svo_*` + `subject_entity_id`; `predicate_canonical` (slug from
    `kg/_common.py::CANONICAL_VERBS`).
  - **Attribution:** `speaker_name`/`speaker_entity_id`, `scribe_*`, `editor_*`,
    `quotation_kind`, `provenance_layer`, `source_genre`, `audience`,
    `source_language`.
  - **Temporal/spatial:** `time_start/end/precision`, `claim_recorded_at`,
    `claim_geo`/`claim_location` (the #1266 source-anchored dimensions).
  - **Quality:** `confidence` + `confidence_source`, `provider`/`model`.
- `knowledge_models.py::KnowledgeEntity` + `EntityType` enum (line 252:
  person/location/organization/event/concept/other). **User-extensible registry
  landed** (#874 / tasks #264, #267 / #1240) — new types without code edits.
- Upsert: `POST /api/kg/entities` → `entities.py::upsert_entity` (line 152),
  with the dedupe review band in `kg_review.py`; curation merge/split at
  `/api/kg/entity-curation`.

### Extractor / workflow node system — SHIPS
- `workflows/tools/extractors.py::_SECTIONS` — list of dicts
  (`name`/`display`/`entity_type`/`instructions`/`output_format`); `EXTRACTORS`
  dict builds one registered tool per section.
- `workflows/tools/extract_all.py::extract_all` — orchestrator over sections.
- **A new extraction capability = a new `_SECTIONS` entry / tool**, surfaced in
  the palette (#697 fixed) and as a workflow node.

### OCR / Apple Vision — SHIPS
- `workflows/tools/vision_base.py::apple_vision_ocr_pages_async` /
  `_apple_ocr_pdf_pages` (kreuzberg → macOS Vision); "Transcribe (Auto-Detect)"
  preset routes scanned pages here.

### Page / parent-doc model — SHIPS
- PDF pages are child `Document` rows: `parent_id` → parent PDF, `doc_type=page`,
  `sequence` ordinal, `page_content` text; **page docs have `path=None`**, and
  **artifacts live on the parent** (see MEMORY `project_artifact_page_lookup`).
  Any structure feature must NOT re-parent pages or it breaks artifact lookup.

---

## Shared primitive (build once, used by all three)

**Printed-page ↔ PDF-`sequence` offset resolver.** A book's index, TOC, and
in-text "p. 214" references all use *printed* page numbers, which are offset from
the PDF page ordinal (`sequence`) by front matter (cover, roman-numeral prelims,
blank versos). All three features need to map a printed page to the right page
`Document`. Recommend a small utility (e.g. `books/page_offset.py`) that, given a
parent document + a known anchor (one printed↔sequence pair, or `fitz` labels via
`doc.get_page_labels()`), resolves printed→`sequence`→page `Document`. Tracked as
a sub-task in #1278 and reused by #1277 and #1279.

---

## Feature 1 — In-text citation USAGE extraction (#1277)

**Problem.** We know a doc's reference metadata (front matter) and can import its
bibliography, but not *how* a source is used in the body: "Author A claims X about
source Y on page N, with the surrounding text." Daniel wants to see how a given
citation is used by an author and cross-explore that usage across sources.

**Approach.** A body-pass extractor that, per page/chunk, (1) detects in-text
citation markers (Author-Year, `[n]`, footnote/endnote refs), (2) resolves each
to a cited work, and (3) emits a **structured usage record**: citing doc + page +
char span → cited work + a *stance* + the surrounding reference text.

**Reuse, not rebuild:**
- **Structural anchor** = `DocumentCitation` with `detector="llm"` (or a new
  `"llm-usage"` tag) — it already has source/target/page/char-span/confidence.
- **Interpretive layer** = a linked `KnowledgeClaim`: `speaker_name` = author,
  `source_excerpt` = surrounding text, `source_page_label` = N, and the *stance*
  as `predicate_canonical` / a **#1124 hermeneutic predicate**
  (`contests_reading`, `extends_reading`, `critiques`, `defends`, `builds_on`).
  This is exactly the "interpretive move" register #1124 defines.
- **Resolution** = `match_to_reference` + the document's bibliography entries as
  the candidate set.

**Phased breakdown:**
1. **Schema decision (no new table if avoidable — 0.0.x no-migration):** model a
   usage as `DocumentCitation` (structure) + linked `KnowledgeClaim`
   (interpretation), joined via `metadata`/`entity_ids`. Document the join.
2. **Marker detector + extractor:** new `citation_usage` section/tool in
   `extractors.py` over body `page_content` → `{marker, stance, claim_text,
   excerpt, page, char_span}`.
3. **Resolution pass:** marker → `DocumentCitation.target_document_id` via
   `match_to_reference` + bibliography list; leave unresolved string when no
   match (mirrors existing `target_document_id=None`).
4. **Cross-explore endpoint:** `GET` usages by cited work across the library
   ("how is Source Y used, by whom, with what stance?").
5. **Tests + OpenAPI regen** (+ later inspector surface — frontend issue).

**Dependencies / cross-links:** #1124 (predicate vocabulary), #906
(`DocumentCitation` graph), #908/#909 (bibliography), #1123/#1266 (evidential
claim model). Adjacent to the hermeneutic layer but framed as programmatic
structured extraction from the body.

---

## Feature 2 — Back-of-book INDEX → topic entities + grounded statements (#1278)

**Problem.** Academic books ship a hand-built index (term → page numbers) — a
curated topic map — and Fichero ignores it.

**Approach.** Given the index page range + page offset: (1) parse index entries
(term, subentries, page refs incl. ranges `12–15` and `ff.`), (2) create a
**TOPIC entity per term**, (3) for each topic, gather the referenced pages and
extract **grounded statements** tied to source page + excerpt.

**Reuse, not rebuild:**
- **Topic entity** = `KnowledgeEntity` with `entity_type` = a registered
  `"topic"` type (via the #874 registry) or the existing `concept`. Subentries →
  alias/hierarchy. Upsert via `entities.py::upsert_entity` (gets dedupe review
  for free).
- **Grounded statements** = `KnowledgeClaim` with full #1266 provenance:
  `subject_entity_id` = topic, `source_page_label`/`source_excerpt`/
  `source_char_start/end`/`source_bbox`, and `confidence_source`. Source-anchored
  basis when the page text under-determines a date/place.
- **OCR** = `vision_base::apple_vision_ocr_pages_async` for scanned index +
  body pages.
- **Page access** = the `_gather_cover_pages_text` page-child query pattern +
  the shared offset resolver.

**Phased breakdown:**
1. **Index parser:** input = index page range + page offset; OCR/parse →
   `{term, subentries[], page_refs[]}` (handle ranges + `ff.`).
2. **Topic entities:** upsert one entity per term; subentry hierarchy via
   aliases/links; provenance = index location.
3. **Offset resolver** (shared primitive): printed page → page `Document`.
4. **Per-topic statement extractor:** for each topic's pages, extract grounded
   statements → `KnowledgeClaim` (subject = topic, source-anchored).
5. **Cross-link + query:** `entity_ids`/`subject_entity_id`; endpoint
   "statements for topic".
6. **Tests + OpenAPI.**

**Dependencies / cross-links:** #874 (entity-type registry / topic type), #1266
(evidential + source-anchored basis), Apple Vision OCR, page/parent model.

---

## Feature 3 — Programmatic book STRUCTURE: chapters/sections/subsections (#1279)

**Problem.** A book is currently a flat list of page `Document` children under a
parent PDF — no chapter/section hierarchy.

**Approach.** Detect structure from (a) the embedded PDF outline / TOC, (b)
heading + page-feature heuristics, (c) optional LLM fallback, and build a
hierarchy of **page-`sequence` ranges**: chapter → section → subsection.

**Reuse, not rebuild:**
- `PyMuPDF` (already a dep, used by the bibliography extractor): `doc.get_toc()`
  for an embedded outline; font-size deltas + `"Chapter N"` patterns + page
  breaks for heuristics.
- `extract_from_first_pages` pattern for parsing TOC-page text when no embedded
  outline exists.
- Page/parent/`sequence` model + the shared offset resolver.

**Critical constraint.** Do **not** re-parent page `Document` rows under new
chapter rows — pages have `path=None` and artifacts live on the parent
(`project_artifact_page_lookup`). Model structure as **range references over page
`sequence`**, not by mutating the page tree.

**Phased breakdown:**
1. **TOC source:** embedded outline (`fitz.get_toc`) → printed-page offset;
   fallback = parse TOC pages text.
2. **Heuristic detector:** heading patterns + font-size deltas + page features →
   candidate boundaries.
3. **Structure model:** hierarchical `{title, level, start_sequence,
   end_sequence, parent_structure_id, basis}` referencing page sequences (new
   Pydantic model + `_ensure_table`, no ALTER — 0.0.x rule).
4. **Reconcile** TOC vs heuristic; record `basis` (`toc`/`heuristic`/`llm`) +
   confidence (mirrors #1266's basis-tagging discipline).
5. **API:** get structure tree for a document; navigate page ↔ chapter.
6. **Tests + OpenAPI**; document interaction with page/parent/artifact model.

**Dependencies / cross-links:** page/parent model, PyMuPDF, shared offset
resolver (with #1278), optional LLM. Chapter/section ranges also give #1277 and
#1278 a "which chapter is this page in?" context for free.

---

## Milestone note

Per the planning directive these are filed against **0.0.2 — Backend Merge + Bug
Fixes** (milestone 8) as the default bucket. They are **net-new feature epics,
not bug fixes**, and all build on KG infrastructure that landed in the 0.0.3-era
issues (#874, #1123, #1266). Recommend re-milestoning to a 0.0.3 KG milestone
(**#48 "0.0.3 — KG Navigation + Polish"** or **#50 "0.0.3"**) once 0.0.2 ships —
flagged here so the move is a one-click decision for Daniel.

## Suggested build order

1. **Shared offset resolver** (small; unblocks #1278 + #1279, helps #1277).
2. **#1279 structure** (gives the others chapter context; pure parsing, low KG
   risk).
3. **#1278 index → topics** (depends on offset resolver + entity registry).
4. **#1277 in-text usage** (richest; benefits from #1124 predicate vocab landing
   first).
