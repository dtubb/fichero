# Importing the Fichero 1.0 Compañía Minera archives

**Lane:** lane-legacy-import · **Date:** 2026-09-04 · **Status:** review + delta spec (build held for the team-lead's machine window)

Daniel's mandate: drag the two Compañía Minera folders on the external volume into
today's Fichero and have them land *properly* — artifacts, renditions, folder-level
catalogue, dates — with the 300 GB staying exactly where it is.

Everything below Phase 1 was read off the volume **read-only**. Nothing on
`/Volumes/Historical Archives Portable` was written, moved, or renamed.

---

## Phase 1 — What Fichero 1.0 actually wrote to disk

### 1.1 The two archives

```
/Volumes/Historical Archives Portable/
├── Compañía Minera Big Files/
│   ├── 02 In-Progress (to Check)/<batch>_processed/<doc folder>/
│   └── 05 Posted/<year range>/<doc folder>/
└── Compania Minera Smaller Files/
    ├── 04 Checked/<doc folder>/
    └── 05 posted/<doc folder>/
```

Measured inventory (metadata walk, no bytes read):

| | count |
|---|---|
| processed document folders (carry `assets/manifests/`) | **120** |
| raw, never-processed folders (loose JPGs only) | 6 |
| original page images under `*/documents/` | **63,530** |

Nesting is **not uniform**: a document folder sits 3 levels deep under
*Smaller Files* and 4 levels deep under *Big Files* (an extra
`<batch>_processed/` or `<year range>/` tier). Any walker must find document
folders by **marker**, not by depth.

Stage names are pure human curation (`02 In-Progress`, `04 Checked`, `05 Posted`)
and should survive as folder nodes — they are the archivist's workflow state.

### 1.2 A processed document folder

```
<doc folder>/                       # name IS the catalogue title, year-prefixed
├── documents/<doc folder name>/*.JPG     # the ORIGINALS — 21 GB in one folder
├── logs/workflow_00)_default_<ts>.log    # full provenance of the run
└── assets/
    ├── manifests/documents_manifest.jsonl
    ├── crops/            crop_manifest.jsonl        + documents/*.jpg
    ├── split/            split_manifest.jsonl       + documents/*.jpg
    ├── rotated/          rotate_manifest.jsonl      + documents/*.jpg
    ├── enhanced/         enhance_manifest.jsonl     + documents/*.jpg
    ├── background_removed/ background_removed_manifest.jsonl + documents/*.png
    ├── segmented/        segment_manifest.jsonl     + documents/<page>_segments/segment_NNN.jpg
    ├── segmented_transcriptions/ …_manifest.jsonl   + documents/<page>_segments/segment_NNN.txt
    ├── recombined/       recombine_manifest.jsonl   + documents/*.txt
    ├── transcriptions/   transcription_manifest.jsonl + documents/*.txt   ← FINAL page text
    ├── word/             convert_to_word_manifest.jsonl + documents/<title>.docx
    ├── llm_catalogue/    llm_process_manifest.jsonl + steps/documents/*.json + documents/documents_summary.json
    └── llm_catalogue_word/ json_to_word_manifest.jsonl + documents/<title>-catalogue.docx
```

Counts line up 1:1 per page (447 originals → 447 crops → … → 447 final `.txt`),
with `segmented/` fanning out to ~1,500 strips.

### 1.3 The pipeline that produced it

From `logs/workflow_00)_default_*.log` — workflow **"00) default"**, run
2025-06-29, and confirmed against the 1.0 source still in this repo's history
(`src/fichero/tools/*` at `c22bcd04c`, `resources/config_defaults/plans/*.yml`):

```
build_documents_manifest → crop → split → rotate → enhance → remove_background
  → segment → transcribe_qwen_max_segments → recombine_segments → fuzzy_clean
  → convert_to_word → catalogue_folder → catalogue_to_word
```

Models recorded on disk:
* **`qwen-vl-max`** — per-segment transcription (`segmented_transcriptions`, field `details.model`)
* **`gpt-4.1-mini`** — folder-level catalogue (`llm_catalogue/llm_process_manifest.jsonl`, field `model`)

So "processed with qwen" is right for the transcription, and the catalogue was
a second model — the provenance must record **both**, not one label for the folder.

### 1.4 The manifest record shapes (this is the format)

Every stage writes a **JSONL manifest, one record per unit of work**, in a
consistent shape: `{"source", "outputs": [...], "success"?, "details": {...}}`.
Paths inside are *relative to that stage's `documents/` root*, so the chain is
walkable without any absolute path.

`assets/manifests/documents_manifest.jsonl` — the roll call of originals:
```json
{"path":"<doc>/<doc>-1.JPG","type":"file","mtime":1751044512.739,"size":7275431,"format":"jpg","process_fn":"process_fn"}
```
`mtime` is the **file date carried through the pipeline** — the only per-page
date the archive holds.

`crops/crop_manifest.jsonl` — the one record with real geometry:
```json
{"source":"<doc>/<doc>-2.JPG","outputs":["<doc>/<doc>-2.jpg"],
 "details":{"box":{"x1":0,"y1":62,"x2":3107,"y2":4796},"confidence":0.806,"method":"yolo",
            "padding":30,"original_size":[3107,4839],"cropped_size":[3107,4734],
            "rotation":{"original_dimensions":[4839,3107],"reason":"EXIF rotation applied…",
                        "final_dimensions":[3107,4839]}}}
```

`segmented/segment_manifest.jsonl` — horizontal bands, **not** boxes:
```json
{"source":"<doc>/<doc>-1.png","parent_image":"<doc>/<doc>-1.png",
 "details":{"num_segments":3,"segments":[
   {"index":0,"file_path":"…/<doc>-1_segments/segment_001.jpg","bounding_box":[0,1521],"text_len":51}]}}
```
`bounding_box` is `[y_start, y_end]`, full page width, in the
**background-removed PNG** coordinate space — i.e. *after* EXIF rotation, crop,
split, rotate and enhance. Recovering original-image pixels means composing that
whole transform chain.

`transcriptions/transcription_manifest.jsonl` — the fuzzy-clean pass, and the
one to trust for page text:
```json
{"source":"<doc>/<doc>-1.png","outputs":["<doc>/<doc>-1.txt"],"success":true,
 "details":{"original_length":369,"cleaned_length":366,"reduction_percent":0.81}}
```

`llm_catalogue/` — **folder-scoped**, not page-scoped. `steps/documents/*.json`
holds one file per catalogue step, each `{"source","step","result":{…}}`:
`extraer_entidades_personas_organizaciones_ubicaciones`,
`extraer_entidades_fechas_legales_rios`, `extraer_entidades_especializadas`,
`linea_temporal`, `personas_clave_y_etiquetas`, `resumen`. Entities carry
`nombre`, `ortografias_alternativas`, `contexto`; `linea_temporal` is a list of
`{"fecha":"1919-12-10","evento":"…"}` — real, ISO-shaped historical dates.

`documents_summary.json` repeats the results plus the original
`source_folder` (a `/Volumes/Files/fichero/…/03 Processing/…` path that no longer
exists — useful as provenance, useless as a file reference).

### 1.5 Marshall precedent

`~/code/marshall-dary` **is gone from this machine** — the precedent converter
cannot be read. What survives of it is exactly the thing that matters: the
canonical interchange format it produced (§2.1) and `rendition_sidecar.py`,
whose docstring names the Marshall corpus as the source of the
`fichero-page-renditions-v0-proposed` shape.

---

## Phase 2 — Gap analysis against today's importer

### 2.1 What already exists, and it is closer than expected

`fichero-server/src/fichero_server/importers/manifest_import.py` (1,177 lines)
reads a **`fichero-corpus-import-v1`** JSONL manifest and creates folders, pages,
image renditions, entities, claims and artifacts *through the app's own FastAPI
routes*. Its properties read like they were written for this job:

* **`DEFAULT_INGEST_MODE = "link"`** (`manifest_import.py:61`) — bytes stay put.
* `_is_safe_to_delete_source` (`:118`) refuses to delete anything under
  `/Volumes/` outright. The 300 GB is structurally safe.
* **Idempotent** — documents skipped by `canonical_external_id`, entities reused
  by canonical name, claims by `canonical_claim_external_id`, artifacts by
  `(doc_id, artifact_type)`.
* `IMAGE_ROLE_PREFERENCE = ("enhanced","background_removed","rotated","crop","original")`
  (`:63`) — **the 1.0 rendition vocabulary, verbatim.** This format was designed
  around exactly this pipeline.
* A dropped folder containing `manifest.jsonl` at its root is already routed to
  it: `api/routes/ingest/core.py:419-427`.

The 794 Caciques geometry artifacts stamped `provider="manifest-importer"` come
from this path — it is live and exercised.

### 2.2 What a 1.0 folder drop does *today*

`core.py:423` looks for exactly `<dropped folder>/manifest.jsonl`. A 1.0 archive
has no such file — its manifests are `assets/manifests/documents_manifest.jsonl`,
one per document folder, several levels down. So the drop **falls through to
plain `ingest_folder`**, which recurses and ingests every file it finds.

That is the failure mode, and it is worse than "nothing happens": one document
folder would import ~2,700 image files (447 originals plus 447 × 5 rendition
copies plus ~1,500 segment strips) as **sibling documents**, plus ~900 `.txt`
files and 13 `.jsonl` manifests as more documents. Across 120 folders that is
roughly a third of a million junk nodes, with the renditions divorced from their
pages and the catalogue never read. Link mode would at least keep the bytes on
the volume, but the library would be unusable.

**No 1.0/legacy converter exists in the repo.** `grep` for
`fichero-corpus-import-v1` finds only the importer, its tests, and the CLI —
no producer. `source_archive_import.py` is a set of one-off release/demo corpus
importers keyed to named libraries, not a format reader.

### 2.3 Per data kind

| Data kind | On disk in 1.0 | Imported today? | Maps to current model? | Link-safe? |
|---|---|---|---|---|
| Original page images | `documents/*.JPG` | as unrelated documents | ✗ no page/folder structure | ✓ link |
| Renditions (crop/split/rotate/enhance/bg-removed) | `assets/<stage>/documents/*` | as *separate documents* | ✗ — should be `images[]` roles on one page | ✓ link |
| Page transcription | `assets/transcriptions/documents/*.txt` | as `.txt` documents | ✗ — should be node `text` → `transcription` artifact | n/a |
| Segment strips + text | `assets/segmented*/…segment_NNN.*` | as documents | ✗ — **no manifest field exists for regions** | ✓ link |
| Segment geometry | `segment_manifest.jsonl` `[y0,y1]` | ✗ ignored | ✗ — needs the transform chain back to original pixels | n/a |
| Crop geometry | `crop_manifest.jsonl` `box` + sizes | ✗ ignored | ✓ representable, nothing reads it | n/a |
| Folder catalogue (entities, tags, resumen) | `llm_catalogue/steps/*.json` | ✗ ignored | ✓ node `entities` on the **folder** node | n/a |
| Timeline (`linea_temporal`) | `steps/linea_temporal.json` | ✗ ignored | ✓ node `claims`, or a folder artifact | n/a |
| Dates | folder-name year; page `mtime`; `fecha` per event | ✗ ignored | ✓ node `date` | n/a |
| Curation stage (`04 Checked` / `05 Posted`) | directory tier | as a plain folder | ✓ folder node + metadata | n/a |
| Word renditions (`.docx`) | `word/`, `llm_catalogue_word/` | as documents | ~ no non-image rendition role | ✓ link |
| Run provenance (models, timestamps) | `logs/*.log`, manifest `model` fields | ✗ ignored | ✓ artifact `provider`/`model` — **but hardcoded** | n/a |

### 2.4 The three real deltas in existing code

1. **Provider/model are hardcoded.** Every artifact the importer writes is
   stamped `provider="manifest-importer"`, `model=CANONICAL_VERSION`
   (`manifest_import.py:991, 1015, 1052`). A 1.0 import must say
   `provider="fichero-1.0"` and `model="qwen-vl-max"` on the transcription,
   `"gpt-4.1-mini"` on the catalogue. Delta: let a node/artifact carry optional
   `provider`/`model`/`step_name`, defaulting to today's values.
2. **No region concept in the manifest.** `rendition_sidecar.py` models
   `region_on_original` properly, but it is keyed off a `<file>.renditions.json`
   sidecar written *next to the image* — impossible here, the volume is
   read-only and precious. Segment geometry needs either a node-level `regions`
   field on the canonical manifest, or to be deferred.
3. **Drop detection is a single filename check.** `core.py:423` only knows
   `manifest.jsonl`. It needs a second recogniser for a 1.0 archive root.

---

## Phase 3 — Recommendation

**Do not build a second importer.** The existing manifest importer already does
the hard, dangerous parts (link mode, idempotency, routes-not-SQL, /Volumes
protection) and its role vocabulary was drawn from this very pipeline. Build the
**converter** the format's own docstring says is missing — "a general
interchange format produced by corpus-specific converters".

### 3.1 Shape

New module `fichero-server/src/fichero_server/importers/legacy_10_archive.py`,
pure and engine-free:

* `LegacyArchiveScan` / `LegacyDocumentFolder` / `LegacyPage` — pydantic models.
* `scan_archive(root) -> LegacyArchiveScan` — walks by **marker**
  (`assets/manifests/documents_manifest.jsonl`), depth-agnostic; records every
  folder it recognises, every folder it *rejects* and why, and every stage
  manifest that is missing or unparseable. Refusals are data, not log lines.
* `to_canonical_nodes(scan) -> Iterator[dict]` — emits `fichero-corpus-import-v1`
  nodes, parent-before-child.
* `write_manifest(scan, out_path)` — writes `manifest.jsonl` **into a scratch
  directory**, never onto the volume.

### 3.2 The mapping

* **Archive root** → folder node. **Stage tier** (`04 Checked`, `05 posted`,
  `<year range>`, `<batch>_processed`) → folder node, `metadata.legacy_stage`.
* **Document folder** → folder node. `name` = folder name with hyphens restored
  to spaces; `date` = leading 4-digit year; `metadata` carries `resumen`,
  `personas_clave_y_etiquetas`, the original 1.0 `source_folder`, the workflow
  name and task id from the log.
  * `entities[]` ← the three `extraer_entidades_*` steps, mapped
    `personas→person`, `ubicaciones/rios→location`, `organizaciones→organization`,
    else `concept`; `ortografias_alternativas` → aliases, `contexto` → context.
  * `claims[]` ← `linea_temporal`, one per `{fecha, evento}`, `external_id`
    derived from folder + index so re-runs dedupe.
* **Page** → page node, `parent_external_id` = the document folder.
  * `external_id` = `fichero10:<archive>/<doc folder>/<page stem>` — stable
    across re-runs, and the idempotency key.
  * `sequence` = the trailing `-N` in the filename (numeric sort, so `-99` does
    not precede `-100`).
  * `date` = `documents_manifest` `mtime`.
  * `images[]` = one entry per stage that produced a file for that page, roles
    `original / crop / split / rotated / enhanced / background_removed`,
    `source_path` absolute on the volume. Preference order already matches.
  * `text` = `assets/transcriptions/documents/<stem>.txt` (the fuzzy-cleaned
    final), with a note recording that `recombined/` is the pre-clean version.
* **Provenance**: transcription artifacts `provider="fichero-1.0"`,
  `model="qwen-vl-max"`, `step_name="transcribe_qwen_max_segments"`; catalogue
  artifacts `provider="fichero-1.0"`, `model="gpt-4.1-mini"`,
  `step_name="catalogue_folder"`. Read the models **from the manifests**, never
  assume them — a folder processed with a different model must say so.

### 3.3 Deliberately deferred, and said out loud

* **Segment strips and their `[y0,y1]` bands.** Mapping them back to original
  pixels means composing EXIF-rotation → crop box → split → rotate → enhance,
  and the bbox program (`bbox-program-rulings-2026-08-20`) owns that transform
  work. The dry run **counts** them and reports them as unmapped rather than
  attaching geometry we cannot prove. Per-segment text is already subsumed by
  the recombined/cleaned page text, so nothing is lost meanwhile.
* **`.docx` renditions.** No non-image rendition role exists. Counted and
  reported, not attached.

### 3.4 Dry run first, always

`fichero import-legacy-archive <path> --dry-run` (default on) prints, without
touching the library:

```
Fichero 1.0 archive: Compania Minera Smaller Files
  stages                    2   (04 Checked, 05 posted)
  document folders        120   (+6 raw, unprocessed — skipped, listed)
  pages                63,530
  renditions          317,650   (5 roles × pages, link-mode, 0 bytes copied)
  page transcriptions  63,530   qwen-vl-max
  folder catalogues       120   gpt-4.1-mini
    entities              …     timeline claims  …
  UNMAPPED
    segment strips    ~189,000  (geometry deferred — bbox program)
    word documents          240
```

Then `--no-dry-run` writes `manifest.jsonl` to scratch and hands it to
`import_manifest(..., ingest_mode="link")`. Re-running is a no-op on everything
already present.

### 3.5 Drop recognition

Extend `core.py:419-427`: if the dropped folder has no `manifest.jsonl`, look for
a 1.0 marker (any descendant `assets/manifests/documents_manifest.jsonl` within
a bounded depth). On a hit, run the converter into the library's scratch
directory and route to `_import_manifest_folder`. Nothing about the plain-folder
path changes.

### 3.6 Discipline

Real-data rules stand: the volume is read-only; the converter is developed
against a **copied** single document folder in scratch; imports target a scratch
library; zero cloud calls (every model label is read off disk, nothing is
re-inferred). Any schema change (a `regions` field, per-node `provider`) lands as
an idempotent `db_migrations.py` step — never a nuke.

---

## Open questions for Daniel

1. **Stage tiers as folders?** `04 Checked` / `05 Posted` is curation state, not
   provenance. Folder nodes (proposed), or flatten and keep the stage as
   metadata/a tag?
2. **The two archives** — one library or two? They overlap: several document
   folders appear in both *Big Files* and *Smaller Files* (e.g.
   `1936-Frank-E-Smith…`, `1948-Sentencias…`), and some carry a `-1` suffix
   duplicate. Content-identity dedupe would merge them; folder-path identity
   would keep both.
3. **Segment geometry** — worth the transform-chain work now, or genuinely fine
   to leave to the bbox program?
