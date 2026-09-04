# MLX-in-Fichero — audit, fixes, OCR matrix, tool sweep — 2026-09-03

Lane: MLX / local-inference provider, worker on `integration`.
Test material: real 17th-c. colonial Spanish secretary-hand page scans from the
live library (3660×4878 TIFF), downscaled read-only into `/tmp/mlx-lane/`.
Scratch library only; zero cloud calls; one inference at a time.

Commits: `e1f1a4407`, `3ed311ca3`, `99c004720`, `1071a8e50`.

## 1 · The headline

**On-device OCR had never worked, and could not have.** Every model in
`MANAGED_MLX_MODELS` is a vision/OCR VLM, and every one was served by
`mlx_lm server`, whose `process_message_content` rejects any non-text content
part with `"Only 'text' content type is supported."` The server returns that
as a 404.

Verified live, not inferred: Qwen3-VL-8B-4bit under `mlx_lm server` answered
"Say hello in three words." in 56s and returned
`404 {"error": "Only 'text' content type is supported."}` for the very image
the model exists to read.

Daniel's "backend is done, UX is not set up" was half right. The backend
*surface* was complete and the Settings pane was rich — runtime provisioning,
catalog with size + memory floor + capability chips, Download with progress and
Cancel, Delete. What was missing sat between them: **the models could not be
reached, could not be seen, and could not be named.** Four separate breaks, all
found by running the thing rather than reading it.

## 2 · What was already built (do not rebuild)

| Layer | State |
|---|---|
| `mlx_runtime.py` venv provisioner | complete |
| `mlx_model_store.py` — HF `snapshot_download`, job/cancel/delete, disk accounting | complete |
| `/api/local-inference/*` routes | complete |
| Swift `LocalInferenceStore` + `LocalInferenceSettingsView` | complete |
| MLX folded into the Providers tab (#4503) | already landed |
| Catalog holding Daniel's three named models | already there |

## 3 · The four breaks, and the fixes

| # | Break | Fix |
|---|---|---|
| 1 | Vision models served by an image-blind server | runtime provisions **mlx-vlm**; vision models launch `mlx_vlm.server`. A runtime with only mlx-lm now reports UNPROVISIONED — it genuinely cannot do what the catalog advertises (same honesty rule as #4504) |
| 2 | Downloaded models invisible in every picker | oMLX enumeration was one call to the sidecar's `GET /v1/models`. Server down → zero models — and the sidecar starts on demand FOR A RUN, so you could not pick the model that would have started it. Installed models are now listed from the **store**, with real display names and vision capability |
| 3 | Catalog id sent as the wire `model` name | `"Qwen2.5-VL-3B"` names a row in *our* catalog; the sidecar went to Hugging Face for it and got `401 Repository Not Found` — over a model already installed and already loaded in the process being asked. Managed models now go over the wire as the resolved snapshot path |
| 4 | 120s cold-start budget | `mlx_vlm.server` preloads the model BEFORE uvicorn binds, so the port refuses connections for the entire load and the probe cannot tell it from nothing being there. A 3B on a pressured 16 GB M1 needed >145s. Raised to 300s; health is polled, so a fast start still returns fast |

Plus two diagnostics: a dead sidecar reported uvicorn's farewell
(`"INFO: Application shutdown complete."`) instead of the cause
(`"[Errno 48] Address already in use"`, three lines up in the same buffer); and
`exercise_tools.py` counted on-device MLX as a **cloud** call, because its
local-provider set said `"mlx"` and the engine's `ProviderType` is `"omlx"` — a
string that matched nothing, so `--max-cloud-calls 0` refused to run the free
local models the flag exists to make room for.

## 4 · Model quality matrix — HTR on real secretary hand

Fichero's own `build_transcribe_prompt`, `language: es`.

| Model | Size | Speed | Verdict |
|---|---|---|---|
| **Qwen2.5-VL-3B-4bit** | 2.9 GB | 9.1 tok/s | **Usable.** A genuine line-aligned diplomatic transcription on p1 (442 tok). Refused p2/p3 (`[ilegible]` / `Sin texto`) — honest refusal, not invention |
| **Apple Vision** (baseline) | on-device | instant | **Garbage** on all three pages (`звенинія`, `·º98`). The 3B beats it decisively |
| **Qwen3-VL-8B-4bit** | 5.4 GB | — | **Unusable on 16 GB.** Vision prefill drove swap to 24 GB of 25 GB, no token in ten minutes. Text prompts work fine at 16 GB, which is exactly what made it look healthy |
| **Chandra** | 5.8 GB | — | **Untested.** `mlx-community/chandra-4bit` exists and is now what the catalog points at (was a personal 8-bit repo, 8.2 GB). Not downloaded — held the disk floor |
| **Nanonets-OCR** | ~4.8 GB | — | **Untested.** MLX 4-bit exists but the upstream repo carries two overlapping weight sets (~8.7 GB download for a ~5.6 GB model) |

Nothing here was forced: a model with no MLX build, or no run inside Fichero,
says so rather than borrowing a reputation.

## 5 · Tool sweep — Qwen2.5-VL-3B, vision family

`scripts/exercise_tools.py`, one page, one inference at a time, zero cloud calls.

| Tool | Verdict | Note |
|---|---|---|
| `transcribe` | **green** | Best OCR output here; real diplomatic transcription |
| `classify` | **green** | `book_page` — correct |
| `classify_script` | **green** | `htr`, conf 0.9, "16th–19th century" — correct and well calibrated |
| `describe` | **green** | Correctly reads it as an old manuscript/decree |
| `extract` | **green** | Correctly identifies Spanish, legal/judicial matter |
| `layout` | **green** | Structured JSON, real content, one column |
| `quality` | **green** | Plausible scores, names blur and lighting |
| `tags` | **green** | Accurate |
| `analyze` | **green** | Correct (from the earlier full run) |
| `caption` | **green-ish** | Correct shape, but calls the Spanish text "Latin" |
| `handwriting` | **defect** | ALL-CAPS output with lines repeated verbatim — worse than `transcribe` on the same page, and it violates the prompt's own no-repeat rule. Model-quality, not plumbing |
| `table_extract` | **defect** | Invented a table (`0,1,2…30`) on a page with none. Root cause is legible: it read the **cm ruler** in the scan margin as a table. Understandable perception, wrong output — and nothing guards a fabricated table |
| `similarity` | **honest refusal** | "requires at least 2 images" — correct |

16 palette placeholders (`if`, `loop`, `to_excel`, `save_to_library`, …) call no
model and were not run.

## 6 · Whisper

Fixed by a sibling lane during this session, building on the mlx-vlm pattern:
`mlx-whisper` now installs into the same isolated runtime venv, keeping torch
out of the shipped engine. `has_audio()` is deliberately its own capability —
a runtime that serves every text and vision model is not "unprovisioned"
because it cannot transcribe.

The gap it closed: the Downloads tab listed **six** Whisper models with sizes,
speeds and Download buttons, and all six failed with
`ImportError: openai-whisper is not installed` — buttons that could not work.

## 7 · Open, for Daniel

1. **Qwen3-VL-8B's 16 GB floor is honest for LOADING and false for vision.**
   24 GB is the truthful gate, and it would drop the flagship model off every
   16 GB Mac including yours. Left at 16 GB with the measurement recorded in a
   comment rather than changed silently. Your call.
2. **`table_extract` has no fabrication guard.** A page with no table should
   yield nothing, not a table read off the ruler.
3. **A healthy sidecar this engine did not spawn is misread as a crash.** The
   manager conflates "I started it" with "it is running", then restarts onto a
   port that is already held, twice, and gives up. Triggered here by my own
   orphan process, but the conflation is real.
4. **Swift changes in `3ed311ca3` are UNBUILT** — no xcodebuild in this lane,
   and swiftlint's sourcekit failed to load in this environment.
