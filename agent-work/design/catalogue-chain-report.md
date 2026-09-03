# Catalogue = the 1–6 chain — restructure report (2026-09-03)

Daniel's ruling: the preset named **Catalogue** should BE the chain of the six
numbered stage presets in the `/Catalogue` folder. Done. This report maps what
existed, what changed, the two live CLI run matrices, and the rulings still
open.

## 1. The map — what each preset did BEFORE this change

| Preset | Nodes (tool) | Model | What it writes |
|---|---|---|---|
| **Catalogue** (v5, monolith) | files → transcribe → extract_all(persist_kg) → 6× `<type>_folder_cleanup` + citations_extract → aggregate → catalogue | transcribe: vision default; everything else `$small` (citations `$medium`) | per-page transcription + `<type>` artifacts, inline KG entities+claims, `<type>_clean` folder artifacts, `catalogue.*` narrative on the container |
| **1 · Import → Artifacts** (v1) | files → import_artifacts | none (deterministic) | `import_receipt` + `transcription` artifacts from page content already present. Skips existing — idempotent |
| **2 · Extract Entities** (v1) | files → extract_entities_only | `$small` | KnowledgeEntity rows only (people/places/organizations/events; dates are claim-only by design) |
| **3 · Extract SVO → Claims** (v1) | files → extract_svo_only | `$small` | KnowledgeClaim rows per entity (canonical claim writer dedups) |
| **4 · Merge / Dedup** (v1) | files → merge_dedup_only | none | reapplies persisted entity-resolution + suppression rules, conservative pruning |
| **5 · KG Persist / Finalize** (v1) | files → kg_persist_finalize | none | corroboration recompute, embedding backfill, kg.nt snapshot refresh |
| **6 · Catalogue** (v1) | files → catalogue | `$small` | narrative `catalogue.*` artifact + container page_content; fails loudly when no claims exist |

The monolith and the stages were two *different* pipelines wearing one name:
the monolith transcribed first and extracted per-page inline; the stages assume
text is already on the pages and write reviewable, re-runnable KG state.

## 2. What changed

- **`catalogue.json` (preset_version 5 → 6)**: now `files-source` + six
  `sub_workflow` nodes referencing the numbered presets by name, sequenced by
  `summary → barrier` ordering edges (LangGraph fan-in join guarantees stage
  N+1 waits for stage N). Reuses the existing chain pattern proven by
  "Transcribe + Review (Pipeline)". Numbered presets stay runnable standalone
  and unchanged (their preset_versions untouched).
- **`extract_svo_only` gains the dates pass**: dates are claim-only
  (`entity_type=None`), so stage 3's per-entity loop could never emit a date
  claim and the timeline probe contract (#1470 time_start/time_end/date_values)
  went dark with the monolith. Stage 3 now runs one direct
  `_SECTION_SCHEMAS["dates"]` structured call per record (reusing the existing
  section prompt + `_write_kg_rows` dates shape) and inherits the truncation
  retry ladder from `chat_structured_with_fallback` (08b2c490a).
- **Manifest regenerated** (`preset_version_manifest.json`) per the #4298 guard.
- **Tests converted, not deleted**: the harness / scope-isolation /
  rerun-preserves suites now run the chain; the extract_all twostage and
  parallel-scheduling regression tests keep their coverage on inline
  monolith-topology *vehicles* pinned in the test files (the defect classes
  they guard live in `extract_all`/the scheduler, not in the preset).

## 3. Run matrices (live CLI, engine from this worktree on :8765)

Scratch library seeded with 6 Marshall 1923 sample pages (5 transcribed text
pages + 1 raw image page with no text, to record the honest no-text behavior).

### (a) Apple-only (`$small` = apple/apple-intelligence, `$vision_small` = apple-vision)

Run A1 — transcribed text page (NCM_Diary_1923IMG_001.md, doc
b29824981cec…): **whole chain completed, error None**, 94.8s.

| Stage | Outcome |
|---|---|
| 1 · Import → Artifacts | ✅ import_receipt + transcription artifacts written (397ms) |
| 2 · Extract Entities | ✅ Apple Intelligence structured call; entities "N.C. Marshall" (person), "The Diary of N.C. Marshall" (event) (25s) |
| 3 · Extract SVO → Claims | ✅ 3 claims incl. a DATE claim "1923-01-01/1923-12-31 → marks → …" — the new stage-3 dates pass, live on Apple |
| 4 · Merge / Dedup | ✅ completed (no rules to reapply on fresh library) |
| 5 · KG Persist / Finalize | ✅ completed |
| 6 · Catalogue | ⚠️ ran, but narrative degraded to "partial success": Apple rejected the EMPTY user prompt (`Missing or empty 'prompt' field`) — **root-caused + fixed** (claims-only path now carries the claim context in the user prompt; regression test `test_catalogue_claims_only_prompt.py`); re-verified after fix — see below |

Run A2 — raw image page with no text (NCM_Diary_1923IMG_005_part_1.jpg): see below.

Run A2 result — raw image page: stages 1–5 complete (honest no-ops on a
textless page), stage 6 **fails loudly** naming the missing work. Its advice
text still recommended the retired monolith — reworded to "run a Transcribe
workflow first" (catalogue.py).

Run A3 — standalone "6 · Catalogue" after the empty-prompt fix, Apple-only:
`catalogue.narrative` + `catalogue.timeline` artifacts landed
("Diary of N.C. Marshall, spanning the calendar year 1923 …"). Fix verified
live.

### (b) Google via OpenRouter (`$small` = openrouter/google/gemini-2.5-flash-lite)

Run B — chain on NCM_Diary_1923IMG_003_right.md: **all six stages completed,
error None**; 3 OpenRouter calls total (≤8 cap held). Machine was under load
~214 (four agent lanes + suites) throughout.

| Stage | Outcome |
|---|---|
| 1 · Import → Artifacts | ✅ |
| 2 · Extract Entities | ✅ structured call 200 OK; added "THE STANDARD DIARY COMPANY" (organization) |
| 3 · Extract SVO → Claims | ✅ dates + per-entity calls (one empty result on the sparse cover page — logged, not fatal) |
| 4 · Merge / Dedup | ✅ |
| 5 · KG Persist / Finalize | ✅ |
| 6 · Catalogue | ⚠️ narrative chat call tripped the 600s provider-hang guard under load-214 ("chat exceeded 600.0s — provider hang"); degraded cleanly to partial success with KG intact and the error surfaced in Activity. Wiring correct; structured calls to the same model completed in 6–20s. Standalone re-run attempted — see log |

## 4. Remaining rulings for Daniel

1. **Catalogue no longer transcribes.** The chain starts from text already on
   the pages (stage 1's contract). A user who selects raw scans and runs
   Catalogue gets a loud stage-6 failure naming the missing work, not a silent
   nothing — but also not a transcription. Options: (a) leave as is and let
   the description say "run Transcribe first" (current state); (b) prepend a
   "0 · Transcribe" stage to the chain; (c) teach stage 1 to invoke transcribe
   for pages without text. Recommend (a) or (b).
2. **Keywords + citations dropped.** The monolith wrote a `keywords` entity
   set and a citations artifact; no numbered stage produces them. If they
   matter, they need a stage (or fold into 6 · Catalogue's narrative, which
   still generates keywords in its own output).
3. **Folder `<type>_clean` artifacts are gone.** Stage 4 curates the KG rows
   directly instead of writing per-type cleaned-list artifacts. The rerun
   correction-preservation guarantees now attach to stage-1 artifacts and
   `catalogue.*`.
4. **Numbered-name cosmetics**: sidebar now shows "Catalogue" beside
   "1 ·"…"6 ·" in the same folder. If the numbered ones should visually nest
   under Catalogue, that's client IA work.
