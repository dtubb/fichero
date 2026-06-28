# Worker Report — Programmatic Guardrails (milestone #92)

Author: Claude (commit authored as Claude, co-authored Daniel Tubb). **Not pushed.**
Branch base: `3fd30fe3` (origin/main). Date: 2026-06-28.

## Milestone state

Open issues at start: **2**
- **#2271** EPIC: Programmatic guardrail suite — *skipped per instructions (EPIC / continuous).*
- **#2269** Guardrail test: models always download to the SHARED models folder — **actionable, done.**

So there was **one** actionable non-EPIC issue (not 3-5); did it fully.

## Done

**`fix(#2269): Whisper downloads to the shared models folder`**

The guardrail `scripts/check_model_download_location.py` already existed and passed, but with **one
seeded divergence**: `workflows/tools/audio_base.py` hardcoded the LEGACY bundle dir
`~/Library/Application Support/com.fichero.fichero/models` for Whisper, so Whisper downloaded to a
*different* folder than embeddings/spaCy — exactly the scattering #2269 forbids. Fixed the root cause:

- `audio_base.py`: `MODELS_BASE = engine_state_dir() / "models"` (mirrors the canonical
  `local_models.py:40`), plus the matching import and an updated docstring. Verified at runtime it
  resolves to `~/Library/Application Support/Fichero/models` with no `com.fichero.fichero`.
- `check_model_download_location.py`: with the last divergence gone, dropped the `KNOWN_VIOLATIONS`
  entry so the guardrail now guards an **empty baseline** (0 divergences) — any future scattered
  download fails CI.
- `test_whisper_shared_cache.py`: added `test_models_base_is_the_shared_folder` — regression asserting
  `MODELS_BASE == engine_state_dir()/"models"` and no legacy-bundle-id / `~/.cache` path.

This completes #2269's acceptance ("every model download lands in the shared folder"): the guardrail
now enforces it with a clean baseline, and the one real divergence is fixed.

### Behavioural note (for the manager / Daniel)
Existing installs that already downloaded Whisper models to the legacy
`com.fichero.fichero/models/whisper/` folder will re-download once into the shared
`Fichero/models/whisper/` folder on next use. This is the intended consolidation (embeddings/spaCy
already live there); the legacy folder can be deleted. No data loss — these are re-downloadable model
weights, not user data.

## Gate results (from this worktree)
- `python3 scripts/check_model_download_location.py` → exit 0 (0 divergences, 0 known).
- `ruff check fichero-engine/src/` → All checks passed.
- `pytest test_whisper_shared_cache.py test_check_model_download_location.py` → **14 passed**.
- Runtime import check: `audio_base.MODELS_BASE == engine_state_dir()/"models"`, no legacy bundle id.
- Did **not** push.

## Not done
- **#2271** EPIC — skipped per instructions. (Prior batches landed its concrete child slices; items
  1-7 have green guardrails, item 8 is explicitly non-blocking/report-only.)
- No other actionable non-EPIC issues remain in the milestone.
