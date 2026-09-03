# Convert re-scope · Export matrix · Tool sweep — 2026-09-03

Lane: CONVERT + EXPORT families, `scripts/exercise_tools.py`, worker on `integration`.
Scratch library: seeded `--full` test library + one real Marshall diary page
(`~/code/marshall_diaries/_import/NCM_Diary_19330101-19331231/…IMG_010_part_2.jpg`,
copied read-only into `/tmp/convex-lane/`). Port 8765 was busy (live engine) →
all route runs used the in-process TestClient with a scratch app-db, per the
lane recipe. Everything written stayed under `/tmp/convex-lane/`.

## 1 · Convert re-scope (Daniel: "LLM converts content to SVG, or MD, or whatever")

What the Convert family actually is: the single `convert` tool sends the page
IMAGE to a generative vision model with a per-format prompt and saves the reply
as a `conversion` artifact (target_format stamped; sanitizer strips fences +
scripts, SVG must parse as XML or the save is refused — #4329). It is a
**generative re-creation**, not a converter. Renamed and re-described to say so:

| Was | Now | preset_version |
|---|---|---|
| Convert to Markdown | **AI Convert to Markdown** — "…a generative re-creation… not a mechanical file conversion" | 1 → 2 |
| Convert to HTML | **AI Convert to HTML** — same honesty | 1 → 2 |
| Convert to SVG | **AI Redraw as SVG** — "a generative sketch… not a vector trace; positions and shapes are approximate" | 1 → 2 |

- Tool `convert` display_name → **AI Convert**; description rewritten (was "Convert image to text format").
- Old names added to `_DEPRECATED_PRESET_NAMES` so seeded libraries retire the
  stale rows instead of showing duplicates; manifest entries bumped; capability
  reference docs regenerated; tests renamed (`test_conversion_presets`,
  `test_preflight_credentials`, `test_empty_output_guard_family_sweep`).
- **Nothing removed**: every promised conversion works when a generative model
  is configured (verified live, below), and the keyless/Apple case is already
  an honest pre-dispatch refusal (`requires_generative_model=True`, 2026-09-01).
- Live verification (real models): flash-lite → markdown ✓ html ✓ svg ✓ (well-formed,
  sanitized); Sonnet 4.5 → svg ✓ markdown ✓. `latex`/`csv` remain config-enum
  options with no preset; `csv` overlaps `table_extract` — left as-is, flagged.
- **Flagged, not touched**: `extract_geo.json` and `extract_table.json` sit in
  `folder_path: "/Convert"` but are named/tagged Extract — cross-family
  mis-filing for whoever owns the strip taxonomy. Folder name `/Convert` kept
  (data-driven in Swift; renaming folders would orphan stored copies).

## 2 · Export matrix (all end-to-end on the scratch library)

| Path | Result |
|---|---|
| POST /api/export/markdown-folder | ✓ 200, files + assets |
| POST /api/export/word | ✓ 200, .docx |
| POST /api/export/excel | ✓ 200, .xlsx (docs/entities/claims sheets) |
| POST /api/export/jsonl | ✓ 200 |
| POST /api/export/parquet | ✓ 200 — **ruled design confirmed**: `iter_export_records` → JSONL temp → `db.export_jsonl_as_parquet` (DuckDB writes the Parquet, no PyArrow). Read back with DuckDB: documents 17 / entities 3 / claims 3 rows, typed columns + manifest.json |
| POST /api/export/training | ✓ 200 (0 samples — no episodes in scratch lib) |
| POST /api/export/eleventy-site | ✓ 200 after fix below |
| workflow tool `export_documents` (md+docx+xlsx+eleventy) | ✓ 65 files |

**DEFECT fixed — silent knowledge loss in exports.** An entity/claim with NO
source documents (hand-created via MCP `kg_entity_upsert` / agent chat) was
silently dropped from every export: `_knowledge_graph_rows` requires a source
intersection and `_knowledge_scope_records` yields nothing for an empty source
list. The seeded library's 3 entities exported as **0 rows**. Fix: whole-library
exports (`target_id=None`) now include unsourced rows at a `library` scope
(`scope_kind="library"`, null found_in fields); 11ty renders "library-level
(no source page)" instead of raising; folder-scoped exports still promise only
that folder's knowledge and keep dropping them. 3 new tests in
`test_export_service.py`. After fix: entities.parquet = 3 rows.

CLI note: the generated CLI drives these same routes over TCP; 8765 is another
lane's engine on a different library tonight, so route-level in-process runs are
the end-to-end evidence (two engines must never open one DuckDB).

## 3 · Individual tools sweep (`scripts/exercise_tools.py`, extended)

Extended the script with `--max-cloud-calls` (hard cloud budget; apple/mlx/
ollama uncounted; fallback rows say "cloud budget spent" instead of silently
costing more). Cloud calls used tonight: **6 of ≤10** (2 flash-lite sweep,
2 flash-lite svg/html, 2 Sonnet).

Runs: (a) full registry `--all-tools` on `apple:apple-vision` (image mode),
(b) content mode on Apple, (c) flash-lite on convert/table_extract/transcribe,
(d) direct convert svg/html/sonnet. Reports: `/tmp/convex-lane/sweep_*.json|md`.

| Class | Tools | Verdict |
|---|---|---|
| GREEN (local, no model by design) | enhance/fuzzy_clean/prepare/recombine/remove_background/rotate/segment/split_images, zoom | ✓ produced output files |
| GREEN (Apple OCR path) | detect_regions, economy_htr, transcribe (direct rerun ✓), extract (after fix) | ✓ real text out |
| GREEN (Apple text/chat) | sentiment, summarize, summarize_file, rewrite, translate, text_translate(_review), timeline, questions | ✓ real answers |
| GREEN (passthrough by design) | clean_text, *_extract/*_cleanup family, extract_all, text_reflow — "answered from the text handed" | ✓ (text-family lanes may want a look at echo-y outputs) |
| CAPABILITY-REFUSAL (honest, pre-dispatch) | analyze, caption, classify, classify_script, colors, convert, describe, diagram, faces, handwriting, layout, objects, quality, safety, scene, style, table_extract, tags, transcribe_review on Apple | ✓ refuse with the standard "Apple Vision performs OCR…" message; convert + table_extract verified green on flash-lite/Sonnet |
| KNOWN STUBS (2026-08-27 audit; not fixed tonight, per brief) | enhance, crop, rotate, segment, custom_llm, if, switch, loop, filter, merge, to_pdf, to_word, to_excel, to_json, save_to_library, export (16 palette placeholders) | recorded |
| **DEFECT fixed** | `extract`: when EVERY file failed it still returned ok (empty text/value, errors buried in `results[]`) — the sweep caught Apple refusing all pages and extract reporting success. Now an all-files-failed run carries a top-level `error`; partial failure stays ok. Tests: `test_extract_all_files_failed_error.py` | fixed |
| Harness/env notes | transcribe rows in sweep hit DuckDB locks (app-db vs live 8765 engine; fixed for future runs via `FICHERO_BASE_PATH`); one sweep aborted on a mid-save import race in another lane's `similarity.py` (fine on re-run) | no code defect |

## Cross-lane flags
- `test_default_workflows.py::test_capture_ocr_transcribe_preset_wiring` fails
  in the tree — Transcribe-family, file is dirty from another lane; not mine.
- `preset_version_manifest.json` staged via patch (my convert hunks only); the
  catalogue.json hunk in the tree belongs to the catalogue lane.
- `docs/user/reference/workflows/index.md` regen also picked up the catalogue
  lane's uncommitted preset text (generator reads the tree); integrator should
  regen once at merge.
- perf_baseline.json still keys the old e2e-harness test ids
  (`…[Convert to Markdown]` etc.) — goes stale with the rename; perf suite
  owner should refresh on its next deliberate run.
