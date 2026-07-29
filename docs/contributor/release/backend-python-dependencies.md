(AI generated. Not reviewed.)

# Backend Python Dependencies

Last updated: 2026-06-27

This file records the current dependency policy for the embedded Briefcase
engine and the release-app bundle size audit.

## Current State

The embedded Mac engine is built from `fichero-server/pyproject.toml`.
Dependencies are mostly floating so a clean Briefcase create resolves the newest
mutually compatible package set. The only ordinary version floor in the core
manifest is `Pillow>=12.2.0`.

The previous `websockets<14` / LangGraph cap has been removed. The server now
launches Uvicorn with the modern sans-IO websocket protocol:

- Briefcase embedded server: `ws="websockets-sansio"` in `fichero-server/src/fichero_server/__main__.py`
- CLI detached engine: `--ws websockets-sansio` in `fichero-cli/src/fichero_cli/engine_manager.py`

A clean Briefcase create on 2026-06-27 resolved the newer websocket/LangGraph
line successfully:

- `websockets==15.0.1`
- `uvicorn==0.49.0`
- `langchain==1.3.11`
- `langgraph==1.2.6`
- `langgraph-sdk==0.4.2`
- `Pillow==12.2.0`

## Optional Heavy Features

These packages are intentionally not in the default Briefcase/core dependency
set for the shareable Mac tester app:

- `pykeen` pulls `torch` into the bundle.
- `rdflib` powers SPARQL/RDF export/query.
- `spacy` powers deterministic first-pass NER; the app falls through to
  LLM-only NER when it is absent.
- `opencv-python-headless` provides `cv2`; image background removal falls back
  to the threshold/Pillow path when it is absent.
- `splink` is not currently shipped; it is future record-linkage work.

Install optional feature stacks explicitly when working on those areas:

```bash
pip install -e ".[kg,image]"
```

## Clean Bundle Result

After deleting the generated Briefcase macOS build and recreating it from the
current manifest, the embedded Release app no longer contains:

- `torch`
- `pykeen`
- `rdflib`
- `spacy`
- `splink`
- `cv2` / OpenCV

Observed sizes after the clean rebuild:

- `fichero/build/xcode/Products/Release/Fichero.app`: `1.2G`
- Embedded `Fichero Server.app`: `1.0G`
- Embedded `app_packages`: `902M`

Largest remaining app packages:

| Package/path | Size | Why it remains |
|---|---:|---|
| `lance` | `147M` | Lance/LanceDB vector-table storage |
| `pyarrow` | `119M` | Arrow data layer used by LanceDB |
| `lancedb` | `108M` | Vector search database |
| `onnxruntime` | `68M` | Native runtime used by `fastembed` |
| `kreuzberg` | `62M` | Document text extraction |
| `litellm` | `60M` | Model catalog + cost metadata (`get_model_info`, `cost_per_token`). Not a router. |
| `pymupdf` | `51M` | PDF rendering/extraction |
| `_duckdb...so` | `43M` | DuckDB database engine |
| `botocore` | `24M` | AWS provider dependency via LangChain |
| `numpy` | `22M` | Numeric dependency used by vector/image stacks |
| `PIL` | `13M` | Pillow image support |

ONNX Runtime is not the same package as FastEmbed, but FastEmbed uses it to run
embedding models without PyTorch. ONNX is the model format/runtime interface;
`onnxruntime` is the native execution engine in the bundle.

Further large reductions require product choices, not obvious dead-dependency
cleanup. The main tradeoffs are:

- Removing local vector search/local embeddings would cut LanceDB/PyArrow/Lance
  and FastEmbed/ONNX Runtime, but would remove core local search capability.
- Removing broad LLM provider support would cut some LangChain/LiteLLM/provider
  packages, but would narrow model/provider support.
- Removing document extraction/rendering packages would cut Kreuzberg/PyMuPDF,
  but would reduce import and preview functionality.

## Verification

Commands run after the 2026-06-27 changes:

```bash
python -c 'import tomllib; tomllib.load(open("fichero-server/pyproject.toml", "rb"))'
PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/ruff check \
  fichero-server/src/fichero_server/__main__.py \
  fichero-cli/src/fichero_cli/engine_manager.py \
  fichero-server/src/fichero_server/knowledge/spacy_ner.py \
  fichero-server/src/fichero_server/api/routes/kg_sparql.py \
  fichero-server/src/fichero_server/api/routes/kg_pykeen.py \
  fichero-server/src/fichero_server/api/routes/kg_predictions.py
PYTHONPATH=fichero-server/src .venv/bin/pytest \
  fichero-server/tests/unit/test_engine_entrypoint.py \
  fichero-server/tests/unit/test_remote_access_tls.py \
  fichero-server/tests/unit/kg/test_spacy_ner.py \
  fichero-server/tests/unit/workflows/test_ner_providers.py \
  fichero-server/tests/unit/workflows/test_remove_background_images.py -q
```

Results:

- TOML parse passed.
- Ruff passed.
- Focused tests passed: `29 passed, 1 warning`.
- Earlier optional-dependency focused suite passed: `51 passed, 5 warnings`.
- Clean Briefcase create/build produced `build/server/macos/app/Fichero Server.app`.
- `bash scripts/build-release.sh --skip-backend` succeeded and embedded the clean engine.
- `bash scripts/smoke-release-embedded-backend.sh --lan` passed:
  - `https://127.0.0.1:8765/api/health`
  - `https://macbook-pro-m1.local:8765/api/health`

## Historical Note

The original 2026-06-14 dependency pass used an isolated `.venv-deps`
environment and reported:

- Full unit suite: `5031 passed, 22 skipped, 21 xfailed, 0 failed`
- `pip check`: no broken requirements

That pass documented a temporary `websockets<14` cap. That cap is no longer the
current policy because the server launch path now opts into
`websockets-sansio`.

## Open Follow-Up

LangGraph strict msgpack remains separate work. Track the fix as primitive
checkpoint storage / allowed type registration / `LANGGRAPH_STRICT_MSGPACK=true`
coverage under the existing #2235 work.
