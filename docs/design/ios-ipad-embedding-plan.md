# iOS / iPad Engine Embedding Feasibility Plan

Status: research only for #105 / #2096. This is a grounded survey of the current backend and packaging surface, not an implementation commitment.

Date: 2026-07-06

## 1. What Exists Today

The shipped backend is a Briefcase-packaged macOS app, not an iOS target.

- `fichero-engine/pyproject.toml` defines one Briefcase app, `tool.briefcase.app.engine`, with a `[tool.briefcase.app.engine.macOS]` section and no iOS briefcase target.
- The current bundle assumes a nested macOS backend app (`docs/BUNDLING_BACKEND.md`).
- The frontend currently pins iOS/iPadOS as a remote-client surface, not an embedded-engine surface:
  - `fichero/fichero/Services/EngineConfig.swift`: “iOS/iPadOS never runs a local engine.”
  - `fichero-engine/tests/unit/test_check_ios_remote_client_target.py` guards that posture.

So the starting point is not “port the existing embedded backend to iPad.” The starting point is “decide whether an iPad should embed any subset of this engine at all.”

## 2. Real Backend Dependency Surface

### 2.1 Core bundle deps declared today

`fichero-engine/pyproject.toml` ships these in the core Briefcase engine:

- Core/server: `fastapi`, `uvicorn[standard]`, `websockets`, `python-multipart`, `python-dotenv`, `aiofiles`, `aiohttp`, `httpx`, `defusedxml`, `cryptography`, `zeroconf`
- Data: `pydantic`, `pydantic-settings`, `duckdb`, `lancedb`, `pylance`
- AI/runtime: `langchain`, `langchain-core`, `langchain-openai`, `langchain-anthropic`, `langchain-google-genai`, `langchain-aws`, `langchain-cohere`, `langchain-mistralai`, `langchain-openrouter`, `langchain-community`, `langchain-mcp-adapters`, `mcp`, `langgraph`, `langchain-ollama`, `litellm`, `apscheduler`, `watchdog`, `kreuzberg`, `fastembed`
- Document/image: `PyMuPDF`, `Pillow`

The same file explicitly keeps these out of the default bundle as optional heavy extras:

- `pykeen`
- `rdflib`
- `spacy`
- `opencv-python-headless`

### 2.2 Additional imports present in source

The source tree imports more than the core manifest, mostly behind optional or platform-specific paths. The significant ones I verified in `fichero-engine/src/` are:

- macOS-only Apple bridges: `Quartz`, `Vision`, `Foundation`, `Speech`, `rubicon.objc`
- optional ML / extraction: `cv2`, `numpy`, `rawpy`, `rembg`, `pykeen`, `torch`, `transformers`, `spacy`, `rdflib`, `whisper`, `docling`, `libxmp`, `cld3`
- PDF/doc loaders: `fitz`/PyMuPDF, `PyPDF2`, `pypdf`
- workflow/runtime: `langchain_core`, `langchain_openai`, `langgraph`, `mcp`, `fastembed`, `kreuzberg`

The important current split is:

- the core Mac bundle already excludes some of the worst bundle bloat (`pykeen`, `spacy`, `opencv-python-headless`);
- the source still contains optional call paths for them;
- several paths are explicitly macOS-bound today (`bookmarks.py`, Apple Vision OCR in `workflows/tools/vision_base.py`, PyObjC frameworks in `pyproject.toml`).

## 3. Feasibility Matrix

Legend:

- `GREEN`: plausible for an iOS embed without architectural replacement
- `YELLOW`: technically possible only with real pruning, stubbing, or a different delivery path
- `RED`: current implementation is macOS-only or otherwise the wrong fit for an iOS-embedded Python engine

Notes:

- “wheel exists” below is based on PyPI metadata checked on 2026-07-06.
- Absence of an `ios_*` wheel is not by itself a hard blocker for pure-Python code, but it is a blocker for native-extension packages unless Briefcase/Xcode builds them for iOS.

| Dependency / area | Current role in Fichero | Packaging facts | iOS embed | Why |
|---|---|---|---|---|
| `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `httpx`, `python-dotenv`, `defusedxml` | core API/runtime | pure-Python wheels/sdists | GREEN | No obvious native blocker; still only useful if we really run an in-process ASGI engine on device. |
| `aiohttp` | async HTTP server/client support | PyPI publishes iOS wheels | GREEN | Best-supported native-ish core dep in the current set. |
| `cryptography` | TLS, token/security helpers | native wheels for macOS/Linux; no iOS wheel seen | YELLOW | Mature package, but still native. Likely workable only if the embed toolchain can build/link it for iOS. |
| `zeroconf` | Bonjour discovery | native wheels for macOS/Linux; no iOS wheel seen | YELLOW | Discovery is not core to “local single-device library”; could be gated out on iPad if needed. |
| `duckdb` | library DB | macOS arm64 wheels, no iOS wheel seen | YELLOW | Critical for current engine shape; likely one of the hardest mobile-port questions. |
| `lancedb` + `pylance` + `pyarrow` | vector store/search | native macOS arm64 wheels, no iOS wheel seen | RED | Heavy native data stack; largest remaining bundle cost on Mac per `docs/release/backend-python-dependencies.md`. |
| `fastembed` + `onnxruntime` | local embeddings | `fastembed` is pure Python, but depends on native `onnxruntime`; no iOS wheel seen for `onnxruntime` | RED | Current local embeddings path is not a good fit for iOS as-is. |
| `PyMuPDF` / `fitz` | PDF render/text extract | native macOS arm64 wheels, no iOS wheel seen | YELLOW | Important for import/preview, but native and large. |
| `Pillow` / `PIL` | image IO/manipulation | PyPI publishes iOS wheels | GREEN | One of the few current native deps with explicit iOS wheel coverage. |
| `kreuzberg` | document text extraction | shipped in core bundle; depends on broader native/doc stack | YELLOW | Likely usable only if its own dependency chain survives iOS packaging; needs direct spike, not assumption. |
| `langchain*`, `langgraph`, `litellm`, `mcp` | LLM/workflow orchestration | pure-Python wheels/sdists | GREEN | Architecturally portable; product value depends on what local providers exist on iPad. |
| `mlx_runtime.py` + `mlx_model_store.py` | managed local MLX runtime | current design provisions a venv and installs `mlx-lm` dynamically | RED | Current implementation is explicitly Python-venv + subprocess-shaped, not iOS-embed-shaped. |
| `mlx` / `mlx-lm` | local model runtime | `mlx` has macOS arm64 wheels, no iOS wheel seen; `mlx-lm` is pure Python but assumes `mlx` runtime | RED | Current path is Mac-focused. |
| Apple Foundation Models provider | on-device Apple LLM path | current engine uses `fm-bridge` subprocess and docs call that the canonical Apple path | RED | The present backend path is a macOS subprocess bridge, not an iOS embed surface. |
| `pyobjc-framework-Vision`, `pyobjc-framework-Quartz`, `pyobjc-framework-Cocoa` | Apple Vision OCR | macOS-only wrappers; `pyproject.toml` keeps them under `[tool.briefcase.app.engine.macOS]` | RED | Explicitly macOS-only. |
| `bookmarks.py` / `rubicon.objc` security-scoped bookmarks | LINK-mode external-file access | current implementation uses macOS security-scoped bookmarks via Rubicon ObjC | RED | Current implementation is macOS-only. iOS would need a different document-provider/files integration. |
| `opencv-python-headless` / `cv2` | optional image editing path | optional today; macOS arm64 wheels, no iOS wheel seen | RED | Already excluded from Mac core bundle; should stay out of any iPad embed. |
| `pykeen` + `torch` | optional KG link prediction | optional today; `pykeen` pulls `torch` per dependency doc | RED | Not appropriate for iPad embed. |
| `spacy` | optional deterministic NER | optional today; large native/runtime stack | RED | Keep off-device or remote-only. |
| `rdflib` | optional RDF/SPARQL | pure Python | YELLOW | Portable, but not part of an MVP iPad embed. |
| `numpy` | transitive for vector/image stacks | no iOS wheel seen in PyPI metadata | YELLOW | Portable in principle only if build toolchain handles it; probably pulled in only by features we should cut from iPad v1. |

## 4. What Already Looks Removable or Gateable

These are the easiest wins if the goal is “small embedded iPad engine,” because the repo already treats them as optional, Mac-only, or non-core:

### 4.1 Already optional in the core bundle

- `pykeen`
- `rdflib`
- `spacy`
- `opencv-python-headless`

Those are already out of the default Mac Briefcase bundle. They should stay out of any iOS embed unless Daniel explicitly wants them later.

### 4.2 Already macOS-only by implementation

- security-scoped bookmark LINK mode in `bookmarks.py`
- Apple Vision OCR via PyObjC in `workflows/tools/vision_base.py`
- the current Apple Foundation Models path via `fm-bridge`
- the current MLX runtime provisioning path in `mlx_runtime.py`

These are not “minor packaging work.” They are separate platform seams that need either:

- a Swift/iOS-native replacement surface, or
- an iPad rule that the feature is unavailable locally and must use a remote Mac engine.

### 4.3 Strong candidates to cut from iPad v1

If the goal is “local iPad library with basic browsing/search/annotation/editing,” the most likely cuts are:

- LanceDB vector search and local embeddings (`lancedb`, `pylance`, `fastembed`, `onnxruntime`)
- optional KG training/inference (`pykeen`, `torch`)
- optional deterministic NER (`spacy`)
- OpenCV/rembg-heavy image transforms
- MLX runtime provisioning as a Python-managed sidecar

That leaves a much smaller possible core:

- FastAPI/Pydantic/runtime glue
- DuckDB, if DuckDB itself proves viable on iOS
- document/image basics (`PyMuPDF`, `Pillow`) if they package cleanly
- auth / ACL / sync / change-stream logic

## 5. Programmatic Gating Strategy

The repo already has some of the right habits for an eventual iOS embed:

- optional imports with clean fallback (`spacy_ner.py`, `kg_pykeen.py`, `remove_background_images.py`)
- explicit platform fences in frontend and tests (`EngineConfig.swift`, `test_check_ios_remote_client_target.py`)
- local-model logic already separated from the main engine env (`mlx_runtime.py`)

For an iOS embed, the backend needs stronger explicit gates:

1. Central platform probe
   - one backend helper that answers `is_ios_embed`, `supports_external_bookmarks`, `supports_apple_vision_pyobjc`, `supports_python_mlx_runtime`, `supports_vector_store`
2. Import guards
   - every macOS-only or optional-heavy path imports lazily and raises a typed “unavailable on this platform” error
3. Capability-advertising API
   - the app should not discover unsupported local features by tripping runtime import errors
4. Product-profile gating
   - “iPad embedded local library” and “remote Mac library” should be explicit modes, not accidental consequences of host configuration

This ties directly to the follow-up platform-shim work the user referenced (`#2097/#2098`).

## 6. Multi-Library Note

The engine already thinks in per-library terms:

- `db_manager.py` manages per-library database instances.
- authz is per-library (`fichero-engine/src/fichero/authz.py`).
- change/activity streams are per-library.
- the Swift app already carries per-library/remote library concepts (`LibraryManager`, `LibraryReference`, `LibraryLocationDescriptor`).

That means the desired product model is already compatible with the backend:

- every device can own one or more local libraries of its own;
- a device can also connect to other libraries hosted elsewhere;
- per-library ACL/change-stream behavior does not need a new concept for iPad.

What changes for an on-device iPad library is not the multi-library model; it is the local engine substrate:

- where the local DB lives
- which features are available locally
- how local file/document-provider access replaces macOS bookmarks
- how local AI providers are surfaced, if at all

## 7. Recommended Phasing

### Phase 0: decision spike, no product promise

- Decide whether the target is:
  - `A.` full Python engine embed on iPad, or
  - `B.` a smaller local-only subset, or
  - `C.` no Python embed on iPad, only a Swift-native local store plus remote-engine access

Without that choice, the dependency problem is underspecified.

### Phase 1: hard capability inventory

- Add a backend capability matrix for platform-gated features.
- Mark all macOS-only paths explicitly instead of letting imports imply it.
- Keep the shipped iOS remote-only posture until this matrix is real.

### Phase 2: smallest plausible local embed spike

Try the thinnest useful backend subset first:

- app DB + per-library DB
- auth/session/ACL
- document CRUD
- change stream
- no local AI
- no bookmark LINK mode
- no vector search

If even that subset fails on DuckDB or packaging shape, a full Python embed is probably the wrong strategy.

### Phase 3: add local content features selectively

If Phase 2 works:

- evaluate `PyMuPDF` for local PDF/text support
- evaluate `Pillow` image pipeline
- decide whether local search is plain DuckDB/text only first, with vectors deferred

### Phase 4: local AI decision

Only after the embed substrate is stable:

- decide Apple Foundation Models bridge shape for iOS
- decide whether MLX belongs on iPad at all
- keep “no silent cloud fallback” as a hard rule

## 8. Open Questions For Daniel

These are the decisions this survey cannot make headlessly:

1. Is iPad local support meant to be:
   - a real embedded Python engine,
   - a reduced local subset,
   - or a Swift-native local store with remote-engine augmentation?
2. Is DuckDB non-negotiable on iPad, or is a different local persistence story acceptable if DuckDB packaging is the blocker?
3. Is vector search required on-device for iPad v1, or can LanceDB/FastEmbed/ONNX be cut entirely for the first mobile local pass?
4. Should LINK mode exist on iPad at all, or is iPad local import copy-only until there is a native replacement for macOS bookmarks?
5. For local AI on iPad, should the product prefer:
   - Apple Foundation Models only,
   - no local AI at first,
   - or a later dedicated bridge path?
6. Is the correct long-term shape “shared Python engine across macOS and iPad,” or “macOS Python engine plus iOS-native implementation for the local subset”?

## 9. Bottom Line

There is no evidence that the current macOS Briefcase backend can simply be “turned on” for iPad.

The repo is already telling us three things:

- the current mobile product is remote-client-first;
- the current embedded backend is macOS-shaped;
- the heavy data/AI stack that makes the Mac engine valuable (`duckdb`, `lancedb`, `fastembed`, `onnxruntime`, Apple bridges, bookmarks, MLX runtime) is exactly the part least likely to carry over cleanly.

So the safe next move is not to start porting. It is to choose the target substrate:

- minimal local iPad library engine,
- or no Python embed on iPad at all.

Once Daniel picks that, the first real engineering slice should be a capability-gated spike around the smallest useful local subset, not the full Mac backend.
