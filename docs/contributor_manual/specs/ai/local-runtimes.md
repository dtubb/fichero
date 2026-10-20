# Local Runtimes and Providers — how each model runs — Design Spec (#5367)

> **Consolidating design:** `ai/where-models-run.md` (#5582) owns choosing a model together with where it runs, local or remote, under one job model; this spec keeps how each runtime on this Mac ships and loads.

> Milestone: ai-settings
> Manual: TBD — a "What runs on your Mac" section in the Settings part: each runtime (Kraken,
> Apple's on-device models, MLX, Whisper, spaCy, the search model, Tesseract, cloud providers),
> whether it came with the app, came with macOS or needs a download; what its status dot means;
> what "unavailable in this build" means and why; how models are downloaded and checked; why
> Fichero loads one heavy model at a time; and what "nothing leaves this Mac" stops.

> Design-led (Testing Constitution). **Status: DRAFT, 2026-10-01 — awaiting the maintainer.**
> Written read-only against the integration tree (branch `mbp-overnight`) from a review of every
> runtime the same day. Server paths are relative to `fichero-server/src/fichero_server/`; app paths
> name the Swift file. Claims about code were re-read for this spec unless marked *(review)*,
> which means taken from the 2026-10-01 runtime review without a second read.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, unproven or partly wired · **[GAP]**
> intended, never built · **[BROKEN]** the code contradicts the intent. Every non-OK line cites
> an issue.
>
> **Where this sits.** Three specs describe one machine and must agree:
> - `source/models-chains-and-projects.md` says **what** a model is (the card, `source.model.*`),
>   what a job takes and gives, how a recipe names a model, and how candidates are ranked.
> - `ui/activity-and-automatic-work.md` says **when and where** work runs (the one job model,
>   lanes, load once, group by model, co-run only if it fits, measure the processors).
> - **This spec** says **how** each runtime runs: how it ships, its card id, how it loads and stays
>   resident, its batching and accelerator, its measured memory, how it reports as a job, how its
>   models are found and verified, its honest status, and its keys and egress.
>
> `ai/ai-settings.md` owns the Settings surface (rows, tabs) and `ai/ai-settings.md` owns where a
> key lives. Neither is restated here; where this spec needs them to change, it says so under
> "Requests to other specs".

## Intent

A researcher should be able to trust three things about every model Fichero offers. **It works
here**: if Settings shows it as ready, it runs in the app they installed, including the sandboxed
one, and if it cannot run here the row says so and why. **It is the model it says it is**: every
model has one pinned identity, the same in Settings, a recipe and the record of what a reading was
made by, and a download is checked before it is used. **It is not wasteful**: a model is loaded
once and used fully, the Mac holds one heavy model at a time unless two fit, and every load,
download and call is a visible job with its progress, cost and a typed reason when it fails.

Today none of the three holds across the board. The runtimes grew one at a time, each with its own
download path, status check and loading habit. This spec gives them one shape, so that the
activity queue can schedule them and a recipe can name them.

## Prior art (what we build on)

- **Hugging Face Hub** pins by repository plus **commit SHA** (`revision=`), and `snapshot_download`
  verifies files by their ETag/sha256. The MLX store already does this (`llm/mlx_model_store.py`).
  We use the same scheme for every Hub-hosted weight.
- **Zenodo / HTRMoPo** (Kraken's model repository) pins by **version DOI**; the record lists each
  file with an MD5 checksum. `htrmopo` reads the card front-matter. We pin by version DOI and
  verify the file checksum.
- **Ollama** pins by manifest **digest**; LM Studio by file. Hosted APIs (OpenAI, Anthropic,
  Google) publish **dated model ids** beside floating aliases (`-latest`). A floating alias cannot
  be pinned; the dated id is the closest a hosted model gets.
- **Apple's frameworks** (Vision, FoundationModels, Speech) are versioned by the OS. Apple's own
  guidance for FoundationModels is to keep one `LanguageModelSession` and call `prewarm()` before
  the first request; Vision document requests pay a system-wide warm-up once.
- **Core ML / ONNX Runtime** pick an execution provider (CPU, GPU, Neural Engine); fastembed uses
  ONNX Runtime on the CPU by default and accepts a `batch_size`.
- **spaCy** recommends one loaded `Language` per pipeline and `nlp.pipe(texts, batch_size=…)` for
  many documents.
- **Mac App Store sandbox**: an app may not execute code it downloads. Data (weights,
  `traineddata`) may be downloaded; code (wheels, interpreters, binaries) must ship inside the app
  at build time. Fichero already ships Kraken this way (`[tool.fichero.kraken_bundle]` in
  `fichero-server/pyproject.toml`).

What we do differently: one id scheme across every source above (others keep one per ecosystem),
because a Fichero recipe chains models from several ecosystems and must pin them all the same way.

## What exists today (verified 2026-10-01)

| Runtime | How it ships | Loading | Accelerator | Memory | Pin | Status in Settings |
|---|---|---|---|---|---|---|
| **Kraken segmenter (blla)** | Bundled at build time, in-process (`[tool.fichero.kraken_bundle]`, version 7.1.1) | **Reloaded every page**: `blla.segment(image)` at `llm/kraken_runtime.py:586,599` | CPU torch, utility QoS, threads capped; GPU measured no faster | 2.3–3.6 GB a page, **never given back** *(review; commit 2415b4c31)* | The bundled wheel's version | Row exists; status from `/api/providers/local-runtimes` is not read by the app |
| **Kraken reader** | Weights fetched from Zenodo by `htrmopo`; two DOIs hard-coded (`llm/kraken_runtime.py:122-139`) | **Reloaded every page**: `models.load_any(model_path)` at `:600` | CPU | as above | Version DOI, **no checksum**; "newest `.mlmodel` in the folder" *(review)* | In-memory install job, not Activity |
| **YOLO layout** | Ultralytics bundled at build time (`pyproject.toml`); weights downloaded on request into the shared models folder (`llm/yolo_runtime.py`, built 2026-10-10) | Loaded once per model, in process | GPU (MPS) | not measured | the stock DocLayNet YOLO11n (`hantian/yolo-doclaynet`), or a model trained in the project | a `download-model` job |
| **PyTorch** | Bundled (with Kraken and PyKEEN) | — | CPU only; PyKEEN hard-codes `torch.device("cpu")` *(review)* | — | bundle | — |
| **Apple Vision** (`VNRecognizeTextRequest`) | OS, through PyObjC (`pyobjc-framework-Vision` is declared) | Per page; **at least four requests a page**: accurate, a fast retry, and three overlapping strips that always run (`workflows/tools/vision_base.py`, `_strip_bands`, promoted to a base pass on 2026-08-23) | OS-chosen (Neural Engine/GPU) | OS-owned | OS version; not recorded on the reading | Always green |
| **Apple document reader** (`RecognizeDocumentsRequest`, macOS 26 and later) | OS, built into `fichero-server/bin/fm-bridge/FmBridge.swift` (`runRecognizeDocuments`, `:537`) | **No Python caller.** Measured cold 168 s on a 929×1346 scan (45 s on a blank image), 0.7 s warm (`FmBridge.swift:588-589`) | OS | OS | OS | none |
| **Apple Intelligence** (FoundationModels) | OS, through fm-bridge | **One new bridge process per call** (`llm/__init__.py:1959`, `asyncio.create_subprocess_exec`); translation likewise *(review)* | OS | OS | OS | Factory default for every text tier (`db/app.py`) |
| **Apple Speech** (`SFSpeechRecognizer`) | **Not bundled**: `workflows/tools/audio_base.py:193` imports `Speech`, and `pyobjc-framework-Speech` is not in `fichero-server/pyproject.toml` | — | — | — | — | **Factory audio default** (`db/app.py:78`, `apple-speech`) |
| **Whisper** (mlx-whisper) | Bundled at build time (`[tool.fichero.mlx_bundle]`) | In the engine's process; audio decoded with PyAV, no `ffmpeg` (`llm/whisper_runtime.decode_16k_mono`) | Metal | not measured | mlx-community repos, downloaded on request |
| **MLX LLM/VLM** | Bundled at build time (`[tool.fichero.mlx_bundle]`: mlx, mlx-lm, mlx-vlm) | The model server runs inside the engine's process (`llm/mlx_in_process.py`); its batch is the client's pages at once (`local_inference.reads_at_once_for`) | Metal | the memory need: `compute.memory.need-is-weights` | mlx-community 4-bit builds, downloaded on request | ready, or the model to download |
| **spaCy** | `es_core_news_sm`, `en_core_web_sm` 3.8.0 bundled as pinned wheels; others downloaded as data folders into the model store (2026-10-04) | **Two caches load the same language twice** (`knowledge/spacy_ner.py:300`, `knowledge/spacy_svo.py:204`); `nlp(text)` per page 2–3 times, never `nlp.pipe` | CPU | not measured | wheel version | NLP stage not counted in progress |
| **Embeddings** (fastembed / ONNX) | `fastembed` bundled; **bge-m3** (default, `db/embeddings.py:349-361`) downloaded lazily on first embed | Resident while used; released after 600 s idle (#5283) | CPU ONNX, fp32, 64 passages a call *(review)* | ~1.5 GB resident | **No HF revision**; the "space contract" pins pooling and normalisation only; chosen by `FICHERO_EMBED_MODEL` | Downloads tab only |
| **Tesseract** | **Not present.** Only `.box`/TSV are parsed | — | — | — | — | — |
| **Cloud** (26 provider types) | langchain clients | per call; 12 pages at once in a run (7b5a4dc1e) | — | — | **bare model-id strings** | Keys: see below |
| **Ollama / LM Studio** | local servers, OpenAI-compatible | whatever the server holds | — | — | none | Always green |

Cross-cutting facts:

- **The honest status endpoint exists and nothing reads it.** `GET /api/providers/local-runtimes`
  (`api/routes/ai/provider_models.py:1274`) returns `installed`, `available`, `reason` and
  `install_action` for MLX, spaCy, Kraken and Whisper. No Swift code calls it (searched the app
  tree); the provider row's dot is still `isLocalProvider || hasApiKey`. Apple, embeddings,
  Tesseract and the local servers are not in it.
- **Five progress systems** for model work *(review)*: MLX download/provision jobs, the
  `LocalModelInstallCoordinator`, `/local-models` `BackgroundTasks`, Whisper's `_DOWNLOAD_STATE`,
  and fastembed's silent first-use download. None writes Activity.
- **The egress gate** `_enforce_local_only_provider` (`llm/__init__.py:1211`) is called for chat,
  vision, audio, translation and structured chat, but **not** inside `chat_with_tools`
  (`llm/__init__.py:2971`, which goes straight to `get_langchain_model`) or `structured_output`
  (`:3067`) *(review for the second)*. `is_local_only()` reads the `local_only_ai` setting
  (`:1195`), which nothing writes and no surface shows (#5368). The chat route's silent fallback to
  `openai/gpt-4o-mini` was removed in 7feee5872 and is pinned by
  `fichero-server/tests/unit/api/test_chat_never_falls_back_to_the_cloud.py`.
- **Keys**: `keychain.has_api_key` (`security/keychain.py:303`) reads only the engine keychain, not
  the keys the app supplies in memory, so a working key shows "Needs API Key"; Add Provider writes
  the key into the engine keychain (#5369).
- **Errors are typed in the runtimes** (`LocalOnlyViolationError` at `llm/__init__.py:707`,
  `KrakenMemoryUnavailableError`, `AppleUnavailableError`, `ProviderQuotaError`) but the runner
  classifies failures by matching message text *(review: `execution/runner.py:317-370`)*.
- **Speed, measured on this Mac on 2026-10-01** (from the workflow-runner review): Kraken
  segmentation takes 17–20 s a page on the CPU and is no faster on the GPU; about 10 s of it is
  single-threaded line post-processing. At background QoS it measured 426 s against 23 s at
  utility (`llm/kraken_runtime.py:527-530`).

## The design

### 1. One card id for every model

Every model has one **card id**, a string with three parts:

```
<runtime>:<source>@<version>
```

| Runtime | `source` | `version` | Example |
|---|---|---|---|
| `kraken` (built-in) | `builtin/<name>` | Kraken's bundled version | `kraken:builtin/blla@7.1.1` |
| `kraken` (Zenodo) | `zenodo/<version DOI>` | `sha256-<file hash>` | `kraken:zenodo/10.5281/zenodo.13788177@sha256-9f2c…` |
| `mlx`, `whisper`, `embed`, `yolo`, `tesseract` | `hf/<repo>` | the 40-character commit SHA | `embed:hf/BAAI/bge-m3@5617a9f…` |
| `tesseract` (traineddata) | `tessdata/<lang>` | `sha256-<file hash>` and the tessdata release | `tesseract:tessdata/frk@sha256-…` |
| `spacy` | `pkg/<package>` | package version | `spacy:pkg/es_core_news_sm@3.8.0` |
| `apple` | `<framework>/<request or model>` | `os` (the macOS build is recorded on each reading) | `apple:vision/recognize-text@os` |
| `ollama` | `<name>:<tag>` | manifest digest | `ollama:qwen2.5vl:7b@sha256-…` |
| `cloud` | `<provider>/<model id>` | `dated` or `alias` | `cloud:anthropic/claude-sonnet-4-5-20250929@dated` |

Rules that make it work:

- **The id is the identity.** Recipes, role defaults, runtime configurations, the making record of
  every reading and the jobs table store the card id; no surface stores a bare model name. A
  recipe's YAML form (`{hf: …, revision: …}`, `{zenodo: …}`, `{spacy: …, version: …}`, as in
  `source/models-chains-and-projects.md` section 9) is the same id split into fields; the engine
  turns one into the other.
- **Apple and alias cloud models cannot be pinned, and the card says so** (`pinnable: false`). A
  recipe step naming one is marked "can change under you". Each reading made by one records what
  actually answered: the macOS build for Apple, the dated id the provider returned for a cloud
  alias.
- **A version that is gone is refused, never replaced** (`source.recipe.pinned-model-gone`): the
  check names the step and offers the rule's next candidate.
- **An embedding space is keyed by the embedding card id**, so a weights update is a new space,
  never a silent mix with the old vectors.

### 2. How each runtime ships

Code ships inside the app at build time; only **data** (weights, `traineddata`) downloads at
run time. A spaCy pipeline is published as a package, but what it needs to run is its data folder
(config, meta, weights): Fichero downloads that folder alone, as files, into the app's model store,
and never installs or runs the package's code (ruled 2026-10-04). The languages that ship in the app
stay bundled. Every runtime is in one of three
states in a given build, and the card and the row say which:

| State | Meaning | Runtimes |
|---|---|---|
| **bundled** | in the app; may need a weights download | Kraken, fastembed, spaCy (bundled languages), PyTorch; Tesseract once added (binary bundled, `traineddata` as data); MLX and mlx-whisper once bundled (open question 1) |
| **OS** | comes with macOS; availability probed, never assumed | Apple Vision, the document reader, FoundationModels (needs Apple Intelligence on and a capable Mac), Speech (once `pyobjc-framework-Speech` is bundled) |
| **unavailable in this build** | needs code installed at run time, which the sandbox refuses | none since 2026-10-09: MLX, mlx-whisper, Kraken, spaCy and Ultralytics ship inside every build (extra spaCy pipelines download as data: `runtime.spacy.pipelines-download-as-data`) |

"Supported" is worked out from the build (a constant written by the bundle step), never from an
environment default.

### 3. Loading and residency (the activity lane's rules, per runtime)

The local ML lane (`activity.lane.*`) owns scheduling. Each runtime gives the lane what it needs to
schedule well: a **load** that happens once, a **batch** entry point, a **resident size** from its
card, the **processor** it uses, and an **unload**.

| Runtime | Heavy? | Loaded once as | Batch unit | Processor | Resident size (card) |
|---|---|---|---|---|---|
| Kraken segmenter | heavy | one net per worker process | a document's pages in one locked call | CPU (post-processing single-threaded) | 2.3–3.6 GB measured |
| Kraken reader | heavy | one net per model path per worker | all lines of a page; pages of a document | CPU | measured with the segmenter |
| MLX LLM/VLM | heavy | one in-process model (open question 1) | several line crops, or a page with its boxes, per call | GPU (Metal) | measured per size class; until measured, the one rule `compute.memory.need-is-weights` |
| Whisper | heavy for medium and up | one resident transcriber | files of a folder | GPU (Metal) | to be measured per size |
| Embeddings | heavy (bge-m3) | one ONNX session | passages, `batch_size` passed | CPU (Core ML provider to be tried) | ~1.5 GB measured |
| YOLO detector | heavy | one model | pages | GPU (MPS) or CPU | to be measured |
| spaCy | light | one `Language` per language | `nlp.pipe` over the derivative queue's batch; one parse shared by NER, SVO and morphology | CPU | to be measured |
| Tesseract | light | one engine per language set | lines or pages | CPU | small; measured |
| Apple Vision | light (OS-owned) | one warmed handler | one page, with conditional extra passes | OS (Neural Engine/GPU) | not ours |
| Apple document reader, FoundationModels, translation | light to us, heavy to the Mac | **one resident fm-bridge** (JSON lines over stdin/stdout), warmed in the background | one request per page or prompt | OS | not ours; counted as "system" |
| Cloud | — | none | the provider's rate limit, per provider | network lane | none |

Cards carry **measured** resident memory where it has been measured on a Mac of this class, and an
estimate labelled as one otherwise. The lane uses these numbers for "co-run only if it fits"; on an
8 GB Mac only one heavy model is resident, and the embedder counts as one.

### 4. Every load, download and call is a job

Each runtime reports through the one job model (`activity.one-job-model`), never its own dict:

- **Download** of weights or `traineddata` is a `download-model` job in the global jobs table, with
  bytes done and total, through **one download path** for every runtime. It verifies before it
  marks the model installed: the HF file hashes, the Zenodo file checksum, the `traineddata`
  sha256. A partial download is never installed.
- **A first-use download inside a run** (bge-m3 on first embed, a Kraken reader fetched
  mid-workflow) is a child `download-model` job of the step, which waits with "Waiting for model
  download" (`activity.global-work-is-the-macs`, which absorbed the request for
  `activity.first-use-download-is-a-job`).
- **Loading** a heavy model is visible on the step's row as "Loading <model>" with elapsed time, so
  a 30–300 s MLX warm-up or a 168 s Vision warm-up is never a silent stall.
- **A call** belongs to its page job; it reports progress, the card id that answered, and, for a
  priced model, its usage through the one pricer.
- **An error** carries the runtime's typed kind (memory, runtime unavailable in this build, needs a
  key, egress refused, quota, model missing) from the exception it raised, so the row can say
  "Waiting for memory" rather than "Failed".

### 5. Finding a model

Finding is `source.find.*`'s; this spec adds only how a found model becomes runnable. A found card
names its runtime; if the runtime is unavailable in this build, the card says so and is not
offered as a download. Kraken readers come through `htrmopo` (structured cards), Hub models through
the Hub API, Tesseract languages from the tessdata list. Downloading creates a row under the
runtime's provider through the one download path (`source.find.download-is-a-provider-row`).

### 6. Honest status in Settings

Every local runtime's row reads its status from `/api/providers/local-runtimes`, extended to every
runtime (Apple's four, embeddings, Tesseract, Ollama and LM Studio by probing their server) and
given one more field, the build state of section 2. The row says one of: **Ready**, **Needs a
download** (with size), **Loading**, **Stopped**, **Unavailable in this build** (with the reason),
**Unavailable on this Mac** (with the reason: chip, memory, Apple Intelligence off). A green dot
means Ready and nothing else.

### 7. Keys and egress

Keys are `ai/ai-settings.md`'s; this spec needs one thing from it: the status a row shows is
read through the same lookup a call uses. Egress is `source.egress.one-gate`'s; this spec lists
where the runtimes call out, so the gate can cover them: every langchain factory caller, the
fm-bridge (local), Fichero's own fetches (the weekly price list from GitHub, Zenodo and Hub
searches, tokenizer downloads for language fit), and model downloads. Fichero's own fetches carry
no library content; they are listed, become jobs, and stop when the person chooses to work offline.

## Behaviors

### A. Identity and pinning (cards)

The card's own behaviours (`source.model.card-id`, `cloud-pin-is-honest`, `weights-verified`, `embedding-space-has-revision`, `runs-here`, `licence-filled`, `jobs-replace-capabilities`) moved to the one card's home, `source/models-chains-and-projects.md`, on 2026-10-04. What stays here is how a runtime honours a card.


### B. Shipping in the sandboxed build

- `runtime.dev-engine-refuses-real-data` — **[PARTIAL]** (#5924, manager item 488, 2026-10-20; an orphan dev engine ran on the M4 for three days with `FICHERO_BASE_PATH` set to the owner's `~/Fichero`) a dev, test or harness engine REFUSES, in words and with a non-zero exit, (a) NO base path (the engine would write the real app state, `~/Library/Application Support/Fichero`), (b) a base that is or sits inside `~/Fichero`, `~/Fichero Projects` or `~/Library/Application Support/Fichero`, and (c) one inside an app's own folder: a container `~/Library/Containers/app.fichero.*` or the legacy `~/Library/Application Support/app.fichero.*` (symlinks resolved, case folded, whole path components: `~/Fichero Dev Test` is not inside `~/Fichero`). The check is `fichero_server.security.real_data_guard` (`refusal`, `refuse_real_base`, and `python -m fichero_server.security.real_data_guard <path>` for a shell). `start_backend.py` guards only in development mode (the bundled engine is the app's own and is untouched). The owner alone can run on the real app STATE on purpose with `FICHERO_ALLOW_REAL_STATE=1` (exactly `1`) typed by hand (`start_fichero_server.sh`, AGENTS.md): it lifts ONLY (a) and the default-state-dir part of (b); `~/Fichero`, `~/Fichero Projects` and every app folder stay refused with it. No script sets it and a test fails if one does. Every script under `scripts/` and `fichero-server/{scripts,bin}` that starts an engine must RUN the guard (an uncommented call to `refuse_real_base` or `-m fichero_server.security.real_data_guard`; a comment naming it does not count) or be listed, with why, in the test's `NOT_A_STARTER`; a new launcher fails the test until it does. *Not covered, said plainly: the guard checks the BASE PATH only. A request to a running engine can still open a real library by path (`FICHERO_LIBRARY_ALLOWED_ROOTS` and the open routes decide that; #5924), and an engine started by hand with `uvicorn` has no launcher to guard.* Built, unrun until an M4 pass; tested in `fichero-server/tests/unit/security/test_real_data_guard.py`.
- `runtime.models-in-the-store` — **[OK]** (2026-10-11) every model the engine downloads or finds lives in
  Fichero's own store (`model_store_root()`), never in ~/.cache: each load that can download names the store
  (`db.paths.hf_hub_dir()` as `cache_dir`; TrOCR in `economy_htr` and a tokenizer in `script_coverage` did not, and
  4.2 GB of tridis landed in ~/.cache/huggingface), and at engine start `HF_HOME`, `HF_HUB_CACHE`,
  `TRANSFORMERS_CACHE` and `SENTENCE_TRANSFORMERS_HOME` point into `model_store_root()/models/hf` unless already
  set, so a library that resolves a model by itself finds the store. Scripts run on a remote machine (a Hugging Face
  Job, a cluster) are the named exceptions. Guarded by `fichero-server/tests/unit/llm/test_models_live_in_the_store.py`.
- `runtime.code-ships-at-build-time` — **[PARTIAL]** (#5367, #4973) every runtime's code is in the
  app at build time; only weights and `traineddata` download. **Built 2026-10-09:** MLX, mlx-lm, mlx-vlm and
  mlx-whisper (`[tool.fichero.mlx_bundle]`), Kraken, spaCy and Ultralytics are bundled; MLX runs in the engine's
  process (`llm/mlx_in_process.py`); a leftover runtime folder from the pip era is deleted at start
  (`mlx_runtime.remove_runtimes_the_app_no_longer_uses`). *Not yet:* the old venv-and-pip installer code is still
  in `llm/mlx_runtime.py`, unreachable in the bundled app; it is removed when nothing calls it.
- `runtime.build-state-is-known` — **[BROKEN]** (#5367) the engine knows, from a constant written
  when it was bundled, which runtimes this build contains; the hardware check never reports a
  runtime supported because an environment variable was unset.
- `runtime.kraken.bundled-in-process` — **[OK]** (#4959) Kraken 7.1.1 ships in the engine at build
  time and runs in-process behind one locked seam (`[tool.fichero.kraken_bundle]` in
  `fichero-server/pyproject.toml`; commit 42a95db93). Specs that still say "subprocess" or
  "installed on request" are listed under Requests. *Test:*
  `fichero-server/tests/unit/packaging/test_engine_starts_without_unbundled_packages.py` (reads the
  `kraken_bundle` table from `pyproject.toml`).
- `runtime.apple.speech-or-none` — **[BROKEN]** (#5367) Apple Speech is either bundled
  (`pyobjc-framework-Speech`, with the authorisation request and the on-device-only flag) or removed
  from the catalogue and the factory defaults. Today it is the factory audio default
  (`db/app.py:78`) and its framework is not in `fichero-server/pyproject.toml`, so "transcribe
  speech" has no working local runtime in a DMG.
- `runtime.whisper.audio-decoding-bundled` — **[BROKEN]** (#5367, #4628) Whisper decodes audio
  without a tool the person must install; today it needs the `ffmpeg` command
  (`llm/whisper_runtime.py:329-331`).
- `runtime.tesseract.provider` — **[GAP]** (#4948) Tesseract is a provider: its binary is bundled
  at build time, each language's `traineddata` downloads as data with a card of its own
  (`tesseract:tessdata/<lang>@sha256-…`), and it reads pages or cut lines. Same behaviour as
  `source.model.tesseract-provider`, which owns the card; this line owns the bundling.
- `runtime.yolo.none-yet` — **[PARTIAL]** (#4948, #4947, #5525) a YOLO-family detector has a card (the recipe's
  find-regions step, `prep.yolo.regions-card`), is downloaded on request (AGPL weights are never bundled) and runs
  in process on the GPU (`llm/yolo_runtime.py`, `recipes/regions.py`; built 2026-10-10). *Not yet:* it runs in the
  recipe's own job rather than as a job on the local ML lane, so it does not yet take its turn with the other
  heavy models.
  **[OK]** (#5654) its model is listed as Kraken's readers are: `GET /api/local-models?model_type=yolo` gives its
  size before it is downloaded (`YOLO_MODELS` carries the file's size, 5.6 MB; it said 0), and the models
  catalog (`GET /api/local-inference/catalog`, MCP `fichero_models_catalog`) lists it under the `yolo` provider
  type, downloaded or not, and deletes it. Tests: `fichero-server/tests/unit/api/test_yolo_size_and_catalog_5654.py`.

### C. Loading, residency and speed

- `runtime.kraken.model-stays-loaded` — **[PARTIAL]** (#5370) the segmenter and each reader are
  loaded once per worker and reused; a document's pages go through one locked call. Built: the line
  finder and the reader stay resident between pages (`llm/kraken_runtime.py:649` `_resident`), and
  the local-model lane runs one reader's pages together (`activity.lane.load-once`, which owns the
  rule; corrected 2026-10-04, this line said nothing was resident). Still a gap: batching pages into
  one call, and several Kraken workers (`activity.run.kraken-workers`). *Test:*
  `fichero-server/tests/unit/llm/test_kraken_runtime.py::test_a_kraken_model_loads_once_and_is_replaced_not_stacked`.
- `runtime.kraken.post-processing-uses-the-cores` — **[GAP]** (#5370, #5358) Kraken's line
  post-processing (about 10 s of a 17–20 s page, on one core) is spread over the performance cores
  or overlapped with the next page's segmentation; measured before and after on the fixture pages.
- `runtime.kraken.memory-returned` — **[GAP]** (#4987, #5358) after Kraken's work is done and the
  lane's idle time passes, its memory is returned; today 2.3–3.6 GB a page stays held *(review)*.
- `runtime.apple.bridge-resident` — **[GAP]** (#5370, #854) one fm-bridge process stays resident for
  FoundationModels, translation and the document reader, speaking JSON lines; it is warmed in the
  background at launch (the `--warm-documents` path), so the 168 s Vision cold start is paid once,
  off any page, and later calls take about 0.7 s. Today each call starts a new bridge
  (`llm/__init__.py:1959`).
- `runtime.apple.document-reader` — **[GAP]** (#4948, #5370) macOS's document reader (26 and later) is a card
  (jobs: find lines, read a page), called through the resident bridge, and marks a page it reads
  sparsely as such. Today it exists only in `FmBridge.swift` with no Python caller.
- `runtime.vision.extra-passes-when-needed` — **[GAP]** (#5370) Apple Vision's fast retry and strip
  passes run when the first pass is sparse, not on every page, provided the fixture pages show no
  loss of lines; today every page makes at least four requests. The strips were promoted to a base
  pass on purpose (2026-08-23), so this needs measuring first (open question 4).
- `runtime.whisper.resident` — **[GAP]** (#5370, #4628) Whisper loads once and transcribes a
  folder's files in one resident process; today each file starts a Python process and loads the
  model (`llm/whisper_runtime.py:319`).
- `runtime.spacy.one-pipeline-per-language` — **[PARTIAL]** (#5370) one loaded pipeline per model serves NER and SVO
  (`llm/local_models.py` `load_spacy_pipeline`, with its lemmatizer, store first then bundled); pinned by
  `fichero-server/tests/unit/knowledge/test_one_spacy_pipeline_per_model_5370.py`. Still a gap: morphology on the same
  pipeline, and parsing each page once with `nlp.pipe` rather than two to three times.
- `runtime.torch.exits-cleanly` — **[PARTIAL]** (#5929; M4 crash reports 2026-10-20) a Python process that has loaded torch ends with its own exit code on macOS 27. All 25 `python3.12` reports from the GIL runs fault on the main thread in `libtorch_cpu` `at::native::mps::MetalShaderLibrary::~MetalShaderLibrary()`, called from `exit()` (SIGSEGV, or SIGABRT "pointer being freed was not allocated"): torch's static destructor at exit, not Kraken's threads, and every result row had printed before it. *Measured (M4, 2026-10-20):* importing torch, asking `torch.backends.mps.is_available()`, `SystemExit`, `torch.mps.empty_cache()`, an MPS tensor, a matmul, a conv2d and a bidirectional LSTM on MPS all exit 0, so plain GPU use and `empty_cache` are not the trigger. The trigger is Kraken's own segmenter loaded (vgsl builds a Core ML model; coremltools warns "Error compiling model") and run on MPS: exit -6 (SIGABRT). M4 2026-10-20: the same load with the forward on the CPU, and the load alone, abort too: the trigger is Kraken's model load (vgsl, coremltools), not MPS, so keeping Kraken off the GPU does not remove it and the way out is the fix. *Built; ran green on the M4 at `bf3d1a721` (2026-10-20: 27 passed, 3 expected failures):* `fichero_server/core/fast_exit.py` `leave(status)`: with torch loaded, every DuckDB connection is checkpointed and closed (an unreplayed WAL is the index hazard), the `atexit` functions run, the logs are flushed, the thumbnail pool's running workers are joined (`os._exit` joins no thread; a file being written finishes), a `SystemExit`'s string is printed to stderr as Python's own exit would, then `os._exit(status)`; with torch not loaded, or a database that will not close, it returns and the ordinary exit follows. `__main__.main()` calls it on a normal return and on `SystemExit`, never on an uncaught error (its traceback prints, status 1) and never when `pytest` is loaded (a test calls `main()` in-process). *Not built:* the same way out in the other processes that load torch: the Kraken line-extraction children (spawned `multiprocessing` workers, whose non-zero exit a parent may read as failure), the subprocess workers (`remote_read` runner, `_pdfium_probe`) and the scripts (`gil_proof.py`, `bench_reading.py`); a fix at the source (stopping vgsl's Core ML build at load), which would need a change in Kraken or a way to load the model without coremltools. *Tests:* `fichero-server/tests/unit/llm/test_torch_exit_5929.py` (M4 only: the plain cases are proof that ordinary MPS work exits clean; `mps-kraken-blla` is a strict expected failure citing #5929; `cpu-kraken-blla` and `kraken-load-only` are strict expected failures too; `mps-kraken-blla-left-by-the-engines-exit` is the fix, red until `fast_exit` exists) and `fichero-server/tests/unit/core/test_fast_exit_5929.py` (a stand-in torch: leaves with the status, never returns, no WAL left, returns when a database will not close).
- `runtime.mlx.idle-unload-and-loading-state` — **[GAP]** (#5370, #5358) a resident MLX model is
  released after the lane's idle time, and while it loads the step says "Loading <model>"; today the
  server child stays up with no idle release and a 30–300 s warm-up is a silent wait *(review)*.
- `runtime.embed.once-per-text-version` — **[PARTIAL]** (#5954; Fable steps-efficiency review) a page is embedded once per
  version of its text, however many doors ask for it (the import, after a read that saves text, the recipe's search step,
  a correction), and the recipe's search step embeds pages in batches of 64 in one job each, one forward pass per batch,
  not one job and one pass per page. A page is "current" when its stored passage vectors are the ones its text and the
  present embedding model would give (the same passages, each unit's id and text, stamped with this model), read from the
  vectors themselves, so no second record can go stale and a page embedded before this is judged on what is stored. *Built,
  unrun until an M4 pass:* `Database.embedding_is_current`, `embed_unless_current` (the correction job, the import's
  embed stage), `embed_many_unless_current` (the batch), `page_text_cache.queue_reembed_batches` and the batch job
  (`make-a-vector` with a `batch:<id>` subject and its pages in the row's detail), the recipe's embed card waiting on the
  batches. *Not built:* a batch shows in Activity under its `batch:` subject, not yet as "64 pages"; the import's resume
  skip still trusts any stored vector (a page whose text changed while the import was interrupted is re-embedded by the
  correction job, not by that resume); the measured saving on the M4 (50 pages read then Start: one embed per page in the
  jobs table, `_embed_texts` once per batch). *Test:*
  `fichero-server/tests/unit/db/test_embed_once_per_text_version_5954.py` (a page embedded after a read is "unchanged" for
  the search step; changed text and another model embed again; a batch of six pages with one current runs one pass; 130
  pages queue as 64, 64 and 2).
- `runtime.cloud-extractors.pages-together` — **[PARTIAL]** (#5955; owner ruling 2026-10-20) a cloud extractor (entities, SVO, tables) sends 5 to 10 pages in one call (within the provider's limits and the project's spend cap), not one call per page. *Built:* concurrent single-page calls with an ordered look-ahead: `workflows/tools/_together.py` `ahead()` keeps up to the step's width in flight (10 for a hosted model, 3 for one served here, `FICHERO_EXTRACT_MAX_IN_FLIGHT` overrides), reads pages lazily and hands answers back in page order; the claims step asks its dates and claims calls together; the entities, diary-split and table steps ask ahead; writes stay sequential; the table step looks for a stop as each call starts. *Not built:* several pages in ONE call (20 pages make 2 to 4 calls; each page still repeats the instruction and schema tokens, and 10 in flight meets provider rate limits a single call would not), so #5955 stays open for it; the width is fixed per step, not taken from the place's width (`ai.where.one-cloud-cap`, #5358) once that lands; the 40-page timing is unrun until an M4 pass. *Tests:* `tests/unit/workflows/test_cloud_extractors_pages_together_5955.py` (40 pages at 200 ms finish in under 2 s at width 10; write order unchanged; a stop sends no new call; `test_twenty_pages_make_two_to_four_calls` is the ruled test, an expected failure citing #5955 until the one-call form is built).
- `runtime.embed.batched-at-utility-when-watched` — **[GAP]** (#5370, #5358) embedding passes an
  explicit batch size, and an embed a person is waiting on (search right after import) runs at
  utility QoS; the Core ML execution provider and an int8 bge-m3 are measured against fp32 CPU
  before either is adopted.
- `runtime.pytorch.device-chosen` — **[GAP]** (#5370) PyTorch work (PyKEEN, a YOLO detector) uses
  MPS where it measures faster on the fixture and the CPU otherwise; nothing hard-codes the device.
- `runtime.mlx.fit-estimate` — **[PARTIAL]** (#5641) before an MLX model loads, Fichero estimates what it
  needs: its weights, plus the KV cache for the step's context length (2 × layers × KV heads × head size × 2
  bytes per token, from the model's own config; a long page needs more), plus a fixed overhead (0.75 GB:
  activations, the vision tower's image tensors, the runtime). It says "fits", "tight" or "won't fit", each with
  one line naming the parts. **Built 2026-10-12 (engine):** `llm/local_inference.fit_estimate(model,
  context_tokens, physical_memory)` is the one rule: the load's check (`assert_memory_available_for_model`) and
  the throttle's need (`mlx_memory_need_bytes`) read it, and the model finder lists it on every MLX candidate
  (`GET /api/recipes/candidates`, each item's `fit`). The default context is 8,192 tokens
  (`DEFAULT_CONTEXT_TOKENS`). "fits": within two thirds of physical memory (`MLX_COMFORT_SHARE`, Apple Metal's
  `recommendedMaxWorkingSetSize` on 8-16 GB Macs, the working set MLX reports and Ollama and llama.cpp take as
  a Mac's GPU memory); "tight": above that, up to the ceiling; a model whose note says reading a page needs a
  bigger Mac is at least tight. **The step's own context (built 2026-10-12):** a call that loads a model judges
  the fit by its own context, its prompt and image (2,048 tokens) plus the answer it allows (`max_tokens`), not
  the default (`step_context_tokens`, `reading_with_context`); the finder, asked for a step, counts that step's
  `max_tokens` where its settings give one, a line's for a line reader (the prompt and image plus 24 tokens a
  line), and the 8,192-token default for a step that says neither. A page read with a model on this Mac is judged
  by its own working lines (`page_lines_context`: the prompt and image plus 24 tokens a line), the call at the
  smaller of that and its own `max_tokens` (`call_context_tokens`). *Not built: the Mac's own Metal reading in place
  of the share.* *Test:*
  `fichero-server/tests/unit/llm/test_mlx_fit_estimate_5641.py`.
- `runtime.mlx.seven-b-reader-needs-24gb` — **[BROKEN]** (#5641; owner ruling via the manager 2026-10-21) the Qwen2.5-VL 7B 4-bit reader is not chosen to read pages on a Mac under 24 GB until it is measured: its catalogue entry has no page floor (the load floor 16 GB equals a 16 GB Mac's whole memory, so `choose_local_model` picked it there, "the larger, the more capable") and the seed card says 7 GB, weights only, so the recipe default took it; on the 16 GB Pro it read at 0.1 tok/s with swap full. Required: the catalogue entry's `page_memory_bytes` and the seed card's `memory_gb` are 24 GB until measured, so below 24 GB it is refused in words ("does not have the memory to run it alongside macOS and Fichero") and the default reader on a 16 GB Mac is Kraken with Apple Vision, until the 3B MLX is measured on the M4. *Test (red until the fix):* `fichero-server/tests/unit/llm/test_seven_b_reader_needs_24gb_5641.py`.
- `runtime.mlx.fit-shown-in-the-app` — **[OK]** (#5641) **Built 2026-10-12 (app), not yet seen:** wherever a
  step's model candidates are listed (Set Up's stage page Compare list, the model finder's cards, and the step's
  own card on its stage page), an MLX candidate says "Fits this Mac", "Tight on this Mac" or "Won't fit this
  Mac" with the engine's reason under it and in its help (`CandidateFit`, drawn by `CandidateFitLabel`; system
  colours, semantic fonts). A model that won't fit is greyed, not hidden: it cannot be ticked to compare and
  the finder offers no Use for This Step for it. The smaller build the engine names (`fit.smaller`) is one press,
  **Use <name> instead**, through the use-candidate route (`RecipeSetupStore.useCard`), when the same list holds
  it. *Test:* `fichero/Tests/Unit/general/Models/CandidateFitTests.swift`.
- `runtime.mlx.refuse-only-what-would-crash` — **[PARTIAL]** (#5641) a model that can run on MLX runs. The
  refusal line is a measured ceiling, the point where macOS starts swapping heavily, measured on an
  8 GB and a 16 GB Mac with the fixture pages; below it the model loads (idle models unloaded first,
  one heavy model at a time when memory is busy, #5622). Above it the step refuses in words, naming the
  estimate and the ceiling. **Built 2026-10-12, provisional:** the ceiling is physical memory less 2 GB for
  macOS and Fichero (`MLX_MAC_RESERVE_BYTES`: 6 GB on an 8 GB Mac, today's 75% there; 14 GB on 16 GB, where 75%
  was 12), and "won't fit" is exactly what the load refuses. *Test:* `fichero-server/tests/unit/llm/test_mlx_fit_estimate_5641.py::test_the_load_refuses_exactly_what_the_estimate_calls_wont_fit`. *Not measured: the swap point on an 8 GB and a
  16 GB Mac, which replaces the 2 GB.*
- `runtime.mlx.offer-a-way-to-fit` — **[PARTIAL]** (#5641) a model that won't fit is offered a way to fit:
  a smaller quantized build of the same model (from the model finder), a quantized KV cache, or a
  shorter context. MLX cannot split a model between GPU and CPU as Ollama does; a smaller build is the
  Mac's equivalent. **Built 2026-10-12:** the largest smaller build of the same model (its name without its
  build: `-4bit`, `-8bit`, `-bf16` …) in the catalogue and the finder's list that fits is named (`fit.smaller`);
  with none, the longest context that would fit, when it is at least 2,048 tokens. *Test:*
  `fichero-server/tests/unit/llm/test_mlx_fit_estimate_5641.py` (`test_a_model_that_wont_fit_is_offered_a_smaller_build_of_the_same_model`,
  `test_with_no_smaller_build_a_shorter_context_is_offered_when_it_would_fit`). *Not built: a quantized KV
  cache as the way.*
- `runtime.mlx.kv-cache-settings` — **[PARTIAL]** (#5641) the bundled MLX server's KV-cache settings
  are chosen per load: the batch is the client's pages at once (`MLX_VLM_MAX_NUM_SEQS` equals
  `local_reads_at_once`, `llm/local_inference.reads_at_once_for`, built 2026-10-10). *Not built:* a
  quantized cache (`kv_bits`) and a cap (`max_kv_size`) when they let a model fit, adopted only after the
  fixture pages show no rise in character error rate; prompt (prefix) caching for a step's fixed
  instruction. *Test:* `fichero-server/tests/unit/llm/test_mlx_ships_inside_the_engine.py::test_the_server_reads_as_many_pages_at_once_as_it_is_sent`.
- `runtime.memory-gates-compose` — **[GAP]** (#4987, #5358) one memory check, fed by the cards'
  resident sizes, replaces the per-runtime guards (Kraken's 2.5 GB free, MLX's estimate); it knows
  what is already resident (Kraken, the embedder, an MLX model) before admitting another.
  The admitting rule is owned by `activity.lane.co-run-only-if-it-fits` and
  `activity.throttle.power-heat-memory`; this line owns the per-runtime resident sizes it reads.

### D. Jobs, downloads and errors

- `runtime.one-download-path` — **[GAP]** (#5359, #4307) every weights and `traineddata` download,
  for every runtime, goes through one engine route family and is a `download-model` job; the five
  progress systems (MLX jobs, the install coordinator, `/local-models` background tasks, Whisper's
  `_DOWNLOAD_STATE`, fastembed's silent first-use download) are retired into it.
  The job is the Mac's own, not a project's, and shows in the window's Mac group
  (`activity.global-work-is-the-macs`, which owns how it is shown); this line owns the one path and
  the check of what was downloaded.
- `runtime.spacy.pipelines-download-as-data` — **[OK]** (#5367; built: `download_spacy_pipeline`, the `download-model` job and `model.download` in `llm/local_models.py` and `api/routes/ai/local_models.py`; tested in `fichero-server/tests/unit/llm/test_spacy_pipelines_as_files_to_spec.py`) a spaCy pipeline that is not bundled
  downloads as files: its release archive is fetched, only the pipeline's data folder (its
  `config.cfg`, `meta.json` and weights) is written into the model store (`<models>/spacy/<name>-<version>`),
  nothing outside that folder is written, and an archive whose data folder holds code (a `.py`,
  compiled module or link) or a path that leaves the folder, or one that is not the pipeline asked for (its meta names
  another), is refused, writing nothing. It is loaded
  from that folder by path; no package is installed and none of its code runs. Installed state, size
  and delete then work as for Whisper and the search models (the bundled pipelines are listed as
  bundled and cannot be deleted). The download is a `download-model` job on the network lane.
- `runtime.spacy.store-first` — **[OK]** (#5367; built: `spacy_ner._open`, `spacy_svo`; tested in `fichero-server/tests/unit/llm/test_spacy_pipelines_as_files_to_spec.py`) the names step and the statement grammar
  (`knowledge/spacy_ner.py`, `knowledge/spacy_svo.py`) look for a pipeline in the model store first,
  then among the bundled ones.
- `runtime.spacy.pin-is-honoured` — **[OK]** (#5367, #4948; built: `spacy_ner._load_named` / `PipelineMissing`, the provider passes its pin; tested in `fichero-server/tests/unit/llm/test_spacy_pipelines_as_files_to_spec.py`) a step pinned to a spaCy pipeline runs that
  pipeline and no other; if it is not on this Mac the step says so and does not run another in its
  place (until 2026-10-04 the names step ignored its pin and took the language's preferred pipeline).
- `runtime.load-is-visible` — **[GAP]** (#5359, #5370) loading a heavy model shows on the step's
  row with elapsed time; a step never sits silent while a model loads.
  A load is one of the Mac's own jobs (`activity.global-work-is-the-macs`).
- `runtime.call-records-the-card` — **[GAP]** (#4948) every call records on its page job, and on
  what it made, the card id that answered (with the macOS build for Apple, the dated id for a cloud
  alias).
- `runtime.errors-are-typed` — **[PARTIAL]** (#5353, #5367) a runtime failure reaches the job as its
  typed kind (memory, unavailable in this build, needs a key, egress refused, quota, model missing),
  from the exception the runtime raised; the runner stops matching message text. Built: the runner's
  `_classify_provider_error(text, exc)` decides by the exception's type first (`_typed_failure`: quota, egress refused,
  memory, model missing, unavailable in this build), message words only for an exception with no type; its test
  `fichero-server/tests/unit/workflows/test_errors_are_typed_5353.py` is written, green NOT yet seen (no pytest during
  gate3). Still a gap: "needs a key" has no exception type of its own yet, and the other call sites pass text only.

### E. Honest status

Moved to the one Settings home, `ai/ai-settings.md` ("Runtime status"), on 2026-10-04: `runtime.status-from-the-endpoint`, `runtime.status-covers-every-runtime`, `runtime.unavailable-says-so`, `runtime.defaults-name-working-runtimes`.


### F. Keys and egress

Moved on 2026-10-04: the two key behaviours to `ai/ai-settings.md` ("Keys a runtime needs"); the four egress behaviours to the one egress home beside `source.egress.one-gate` in `source/models-chains-and-projects.md`.


## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | card id round-trips to and from the recipe YAML form; alias cloud cards are `pinnable: false`; a corrupt or partial download is not installed; the build-state constant decides "available"; `/local-runtimes` reports every runtime; typed error kinds reach the job; every model-factory caller is gated | `fichero-server/tests/unit/llm/` (new `test_card_id.py`, `test_runtime_build_state.py`), `fichero-server/tests/unit/api/` |
| Backend (pytest), residency | y | Kraken loads its nets once per worker across 20 pages (`test_kraken_model_loaded_once_per_worker`, shared with the activity spec); one fm-bridge process serves 10 calls; one spaCy pipeline per language; Whisper loads once for 5 files | `fichero-server/tests/unit/llm/` |
| Pure rule (Swift) | y | a row's status text and dot from each runtime state; no hand-mirrored runtime list | `fichero/Tests/Unit/general/Views/Settings/` |
| MCP / CLI | y | `fichero_local_runtimes` returns the same rows as the app | `fichero-mcp/tests/test_mcp_server.py` (exists, route only) |
| Named-machine (sandboxed DMG) | y | each runtime's row matches what actually runs in the notarised build; "transcribe speech" either runs or is honestly absent | manual checklist with the release gate |
| Load (#4634) | y | 200 handwritten pages: time per page before and after load-once; resident memory never above the card sum | `fichero-server/tests/perf/` |
| Click-around (Mac) | n | covered by `ai/ai-settings.md` | — |
| iPhone / iPad | n | runtimes run on the Mac's engine | — |

## Open questions (with recommendations)

1. **Answered** (design lead 2026-10-04, applying the spec's lean): Bundle mlx, mlx-lm, mlx-vlm and mlx-whisper at build time like Kraken and run them in-process behind one seam, measuring the size first. **MLX in the sandboxed build: bundle it, or Debug only?** *Recommend:* bundle mlx, mlx-lm,
   mlx-vlm and mlx-whisper at build time with the Kraken bundle pattern, and run them in-process
   behind one seam rather than as a child server (the sandboxed engine cannot spawn its own Python
   children, #4973). That also removes the port and the 30–300 s server warm-up. Measure the
   bundle's size first (roughly 150–250 MB, not yet measured).
   *Note 2026-10-01:* Fichero already runs MLX through its oMLX provider, but oMLX installs mlx-lm,
   mlx-vlm and mlx-whisper with pip into a private environment the first time it is used
   (`llm/mlx_runtime.py:222-247,296`). That works in Debug and is refused by the sandboxed DMG, so
   the answer is to bundle those packages at build time and keep the oMLX provider as it is.
2. **Answered** (this spec, ruled 2026-10-01): Speech is a choice of options (Apple, Whisper, MMS), cheapest covering the language starts. **Speech: which runtime?** *Ruled 2026-10-01:* speech is a choice of options, like any job,
   chosen by the same rules and A/B: Apple's on-device speech recognition (bundled so it works in
   the sandbox; macOS's newer speech analyser (26 and later) where available), Whisper (99 languages), and a
   more multilingual model for languages Whisper lacks (Meta's MMS, over 1,100 languages). The
   cheapest local option that covers the language starts; the others are one A/B away.
3. **Answered** (this spec, ruled 2026-10-01): Allowed, marked 'can change', with the dated version recorded on each reading. **Cloud aliases in recipes.** *Ruled 2026-10-01:* allowed, marked "can change" in the recipe
   editor, with the dated version that actually answered recorded on each reading.
4. **Answered** (design lead 2026-10-04, applying the spec's lean): Measure on the fixture pages and keep 'always' if the sparse rule loses any line. **Apple Vision's strips: conditional or always?** They became a base pass on 2026-08-23 because
   they found lines the first pass missed. *Recommend:* measure on the fixture pages whether a
   sparse-first-pass rule loses any line; keep "always" if it does.
5. **Answered** (design lead 2026-10-04, applying the spec's lean): A model whose measured resident size is over 1 GB, the embedder included, with one heavy model at a time below 16 GB. **What counts as heavy on an 8 GB Mac?** *Recommend:* anything whose measured resident size is
   above 1 GB; the embedder counts. One heavy model at a time below 16 GB, and onboarding offers an
   8 GB Mac only cards that fit beside the embedder.
6. **Answered** (design lead 2026-10-04, applying the spec's lean): As 'system', outside the co-run sum, while the memory-pressure wait still applies. **Where does fm-bridge's memory count?** FoundationModels and Vision memory belongs to the system,
   not the engine. *Recommend:* count it as "system" in the job's processor row and leave it out of
   the co-run sum, but let the memory-pressure wait apply.
7. **Answered** (design lead 2026-10-04, applying the spec's lean): Fold them into a card id plus the recipe step's settings, with the privacy rule moving to the egress gate. **Runtime configurations (`llm/model_profiles.py`): keep or fold?** *Recommend:* fold into a card
   id plus the recipe step's settings, with the privacy rule moving to the egress gate, as the
   models-chains spec already asks (it calls the thing a "runtime configuration").
8. **Answered** (design lead 2026-10-04, applying the spec's lean): Card id, then the status endpoint, then one download path writing jobs, then load-once Kraken and the resident fm-bridge, then the egress gate. **Build order.** *Recommend:* (a) the card id and `source.model.runs-here`, data only; (b) the
   build-state constant and the status endpoint wired to the rows (removes the sandbox lie);
   (c) the one download path writing jobs; (d) load-once for Kraken and the resident fm-bridge
   (the two largest speed wins); (e) the egress gate at every call site. Recipes come after (a)–(c).

## Requests to other specs (for the manager to route; nothing edited here)

- `source/models-chains-and-projects.md`: adopt `source.model.card-id`, `.cloud-pin-is-honest`,
  `.weights-verified`, `.embedding-space-has-revision`, `.runs-here`, `.licence-filled` and
  `.jobs-replace-capabilities` into its "Model cards" list (or point to them here); the activity
  spec already cites `source.model.runs-here`, which no spec defined until this one. Its recipe
  YAML pin forms are the split form of the card id.
- `ui/activity-and-automatic-work.md`: *done 2026-10-04, absorbed into `activity.global-work-is-the-macs`.* Add `activity.first-use-download-is-a-job` (a model fetched
  on first use is a child `download-model` job and the step waits with "Waiting for model
  download") and `activity.recipe-adoption-prefetches` (adopting a recipe enqueues downloads for
  its missing pinned cards); its lane table should list Whisper, Tesseract, YOLO and the resident
  fm-bridge (counted as "system").
- `ai/ai-settings.md`: `settings.mlx-runtime-honest-status` widens to `runtime.status-from-the-endpoint`;
  add a Tesseract row, an Embeddings row and the Apple rows; `settings.one-catalog-unification`'s
  download half is `runtime.one-download-path`.
- `ai/ai-settings.md`: `keys.one-store-of-truth` is [OK] for Settings but has a sibling path
  (Add Provider, #5369); `keys.status-sees-supplied-keys` and `keys.add-provider-uses-the-one-store`
  belong in its list.
- `compute/jobs-and-fine-tuning.md` (Kraken "in its own environment by subprocess") and
  `compute/linux-server-image.md` ("on the Mac … still installed on request"): both predate the
  bundled, in-process Kraken (42a95db93).
- `harness/engine-startup-lifecycle.md`: `engine.bundle-trim-litellm` is moot; the litellm package
  is gone and prices come from the vendored JSON.

## Future (ideas, not scheduled)
- (#2585) How the engine talks to optional plugin packs (MLX/OpenCV/KG): three mechanisms, try to drop OpenCV via Core Image/Vision; design note for a future plugin split.
- (#1146) Embedding mlx-swift/MLXVLM for in-app local Qwen3-VL/Nanonets OCR; no package integration exists; model-integration wish, local runtimes Future section.

## Triaged from the backlog (2026-10-04)
- `runtime.apple-intelligence-prewarm` — **[GAP]** (#853) the Apple Intelligence runtime is prewarmed at engine start so the first workflow run is not cold (contentTagging already shipped at fichero-server/bin/fm-bridge/FmBridge.swift:403; prewarm absent).
- `runtime.each-proven-on-a-real-page` **[GAP]** (#5267): MLX (a small vision model on one page, Whisper on a short clip), Kraken, YOLO and spaCy each have a smoke run that does the real work on a real page or paragraph in the weekly schedule on the maintainer's Mac, none of them costs anything at launch, and MLX's failure on the maintainer's setup is named or fixed.
- `runtime.mlx.serves-the-model-a-step-asks-for` **[GAP]** (#5388): when a step names a managed local model the local server is not serving, the server loads that model (when it fits) and the work is grouped by model, following load-once, instead of refusing. (Refusal by name, a5286dc80; the CLI wait, 78d48ec4b; workflow run --model, 74e62f9a1.)
