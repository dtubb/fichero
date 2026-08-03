# #4501 phase 1 — preset triage

39 presets in `fichero-server/src/fichero_server/resources/default_workflows/`.
**38 carry no `config.tested`; only *Transcribe HTR* is marked tested.**

## The mechanism, which changes the shape of the work

The `(Untested)` label is **per-preset `config.tested` in the preset JSON**, NOT
the per-tool `tested=` flag (only 4 tools carry that). So validating a TOOL does
not validate the presets that use it, and 39 presets share a much smaller set of
tools. Dropping the label means setting `config.tested` per preset, after
checking that preset's output.

## How this classification was made, and where it is weak

Mechanically: a preset is "free" if none of its node tools match a model-ish
name (llm, vision, transcribe, translate, describe, extract, summar, chat, ocr,
critique, review, reconcile, classify, caption).

**That heuristic has a known blind spot: `sub_workflow`.** A preset whose nodes
include `sub_workflow` may invoke model nodes inside the child, and this scan
cannot see them — the same blind spot #3804 found in the vision preflight, which
stopped at the parent. *Transcribe Spanish Script (19th-20th C.)* is listed
below as free purely because its only non-file tool is `sub_workflow`; it almost
certainly is not.

The backend lane, applying judgement rather than a name match, reported **14**
free. The gap between 14 and 19 is where that judgement lives. **Treat 14 as the
trustworthy number and this list as the raw material**, not the other way round.

## What "validated" has to mean

Not "it ran without erroring". #4496 is the cautionary case: the paleography
ensemble ran green end to end while storing the model's commentary as the
transcription. A preset is validated when its OUTPUT is checked against what it
claims to produce.

## [A] Classified free-deterministic — no model node (19)

- **1 · Import → Artifacts** — `files,import_artifacts`
- **4 · Merge / Dedup** — `files,merge_dedup_only`
- **5 · KG Persist / Finalize** — `files,kg_persist_finalize`
- **6 · Catalogue** — `catalogue,files`
- **Convert to HTML** — `convert,files`
- **Convert to Markdown** — `convert,files`
- **Convert to SVG** — `convert,files`
- **Enhance Images** — `enhance_images,files`
- **Export to Desktop (MD + DOCX + XLSX)** — `export_documents,files`
- **Fuzzy Clean Images** — `files,fuzzy_clean_images`
- **Group Same Documents** — `files,organize_same_documents,similarity`
- **Prepare Images for OCR** — `files,prepare_images`
- **Recombine Segments** — `files,recombine_segments`
- **Remove Background Images** — `files,remove_background_images`
- **Rotate / Auto-Orient Images** — `files,rotate_images`
- **Segment Images** — `files,segment_images`
- **Split Chapters** — `files,split_chapters`
- **Split Images** — `files,split_images`
- **Transcribe Spanish Script (19th-20th C.)** — `files,sub_workflow`  ⚠️ contains `sub_workflow` — opaque, may hide model nodes

## [B/C] Needs a model (20)

- **Capture OCR + Transcribe** — `enhance_images,files,prepare_images,transcribe`
- **Catalogue** — `aggregate,catalogue,citations_extract,dates_folder_cleanup,events_folder_cleanup,extract_all,files,keywords_folder_cleanup,organizations_folder_cleanup,people_folder_cleanup,places_folder_cleanup,transcribe`
- **2 · Extract Entities** — `extract_entities_only,files`
- **3 · Extract SVO → Claims** — `extract_svo_only,files`
- **Clean Up Text** — `clean_text,files,transcribe`
- **Describe (visual)** — `describe,files`
- **Extract Geo** — `extract_geo,files,transcribe`
- **Extract Table** — `files,table_extract`
- **NER per-page (local)** — `aggregate,extract_all,files`
- **Transcribe (Auto-Detect)** — `classify_script,files,search,transcribe,transcribe_review`
- **Transcribe** — `files,transcribe`
- **Transcribe HTR** — `files,search,transcribe,transcribe_review`  *(already `config.tested=true`)*
- **Transcribe Manuscript** — `files,transcribe`
- **Transcribe Paleography** — `files,search,transcribe,transcribe_review`
- **Transcribe Paleography (Ensemble + Deep Review)** — `files,search,transcribe,transcribe_review,zoom`
- **Spanish Script v2 Child Passes (19th-20th C.)** — `search,transcribe,transcribe_review`
- **Transcribe Typescript** — `files,transcribe`
- **Translate** — `files,text_translate,transcribe`
- **Translate (DeepL)** — `files,transcribe,translate`
- **Translate + Double-Check** — `files,text_translate,text_translate_review,transcribe`
