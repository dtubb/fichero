# Default Workflow Regression Harness (#1287)

## Goal

Catch whole-workflow regressions in CI, especially the #1285 class where a
Catalogue run appears to finish but the `extract_all -> kg_writer -> KG rows`
path does not land `KnowledgeEntity` / `KnowledgeClaim` data.

## Harness Shape

- Reuse the shared seeded library builder from
  `fichero-engine/scripts/seed_test_library.py` via
  `tests.integration._seedlib.seed`.
- Load default workflow JSON through `_load_preset_files()` so tests exercise
  the committed preset definitions, not copied fixtures.
- Execute the real LangGraph runtime with `build_graph(..., skip_cache=True)`.
- Use tiny text fixture files so Transcribe takes its deterministic text-file
  passthrough path instead of Apple Vision.
- In CI, patch only model calls:
  - `extract_all.chat_structured_with_fallback` returns a deterministic
    `_Extraction` object with people, places, dates, and keywords.
  - Catalogue narrative/keyword calls return fixed markdown.
- Assert outcomes in the database, not just node status:
  - final state has no workflow error and no `"No KG payload"` failure,
  - all expected critical nodes complete,
  - transcription/page content artifacts land,
  - new `KnowledgeEntity` and `KnowledgeClaim` rows land for the selected
    fixture document.

## Initial Coverage

Phase 1 covers the default `Catalogue` preset in both shapes that have broken
recently:

- folder selection: folder expands to files, transcribes, extracts, sends
  `kg_payload` to `kg_writer`, and saves catalogue artifacts on the folder.
- doc/file selection: a single file takes the same default preset path and
  writes KG rows against that file.

The test intentionally uses the unmodified `Catalogue` preset rather than a
trimmed test workflow. That makes edits to `catalogue.json` rerun the same
contract in CI.

## Real-LLM Mode

Keep CI deterministic. For local diagnostics, add an opt-in mode later, e.g.
`FICHERO_WORKFLOW_E2E_REAL_LLM=1`, that removes the model-call patches and
requires configured defaults for `$small` / vision. That mode should stay out
of the default pytest path because Apple Intelligence availability and model
latency are not stable enough for CI.

## Next Phases

- Add a manifest for every shipped default workflow and declare the expected
  artifact/KG invariant per workflow family.
- Add `Catalogue Each` once the folder source has an execution-time folder id
  input contract that can be supplied without editing the preset.
- Add the contract walker as a post-run API assertion layer so engine, CLI, and
  Swift-visible envelopes are checked against the same seeded library.
