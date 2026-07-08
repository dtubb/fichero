(AI generated. Not reviewed.)

# Embedded Local Models Plan

Issue: #2615

This doc is grounded in the backend as shipped on `origin/main` on 2026-07-05.
It is a plan for the remaining backend and integration work around embedded
local models; it does not assume the whole feature is unbuilt.

## Current shipped state

### LLM call path

- `src/fichero/llm.py` is the real model call path.
- LangChain is the primary routing path for networked and OpenAI-compatible
  providers.
- LiteLLM is metadata-only here: model catalog, pricing, and capability lookup.
  It is not the chat routing layer.

### Apple Foundation Models backend

- Provider type `apple` is registered in `src/fichero/providers.py` as a local,
  built-in provider with no API key.
- The actual Apple call path is not LangChain today. `llm.py` routes
  `provider=="apple"` to the Swift `fm-bridge` subprocess because the public
  Foundation Models API is Swift-native.
- `llm.py` already probes `fm-bridge` availability, translates structured bridge
  errors into typed Python errors, and fails loudly when the bridge is missing.
- `api/main.py` already seeds the built-in Apple provider and Apple default
  models into the app DB.

### MLX backend

- Provider type `omlx` is already registered as a local provider.
- `llm.py` already routes `provider=="omlx"` through `langchain_openai.ChatOpenAI`
  against a localhost OpenAI-compatible server.
- `api/routes/local_inference.py`, `local_inference.py`, `mlx_runtime.py`, and
  `mlx_model_store.py` already provide:
  - app-managed local-provider profiles
  - isolated MLX runtime directories
  - managed model catalog / install state
  - typed runtime / hardware / availability errors
  - lifecycle management for the local sidecar
- The lean-deps contract is already executable in
  `tests/unit/test_embedded_models_lean_deps.py`.

### Packaging and build hooks

- `pyproject.toml` already declares `resources/bin/*` as package data.
- `fichero-engine/scripts/build_backend_bundle.sh` compiles `bin/fm-bridge/FmBridge.swift` into
  `src/fichero/resources/bin/fm-bridge` before Briefcase packaging.
- `fichero-engine/scripts/bundle_python_backend.sh` stages the same bridge into the packaged
  site-packages path for the Python bundle flow.

## Target architecture

### Apple Foundation Models

- Keep the provider surfaced as a local/private option in Settings.
- Keep the engine-side invocation as a subprocess bridge unless Daniel decides
  on a different bridge boundary. The current Swift-native bridge is consistent
  with the no-heavy-deps rule.
- Continue to fail closed when the host cannot run the bridge or the OS/hardware
  does not support Foundation Models.

### MLX

- Keep MLX on the existing OpenAI-compatible local-server pattern.
- Keep heavy ML packages out of the engine bundle. MLX runtime installation and
  model weights live outside the shipped engine environment.
- Continue to start the sidecar only through the managed local-inference path,
  with typed unavailability errors instead of cloud fallback.

## Open questions for Daniel

### Apple Foundation Models routing boundary

Current code uses a Swift subprocess bridge, not LangChain. If Daniel wants both
local backends to present through one uniform LangChain adapter layer, that is a
future refactor, not a safe first slice.

### Settings surface ownership

The backend already exposes provider metadata and local-inference routes. The
remaining provider-picker and downloads UX is a frontend concern unless a new
backend contract gap is found.

## Remaining slices

### Already shipped on main

- Local provider registration for Apple + MLX
- Lean-deps guard
- Managed MLX runtime + lifecycle
- Model catalog / downloads / typed runtime errors
- Apple availability probe and bundled-bridge build hooks

### Safe backend follow-ups

1. Align user-facing provider metadata with Daniel's recorded naming decisions.
2. Add any missing regression tests around provider metadata / discovery without
   changing routing behavior.

### Deferred / larger work

1. Any Apple bridge refactor that tries to force Foundation Models through a
   LangChain-native adapter.
2. Frontend Settings UX for selection, downloads, and platform gating.

## First safe slice

The first real backend delta after grounding the current code is small:
`ProviderType.omlx` still exposes the name `oMLX` in the provider catalog, while
Daniel's recorded decision says the user-facing picker label should be
`MLX (Local)`. That is safe to fix without touching the working runtime path.
