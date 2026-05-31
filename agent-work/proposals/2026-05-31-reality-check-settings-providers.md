# Reality Check: Settings & Providers milestone — open issues
Date: 2026-05-31
Auditor: claude-sonnet-4-6 (read-only, no builds, no tests)

---

## Summary counts
- Open issues audited: **14**
- Safe to close NOW: **3** (#937, #242, #283*)
- PARTIAL (real work remains): **5** (#1344, #284, #752, #484, #485)
- GENUINELY OPEN (no implementation): **6** (#1059, #1200, #1342, #1152, #732, #854 / #843 / #853)

*#283 is safe to close only if the intent is "gated until feature flag enabled" — the gate exists and works.

---

## Safe-to-close NOW

| # | Title | Verdict | Evidence |
|---|---|---|---|
| **#937** | Two Apple Vision providers — consolidate or label, prevent duplicate-add | **DONE — close** | Backend `_seed_builtin_providers()` in `main.py:162-283` now seeds three distinct models: `apple-intelligence` (text), `apple-vision` (OCR), `apple-speech` (transcription). Duplicate-add dedup landed: `app_db.save_model` upserts by `(provider_id, model_id)` (see test `test_re_adding_same_model_id_updates_existing_row` in `test_app_db_model_dedup.py`). Label ambiguity is resolved — all three have distinct names and capability arrays. |
| **#242** | Add provider QA checklist | **DONE — close** | Issue body is "Define the provider QA checklist" with no acceptance criteria pointing to code. The checklist exists as part of release gate #484. This is a meta/docs task that was superseded. Close as completed via #484. |
| **#283** | Re-enable AI Advanced settings sub-tab after 0.0.2 | **DONE — close (as designed)** | `FeatureManager.isSettingsAIAdvancedTabEnabled` exists (`FeatureManager.swift:138`), `settingsAIAdvancedTabEnabledInternal = false` by default. Gate is wired into `AISettingsView.body`. The issue says "hidden through 0.0.2" — that contract is fulfilled. Close as intentional gating (enable with flag when ready). |

---

## PARTIAL — work remains

| # | Title | Verdict | Evidence | Missing |
|---|---|---|---|---|
| **#1344** | First launch: Settings doesn't auto-select Apple Intelligence models | **PARTIAL** | Backend `_ensure_default_ai_defaults()` (`main.py:286-329`) correctly seeds `default_text_provider=apple`, `default_text_model=apple-intelligence`, `default_vision_model=apple-vision`, `default_audio_model=apple-speech` on startup for any unset key. SwiftUI `loadDefaults()` fetches these and calls `loadModels(for:)` per slot. **BUT**: `loadDefaults()` has a first-run guard that only auto-sets provider if `textProvider.isEmpty && visionProvider.isEmpty && audioProvider.isEmpty` simultaneously — if any one is set, the others don't auto-populate. More critically, `loadModels()` is async and `defaults.textModel` (etc.) is set from the fetched value, but the Picker renders synchronously before `loadModels` completes, so on first launch the model list arrives after render and the saved `apple-intelligence` model_id may not match any row yet visible. The `$small` / `$large` slots (`smallProvider`, `largeProvider`) are seeded to `apple` on backend but there is no equivalent Swift first-run guard for those slots — they may show "None" until user visits Settings. Daniel's live report confirms the issue. | Fix: ensure `loadDefaults()` triggers `loadModelsResettingSelection` (not `loadModels`) for all non-empty provider slots, preserving the saved model string after the async list arrives. Also verify `$small` / `$large` slots are seeded in the Swift first-run path. |
| **#284** | Re-enable Settings tabs (General/Backend/Models) after 0.0.2 | **PARTIAL** | All three gates exist in `FeatureManager.swift` (`isSettingsGeneralTabEnabled = true` by default!, `isSettingsBackendTabEnabled = false`, `isSettingsModelsTabEnabled = false`) and `SettingsView.body` honours them. **General tab is already re-enabled** (default `true`). Backend and Models tabs are still gated. The issue asks for all three to be re-enabled and validated. Close once Backend and Models tabs are validated and flags flipped. | Enable `settingsBackendTabEnabledInternal` and `settingsModelsTabEnabledInternal` defaults + validate tabs. |
| **#752** | Settings → Local Models tab: enable + download/manage local model weights | **PARTIAL** | `LocalModelsSettingsView.swift` exists with Whisper + Embeddings sections, list/download/delete/size UI, all wired to `GET/POST/DELETE /api/local-models`. Backend `LocalModelManager` covers Whisper + Embeddings models. Tab is gated behind `isSettingsModelsTabEnabled = false`. **BUT**: the Models tab feature flag is still off (same as #284). Ollama / Hugging Face local LLMs are not covered — only Whisper + Embeddings. | Enable the Models tab flag; validate the tab; extend scope to cover Ollama local LLM discovery if #485 acceptance criteria requires it. |
| **#484** | [Release Gate] Wire: Providers + API Keys | **PARTIAL** | Providers, API keys, test-connection, catalog browsing are all implemented and wired. Provider add wizard exists (`AddProviderSheet+Step1.swift`, 3-step flow). `POST /api/providers`, `GET /api/providers/catalog`, `POST /api/providers/{id}/test` exist. **But the checklist in the issue includes items not yet verified**: "Settings Backend tab visible" (#284 above, still gated), "Providers QA checklist passed" (#242). Release gate should not be closed until those checklist items are formally verified. | Verify checklist items with Daniel; close after his sign-off. |
| **#485** | [Release Gate] Wire: Local Models | **PARTIAL** | `LocalModelsSettingsView` exists but gated (Models tab `= false`). Ollama discovery is not implemented — `local_models.py` covers Whisper + Embeddings only, no Ollama auto-discover route. `GET /api/local-models` serves Whisper + Embeddings; acceptance criteria calls for Ollama discover + Peekaboo screenshots. | Unlock Models tab, add Ollama discovery, do Daniel's checklist. |

---

## GENUINELY OPEN — no implementation found

| # | Title | Verdict | Evidence | Notes |
|---|---|---|---|---|
| **#1059** | Consolidate ~6 separate provider/model picker UIs | **OPEN** | The 6 separate picker surfaces all still exist: `NodeProviderModelSelector.swift`, `AISettingsView+Helpers.swift:providerPicker`, `AIModelSelectionView.swift`, `ModelPickerSheet.swift`, `AgentSettingsView.swift`, `ChatViewToolbar.swift:modelPicker`. No shared `ProviderModelPicker` component exists. The issue is correctly labelled `needs-design`. | Needs design pass before implementation. |
| **#1200** | Model browser: searchable OpenRouter catalogue in Settings | **OPEN** | No OpenRouter model browser view exists. `AIModelSelectionView.swift` exists (a simpler picker), but it is not the searchable/filterable catalogue described. No `openrouter.ai/api/v1/models` fetch exists in any Swift file. | Labelled `priority:P3`. Needs new feature work. |
| **#1342** | Centralize model downloads to Application Support/Fichero/models/ | **OPEN** | `local_models.py` uses `MODELS_BASE = ~/Library/Application Support/com.fichero.fichero/models/` for Whisper/Embeddings already — partial overlap. But spaCy models still live in venv pip packages; HF/fastembed cache still at `~/.cache/huggingface`. No unified storage service exists. Labelled `needs-design`. | Needs design pass. |
| **#1152** | Model management UI: user-selectable spaCy/embedding models | **OPEN** | `LocalModelsSettingsView` covers Whisper + Embeddings; spaCy models are not listed or manageable in any UI. No spaCy model download/delete route in the backend. `FeatureManager.isSettingsModelsTabEnabled = false` so tab isn't even visible. | Needs design + implementation. |
| **#732** | Surface provider-side errors clearly in UI (quota/429/auth) | **OPEN** | Backend has `ProviderQuotaError` (`llm.py:319`) and `_is_provider_quota_error` with quota/rate detection, and `ErrorCategory` enum in `errors.py` (has `AUTHENTICATION`, `NETWORK`, etc.). But the API response to the Swift client for file-level errors does not carry a `category` field — `WorkflowExecution.workflowError` is a plain String. Activity view shows `errorCount` (int) with no category. No provider-error classification shown in the Activity UI. No action buttons ("Top up account", "Switch provider") exist anywhere in Swift. | Needs backend classification in the workflow file-error response + Swift UI work. |
| **#854** | Apple Intelligence: proactive token budgeting (waiting on SDK 26.4) | **OPEN** | Issue explicitly says "waiting on Xcode CLT 26.4 SDK update". No fm-bridge `--token-budget` flag exists. Intentionally deferred. | Do not start until SDK available. |
| **#843** | Apple Intelligence structured output: polish (schema-in-prompt, typed guardrail, token usage, pre-validation) | **OPEN** | None of the 4 items (includeSchemaInPrompt, typed GenerationError.guardrailViolation, token usage telemetry, schema pre-validation) are implemented in `fm-bridge/main.swift` per the issue. Not investigated in depth (labelled `priority:P3`). | Low priority; no blocking dependency. |
| **#853** | Apple Intelligence: prewarm() + contentTagging useCase | **OPEN** | No `--prewarm` or `--use-case` flags in fm-bridge. No `apple_intelligence_token_budget()` Python helper. Labelled `priority:P3`. | Low priority. |

---

## Live-relevant (#1344 and #937) deep dive

### #937 — DONE
The "two Apple Vision providers" bug is resolved at the data layer:
- `_seed_builtin_providers()` now creates exactly three Apple models with distinct model_ids and clear names
- Duplicate-add is prevented by `save_model` upsert constraint tested in `test_app_db_model_dedup.py`
- `NodeProviderModelSelector.swift` already hides the Apple Intelligence catalog entry when `toolSupportsAppleVision` to avoid the visual duplicate in the workflow picker
- **Close #937.**

### #1344 — GENUINE BUG
The backend does seed defaults correctly on startup. The issue is in the Swift UI path:

1. `loadDefaults()` fetches the saved defaults (provider + model strings like `"apple"` + `"apple-intelligence"`)
2. For each non-empty provider, calls `loadModels(for:into:)` — which fetches the model list **asynchronously**
3. The Picker binds to `$defaults.textModel` (already `"apple-intelligence"` from the fetched defaults) and to `$textModels` (empty until the async load completes)
4. When `textModels` arrives, it contains `ModelInfo(modelId: "apple-intelligence", ...)`, and the Picker should then show it as selected
5. **The gap**: `loadModels` is `func loadModels(for:into:)` which does NOT call `selection.wrappedValue = first.modelId` — it only populates the list. The selection is already set from fetched defaults. **This should actually work** as long as the model_id in defaults matches a model_id in the loaded list.

The real first-launch gap: if this is a truly fresh install where `_ensure_default_ai_defaults` has run **before** Apple models were seeded (a race), or if the Swift `loadDefaults()` first-run guard fires after the models are already set (meaning the guard is skipped), the `$small`/`$large` slots have no Swift-side guard at all — only the backend seeds them. Daniel's repro is "cleared prefs" which would also clear the backend `app_settings` table, so `_ensure_default_ai_defaults` would reseed on next launch. Net: **the Settings pane should show correct selections on second open but may show empty on first-open before the backend's `lifespan` startup has run.**

Action needed: ensure backend seeds defaults before returning the first health check (already the case — `_seed_builtin_providers` runs in `lifespan`), and verify `loadDefaults()` triggers after the backend is confirmed running. The Swift guard in `loadDefaults()` for the `isEmpty` check also needs extending to cover `$small`/`$large`.

---

## Recommended action list (priority order)

1. **Close #937** — done, clean.
2. **Close #242** — meta task, superseded.
3. **Close #283** — gate exists; re-open if/when you want to un-gate Advanced tab.
4. **Fix #1344** — P2 bug Daniel hit live. The `$small`/`$large` Swift first-run guard is missing; verify async load→select path works end-to-end.
5. **Enable Models tab flag + validate** (#284, #752) — unblocks #752's existing UI.
6. **Ollama discovery** (#485) — release gate won't pass without it.
7. **Provider error surfacing** (#732) — P1, needs backend + Swift work.
8. **Defer #1059, #1200, #1342, #1152** — needs-design / P3.
9. **Defer #854, #843, #853** — waiting on SDK or P3.
