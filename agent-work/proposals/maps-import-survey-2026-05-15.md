# Maps Import Survey — `~/code/maps_southern_colombia/agent-work/maps/`

**Date:** 2026-05-15
**Author:** survey subagent (read-only)
**Goal:** scope what it would take to import Daniel's southern-Colombia map archive (images + sidecar JSONs) into Fichero, with sidecar metadata landing on the `Document`.

---

## 1. Directory Inventory

### Top-level totals

| Type        | Count |
|-------------|-------|
| `.jpg`      | 2133  |
| `.JPG`      |   25  |
| `.png`      |    4  |
| `.tif`      |   15  |
| `.jp2`      |    1  |
| `.pdf`      |   88  |
| **Total images/PDFs** | **2266** |
| `.iffy.json` (sidecars) | **497**   |
| `.md` (READMEs)         |    6  |
| `.DS_Store`             |   10  |

### Per-archive breakdown

| Folder              | Images | Sidecars |
|---------------------|-------:|---------:|
| agi                 |     11 |       10 |
| agi-sevilla         |      1 |        0 |
| agn                 |     93 |       97 |
| agn-colombia        |      5 |        3 |
| ahn                 |      1 |        1 |
| ahu                 |      1 |        0 |
| banrepcultural      |      8 |        8 |
| bne                 |      4 |        0 |
| bvmc                |      1 |        1 |
| **bvmdefensa**      | **2004**|    **279**|
| clements            |      2 |        2 |
| ecuador-academic    |     55 |       47 |
| internet-archive    |     24 |       19 |
| jcb                 |      1 |        1 |
| leventhal           |      1 |        1 |
| loc                 |     33 |        6 |
| na                  |      6 |        6 |
| princeton           |      8 |        8 |
| rumsey              |      1 |        3 |
| unidentified        |      5 |        5 |

### Pairing

- **497** sidecars total
- **2261** distinct image stems
- **94** sidecars without a matching image (orphan json — typically `manifest.iffy.json` files inside per-record subfolders)
- **1858** image stems without a sidecar (orphan img — almost all in `bvmdefensa/` and `loc/`; multi-page renders share one record)

### Naming convention

- Image: `<stem>.<ext>` (`.jpg`, `.png`, `.tif`, `.pdf`, `.jp2`)
- Sidecar: `<stem>.iffy.json` *(not `.xmp` — README.md describes a planned XMP convention that wasn't followed)*
- Some records use a subfolder pattern: `archive/<record>/manifest.iffy.json` + `archive/<record>/page_001.jpg, page_002.jpg, ...`

### Three sampled records

1. `agi/moreno_escandon_1782.iffy.json` (paired with `moreno_escandon_1782.jpg`) — minimal "iffy" schema, 10 fields.
2. `agi/cartagena_harbor_1715.iffy.json` (paired with `.png` + `.tif`) — same minimal schema, 10 fields.
3. `agi/zarate_quito_1734.iffy.json` (paired with `.jpg`) — **rich Pares ingest schema**, 17 fields, includes structured `people`, `image_dimensions`.

---

## 2. Sidecar JSON Schema

There are **51 distinct field-set shapes** across 497 sidecars, but they fall into **3 family clusters**. The data is *not* a single normalised schema — it's been written by different scrapers/agents over time.

### Family A — "Iffy provisional" (most common, ~120 records)

Used in `agi/`, `banrepcultural/`, `na/`, `princeton/`, etc. Hand-authored or scraped from PARES/JCB/etc.

```json
{
  "status": "provisional",
  "record_type": "map",
  "source_archive": "AGI",
  "repository": "Archivo General de Indias",
  "identifier": "MP-PANAMA,223",
  "record_url": "https://pares.mcu.es/...",
  "iiif_manifest": "",
  "discovered_date": "2026-03-30T07:11:00Z",
  "original_date": "1797-12-05",
  "notes": ["Black Pacific", "New Granada", "Quito", "..."]
}
```

### Family B — "BVMDefensa rich" (~280 records)

Scraped from Biblioteca Virtual Defensa. 24–25 fields. Adds publication, physical description, subjects, authors, CDU classification, image download URLs, and a `raw_ficha` array of label/value pairs straight from the source page.

```json
{
  "status": "candidate",
  "record_type": "map",
  "source_archive": "BVMDefensa",
  "repository": "Biblioteca Virtual del Ministerio de Defensa (España)",
  "holding_repository": "Archivo General Militar de Madrid",
  "identifier": "PAN-1/4",
  "record_url": "https://bibliotecavirtual.defensa.gob.es/.../registro.do?id=114766",
  "image_group_url": "https://...catalogo_imagenes/grupo.do?path=212709",
  "discovered_date": "2026-05-11T11:07:16Z",
  "discovered_via": "search hit (#43 BVMDefensa pass 2)",
  "title": "Quarta hoja que comprende las Costas...",
  "title_uniforme": "CÓRDOBA (Colombia). Cartas náuticas. 1:589.286 (1817)",
  "publication": "Madrid : [Nombre de editor no identificado], 1817",
  "original_date": "Madrid : [Nombre de editor no identificado], 1817",
  "year": "1817",
  "physical_description": "1 carta náutica : Papel agarbanzado ; 67 x 100 cm",
  "subject": "Cartas náuticas ‌ 1817 ‌ Bolay ‌ Sucre (Colombia) ‌ Panamá ‌ Colombia",
  "other_authors": "Cardano, Felipe, 1778-1824 ‌ ...",
  "cdu": "861.25 861.22-17 728.7-11",
  "notes_field": "Comprende la provincia de Córdoba...",
  "image_ids": ["2163104"],
  "image_download_urls": ["https://...&idImagen=2163104&formato=jpg..."],
  "bvmdefensa_path_id": "212709",
  "bvmdefensa_record_id": "114766",
  "raw_ficha": [
    {"label": "Título uniforme", "value": "CÓRDOBA (Colombia)..."},
    {"label": "Notas", "value": "Comprende la provincia..."},
    ...
  ]
}
```

### Family C — "Pares download record" (a handful, e.g. zarate_quito_1734)

Different field names entirely (`filename`, `archive`, `pares_record_id`, `series`, `volume`, `sheet`, `title_es`, `date_start`, `date_end`, `subjects`, `places`, `people` (objects with `name`/`role`/`birth_place`), `keywords`, `research_value`, `download_date`, `downloaded_by`, `image_dimensions`, `image_format`, `file_size_bytes`).

### Field frequency (top 25, across all 497)

```
497  status            220  subject
496  record_type       214  cdu
496  discovered_date   207  holding_repository
478  source_archive    183  other_authors
472  identifier        180  notes
468  repository        179  title_uniforme
452  record_url        167  iiif_manifest
399  original_date     161  publication
329  discovered_via     65  user_note
311  title              47  image_download_url
279  image_group_url    44  creator
253  bvmdefensa_path_id 43  publisher
245  image_ids          41  description_summary
245  image_download_urls
245  raw_ficha
244  year
240  physical_description
229  notes_field
228  bvmdefensa_record_id
```

**Required-ish fields** (present in >90% of sidecars): `status`, `record_type`, `discovered_date`, `source_archive`, `identifier`, `repository`, `record_url`. Everything else is optional.

---

## 3. Field Mapping → Fichero Document

Fichero's `Document` model (`fichero-engine/src/fichero/models.py:131`) has these declared fields relevant here:

- `id`, `parent_id`, `doc_type`, `file_type`, `name`, `path`, `page_content`
- `metadata: dict[str, Any]` (free-form, but **note**: `extra="allow"` means undeclared *top-level* fields silently drop on `model_dump()` — but `metadata` itself IS declared, so anything stuffed inside the dict round-trips fine)
- `source_metadata: dict[str, Any] | None` — **already exists** for bibliographic metadata (#908, used by citation renderer)
- `source_authority` — enum, KG weighting

Plus typed accessors that read from `metadata`: `source_url`, `source_type`, `iiif_manifest`, `width`, `height`, `checksum`, `file_size`, `page_count`, `bookmark`.

### Mapping table

| Sidecar field           | Target on Document                              | Notes |
|-------------------------|-------------------------------------------------|-------|
| `title`                 | `metadata["title"]` AND `source_metadata["title"]` | citation renderer reads from `source_metadata` |
| `record_type`           | already implied — these are all maps; could set `metadata["record_type"]="map"` | could also map to a new tag/label |
| `source_archive`        | `source_metadata["archive"]` + `metadata["source_archive"]` | needed by KG `source_authority` |
| `repository`            | `source_metadata["repository"]` | |
| `holding_repository`    | `source_metadata["holding_repository"]` | |
| `identifier`            | `source_metadata["call_number"]` (closest) or `metadata["identifier"]` | |
| `record_url`            | `metadata["source_url"]` (uses existing typed accessor `Document.source_url`) | |
| `iiif_manifest`         | `metadata["iiif_manifest"]` (typed accessor exists) | |
| `image_download_urls[]` | `metadata["image_download_urls"]` | not currently typed |
| `original_date` / `year`/ `date_start` | `source_metadata["date"]` + `metadata["original_date"]` | accept both, prefer `original_date` |
| `creator`, `other_authors`, `people[]` | `source_metadata["author"]` (string) + `metadata["people"]` (raw) | |
| `publication`, `publisher` | `source_metadata["publisher"]` | |
| `physical_description`  | `metadata["physical_description"]` | |
| `subject`, `subjects[]`, `keywords[]`, `places[]` | `metadata["subjects"]`, `metadata["places"]` (lists) | candidates for KG entity seeding |
| `notes[]`, `notes_field`, `description_summary` | `page_content` (joined string) so they're indexed for search | this matters — without this, the sidecar text never reaches search |
| `discovered_date`, `discovered_via` | `metadata["discovered_date"]`, `metadata["discovered_via"]` | |
| `status` ("provisional", "candidate", "downloaded") | `metadata["sidecar_status"]` (don't collide with Fichero's `Document.status`) | |
| `image_dimensions.{width,height}` | `metadata["width"]`, `metadata["height"]` (typed accessors) | already extracted by `_extract_image_metadata`; use sidecar as fallback |
| `file_size_bytes`       | `metadata["file_size"]` (already extracted at ingest) | sidecar redundant |
| `image_ids[]`, `bvmdefensa_path_id`, `bvmdefensa_record_id`, `pares_record_id` | `metadata["external_ids"]` (dict) | |
| `cdu`                   | `metadata["cdu"]` | Spanish library classification |
| `raw_ficha[]`           | `metadata["raw_ficha"]` (preserve as-is) | dump of source page |
| `local_pdf`, `local_file`, `pdf_filename`, `download_url`, `image_download_url` | drop — supplied by ingest | |
| `user_note`             | append to `page_content` or `metadata["user_note"]` | Daniel's annotations, must preserve |
| `doi`, `primary_source_creator`, `primary_source_date` | `source_metadata["doi"]`, `source_metadata["author"]`, `source_metadata["date"]` | |

### What does NOT need a new declared field

Everything fits in the existing `metadata: dict` and `source_metadata: dict | None`. **No schema migration needed.** The Pydantic-extra gotcha (`feedback_pydantic_field_must_be_declared`) only bites when code tries to set a *top-level attribute* like `doc.cdu = "..."`. Setting `doc.metadata["cdu"] = "..."` is safe — `metadata` is a declared dict.

### What might benefit from a typed accessor (optional, follow-up)

If maps become a first-class workflow (KG seeding, map-specific search facets), add `@property` accessors on `Document` for: `archive`, `identifier`, `physical_description`, `subjects`, `places`. Read-only, backed by `metadata` — no migration.

---

## 4. Import Surface

### What already exists

**Backend endpoints** (`fichero-engine/src/fichero/api/routes/ingest.py`):
- `POST /api/ingest/file` — body: `{path, parent_id?, copy_mode, extract_text, auto_embed}` → returns `Document`
- `POST /api/ingest/folder` — same shape, returns `IngestTaskResponse` with `task_id`
- `GET /api/ingest/status/{task_id}` — poll progress
- `PUT /api/documents/{doc_id}` — merges `metadata` (line 258–264 in `documents.py`), so post-ingest enrichment is safe and additive

**Backend lib** (`fichero-engine/src/fichero/ingest.py`):
- `ingest_file(path, mode, parent_id, ...)` — single file, runs `_extract_file_metadata` + optional `_extract_text_content`
- `ingest_folder(path, ...)` — walks recursively, calls `ingest_file` per file
- `IngestMode.LINK | COPY | MOVE`
- Headers: requires `X-Fichero-Library-Path`

**SwiftUI client** (`fichero/fichero/Services/ImportServiceGenerated.swift`):
- `importFiles(urls, mode, parentId, extractText, autoEmbed, onProgress)` — calls the same backend
- Folder import is async (start task, poll status)
- `IngestMode.link / .copy / .move`

**CLI client** (`fichero-engine/src/fichero/cli/client.py:208`):
- `import_file(path, parent_id)` uses a *different, older* endpoint: `POST /api/documents/import` (multipart upload). This is **not** `/api/ingest/file`. There is **no** CLI command today that walks a folder + posts to `/api/ingest/folder`, and **no** path that knows about sidecar JSONs.

### What's missing

**The ingest pipeline knows nothing about sidecar JSONs.** `ingest_folder` walks every file, so a `.iffy.json` next to a `.jpg` would be ingested as its own `Document` (file_type=other, page_content=raw JSON). That's wrong — we want the JSON's *content* attached to the image's `Document`, not a separate doc.

### Smallest viable importer (recommended)

Add a new module `fichero-engine/src/fichero/ingest_sidecars.py` with one function:

```python
def ingest_with_sidecars(
    folder: Path,
    *,
    sidecar_suffix: str = ".iffy.json",
    mode: IngestMode = IngestMode.LINK,
    parent_id: str | None = None,
    db: Database,
    package_path: Path,
) -> list[Document]:
    """
    Walk folder. For each image/pdf, look for <stem><sidecar_suffix>.
    Ingest the image. If a sidecar exists, merge its fields into doc.metadata
    + doc.source_metadata + doc.page_content (notes joined) per the mapping
    table in agent-work/proposals/maps-import-survey-2026-05-15.md.
    Skip the sidecar JSON itself (don't ingest it as a doc).
    Skip orphan sidecars (no image partner) by default; emit a warning.
    """
```

Pair with:

1. **One backend endpoint**: `POST /api/ingest/folder-with-sidecars` (mirror of `/api/ingest/folder` + `sidecar_suffix` param). Or: extend `/api/ingest/folder` with an optional `sidecar_suffix: str | None = None` and gate on it.
2. **One CLI command**: `fichero ingest folder <path> --sidecar-suffix .iffy.json [--mode link|copy] [--parent-id ID]`. Add to whatever Typer app the CLI uses (currently there's a `client.py` with methods but the survey didn't find a Typer entrypoint inside `fichero/cli/`; the CLI lives somewhere else — see "Risks").
3. **Field-mapping helper**: keep mapping in one tested function `apply_sidecar_to_document(doc, sidecar_dict) -> None`. Cover the 3 schema families; unknown fields go into `metadata["sidecar_raw"] = sidecar_dict` so nothing is silently dropped.

**Estimated size:** ~250 LOC backend (importer + mapper + endpoint), ~50 LOC CLI command, ~150 LOC tests (one fixture per sidecar family). No SwiftUI changes needed for v1 — Daniel runs it from CLI, browses results in the app.

---

## 5. Risks & Gotchas

1. **Schema fragmentation (51 shapes).** Field-mapping function must be defensive: every field optional, type-check each value, never assume nesting. Build the mapper around the ~25 most-common fields; dump everything else into `metadata["sidecar_raw"]` for human review.

2. **1858 orphan images (no sidecar).** Mostly `bvmdefensa/` (multi-page records share one record-level sidecar in a parent folder, while individual page JPGs sit in subdirs without their own JSON). Decide policy:
   - (a) ingest anyway, no extra metadata — easy default
   - (b) walk up one directory and look for a folder-level `manifest.iffy.json` to apply to all siblings — handles the bvmdefensa pattern correctly
   - **Recommend (b)** with `--orphan-policy ignore|inherit-parent|skip` flag

3. **94 orphan sidecars (no image).** Most are `manifest.iffy.json` files in subfolders that describe a record group. Either skip silently or — if (b) above is implemented — use them as folder-level metadata applied to all images inside the folder.

4. **Duplicate handling.** No checksum dedupe in `ingest_file` today (it computes a checksum but doesn't query for existing docs by it). Re-running the importer creates duplicate `Document`s. Add a pre-check: if a doc with the same `metadata["checksum"]` exists under the target `parent_id`, update its metadata instead of creating a new one.

5. **Coordinates.** Some `notes_field`/`physical_description` strings contain raw lat/long ("O 73°50'-O 68°40'50''/N 11°05'40''--N 7°44'40''") referenced to non-Greenwich meridians (Cádiz, in the example). v1 should preserve as text; geo extraction is a future workflow.

6. **`status` field collision.** Sidecar's `"status": "provisional"` ≠ Fichero `Document.status` (which is the processing pipeline state). Map sidecar status to `metadata["sidecar_status"]`.

7. **Multilingual content.** Most metadata is Spanish (titles, subjects, notes). `lang_detect.py` exists in the backend — when joining notes into `page_content`, also set `metadata["language"]` so search/extraction picks the right model.

8. **`raw_ficha` non-ASCII separator.** The `subject` field uses `‌` (U+200C zero-width non-joiner) as a delimiter. Don't split on regular punctuation; use that exact character or the parallel `raw_ficha` array (which is already structured).

9. **Sidecar of sidecar (rare).** A few records have nested objects (`people: [{name, role, birth_place}]`, `image_dimensions: {width, height}`). Mapper must handle dicts/lists, not just scalars.

10. **CLI entrypoint location.** `fichero-engine/src/fichero/cli/client.py` exposes a `FicheroClient` class but **not** a Typer/Click app. The CLI app itself appears to live in another worktree (`agent-work/proposals/fichero-cli-*` files reference a separate branch). Verify which branch owns the CLI before adding a `fichero ingest folder` subcommand — may need to land the importer as a backend route first and add the CLI subcommand on the cli branch.

11. **SwiftUI ImportService doesn't pass sidecar info.** If the user drag-drops a folder of maps in the app today, sidecars get ingested as `.json` documents. Either (a) document the CLI as the only sidecar-aware path for v1, or (b) extend `ImportServiceGenerated` to pass `sidecarSuffix` through (small additive change once the backend endpoint exists).

12. **`extract_text=true` on `.iffy.json` files.** Today's folder ingest would call Kreuzberg on each JSON. Even after we skip sidecars at the importer level, make sure the `_TEXT_EXTRACTABLE` filter in `ingest.py` doesn't accidentally feed JSON to a text extractor that produces noise.

---

## Recommendation

Build this as a **backend importer enhancement**, not a one-off CLI script:

- The mapping logic belongs next to `ingest.py` so SwiftUI can use it later.
- The pairing logic (image ↔ sidecar) belongs in the backend so re-runs, dedupe, and orphan-policy are consistent.
- Expose it via one new endpoint + one CLI subcommand. SwiftUI integration can wait for v2.

Total scope: ~1 day of focused work + tests + doc. No model migration. No SwiftUI changes for v1.
