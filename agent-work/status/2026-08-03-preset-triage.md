# Preset triage for #4501 phase 1 — 2026-08-03

39 shipped presets. **38 carry `(Untested)`**; only `Transcribe HTR` does not.
That is what makes the label wallpaper: the one preset that might deserve a
warning gets the same glance as the 37 that are merely unchecked.

This file is the phase-1 deliverable: which presets can be validated with **no
paid provider**, and which cannot. Validation itself comes after.

## Mechanism — this changes the shape of the work

The `(Untested)` suffix is **not** derived from the per-tool `tested=` flag.

- `ToolDef.tested` exists and is `True` on exactly four tools (`files`,
  `search`, `transcribe`, `transcribe_review`).
- But the preset label comes from `_workflow_untested()` in
  `api/routes/workflow/workflows.py`, which reads **`config.tested` on the
  preset JSON**, and is deliberately "tied to the preset definition, not the
  node tools: several presets reuse the same validated HTR tools yet are not
  themselves validated workflows."

**Validating a tool therefore does not validate the presets that use it.**
Removing a label means setting `"tested": true` in that preset's own JSON
`config`, earned by checking that preset's output.

## The finding that reframes "free" — no preset pins a provider

**Not one of the 39 presets pins a provider on its model-using nodes.** Every
`transcribe` / `convert` / `describe` / `table_extract` node falls back to the
app database's `default_vision_*` settings.

So **"is this preset free?" is a property of the user's configuration, not of
the preset.**

- On a **factory install** — `FACTORY_AI_DEFAULTS` is fully on-device (`apple`
  / `apple-vision`) since #4325 — group [B] is genuinely free.
- On **this machine**, `default_vision_provider = openrouter` and
  `default_vision_model = google/gemini-3-flash-preview`, so every group [B]
  preset **bills on every run**.

I learned this the expensive way: I swept group [B] believing it was on-device
and it went to the paid tier. That is reported separately. The lasting lesson
for #4501 is a requirement on the deliverable itself:

> **A removed `(Untested)` label MUST state which configuration it was
> validated under.** "Validated" earned on Apple Vision, while the user's
> install silently routes to OpenRouter, is a worse lie than "(Untested)" —
> it is the same wallpaper with the sign flipped.

Group [A] is immune to this: those presets call no model at all, under any
configuration.

## Groups

### **[A] free — deterministic** — 14 presets

| preset | `config.tested` | tools |
|---|---|---|
| 1 · Import → Artifacts | no | `files,import_artifacts` |
| 4 · Merge / Dedup | no | `files,merge_dedup_only` |
| 5 · KG Persist / Finalize | no | `files,kg_persist_finalize` |
| Enhance Images | no | `enhance_images,files` |
| Export to Desktop (MD + DOCX + XLSX) | no | `export_documents,files` |
| Fuzzy Clean Images | no | `files,fuzzy_clean_images` |
| Group Same Documents | no | `files,organize_same_documents,similarity` |
| Prepare Images for OCR | no | `files,prepare_images` |
| Recombine Segments | no | `files,recombine_segments` |
| Remove Background Images | no | `files,remove_background_images` |
| Rotate / Auto-Orient Images | no | `files,rotate_images` |
| Segment Images | no | `files,segment_images` |
| Split Chapters | no | `files,split_chapters` |
| Split Images | no | `files,split_images` |

### **[B] free ONLY on factory defaults** — 14 presets

| preset | `config.tested` | tools |
|---|---|---|
| Capture OCR + Transcribe | no | `enhance_images,files,prepare_images,transcribe` |
| Convert to HTML | no | `convert,files` |
| Convert to Markdown | no | `convert,files` |
| Convert to SVG | no | `convert,files` |
| Describe (visual) | no | `describe,files` |
| Extract Table | no | `files,table_extract` |
| Spanish Script v2 Child Passes (19th-20th C.) | no | `search,transcribe,transcribe_review` |
| Transcribe | no | `files,transcribe` |
| Transcribe (Auto-Detect) | no | `classify_script,files,search,transcribe,transcribe_review` |
| Transcribe HTR | yes | `files,search,transcribe,transcribe_review` |
| Transcribe Manuscript | no | `files,transcribe` |
| Transcribe Paleography | no | `files,search,transcribe,transcribe_review` |
| Transcribe Paleography (Ensemble + Deep Review) | no | `files,search,transcribe,transcribe_review,zoom` |
| Transcribe Typescript | no | `files,transcribe` |

### **[C] blocked — needs on-device Apple Intelligence** — 9 presets

| preset | `config.tested` | tools |
|---|---|---|
| 2 · Extract Entities | no | `extract_entities_only,files` |
| 3 · Extract SVO → Claims | no | `extract_svo_only,files` |
| 6 · Catalogue | no | `catalogue,files` |
| Catalogue | no | `aggregate,catalogue,citations_extract,dates_folder_cleanup,events_folder_cleanup,extract_all,files,keywords_folder_cleanup,organizations_folder_cleanup,people_folder_cleanup,places_folder_cleanup,transcribe` |
| Clean Up Text | no | `clean_text,files,transcribe` |
| Extract Geo | no | `extract_geo,files,transcribe` |
| NER per-page (local) | no | `aggregate,extract_all,files` |
| Translate | no | `files,text_translate,transcribe` |
| Translate + Double-Check | no | `files,text_translate,text_translate_review,transcribe` |

### **[C] paid — external API** — 1 presets

| preset | `config.tested` | tools |
|---|---|---|
| Translate (DeepL) | no | `files,transcribe,translate` |

### **[E] delegates** — 1 presets

| preset | `config.tested` | tools |
|---|---|---|
| Transcribe Spanish Script (19th-20th C.) | no | `files,sub_workflow` |
## What each group needs

| group | n | validatable now? | what it needs |
|---|---|---|---|
| **A** | 14 | **Yes, free, any config** | Nothing. No model call exists in these presets |
| **B** | 14 | Free **only** pinned to on-device | Run with `FICHERO_VISION_*_PROVIDER=apple` pinned and asserted, never inheriting app defaults |
| **C blocked** | 9 | Free in principle, blocked today | The `fm-bridge` binary: `chat_with_fallback` on `apple`/`apple-intelligence` raises *"fm-bridge binary not found. Build it with fichero-server/bin/fm-bridge/build.sh"*. A Swift build, so not mine to run. Building it converts the largest apparently-paid block to zero cost |
| **C paid** | 1 | No | `Translate (DeepL)` — external API, no on-device path. Needs explicit approval |
| **E** | 1 | Inherits | `Transcribe Spanish Script` delegates via `sub_workflow`; its cost is its child's |

## What "validated" has to mean

Not "it ran without erroring". #4496 is the cautionary case: the ensemble ran
green end to end while storing the model's commentary as the transcription. A
preset is validated when its **output** is checked against what it claims to
produce.

Instruments that already exist and should be reused:

- `workflows/run_steps.py` (#4284) — `build_run_steps` distinguishes
  `not_run` from `produced_nothing`, so a step that ran and produced nothing
  is legible instead of merely absent.
- `workflows/transcription_accuracy.py` — CER under four normalisation
  policies, for anything claiming to transcribe.
- The real-preset runner from #4414, which no longer no-ops 7 of 12 nodes.

## Fixture note

Group [A]'s image tools reject PDFs (`Unsupported input file type: .pdf`).
That is correct behaviour, not breakage — validating them needs an image
fixture. A 150-dpi PNG rendered from the paleography page works and costs
nothing.
