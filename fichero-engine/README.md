# fichero-engine — Python / FastAPI backend

The engine is where all the logic lives. The SwiftUI app, the `fichero` CLI, and
the MCP server are thin clients over its HTTP surface. It ingests documents,
extracts text and meaning, runs AI workflows, and owns the knowledge graph,
backed by DuckDB (structured metadata) and LanceDB (vector embeddings).

See the [top-level README](../README.md) for the whole-system picture and
[`docs/developer/architecture-overview.md`](../docs/developer/architecture-overview.md)
for the deep dive.

## What lives here

| Path | What |
|---|---|
| `src/fichero/` | The package: API, workflows, KG, ingest, storage, providers, CLI |
| `src/fichero/api/` | FastAPI app (`api/main.py` → `app`) and ~90 route modules under `api/routes/` |
| `src/fichero/workflows/` | LangGraph workflow engine, tool registry, graph builder |
| `src/fichero/kg/` | Knowledge graph: entities, claims, aggregation, curation |
| `src/fichero/loaders/` | Text extraction (PDF, DOCX, images, …) |
| `src/fichero/cli/` | Typed CLI mirroring the engine's HTTP surface (`openapi_surface_generated.py`) |
| `src/fichero/db.py` | DuckDB + LanceDB storage |
| `src/fichero/models.py` | Pydantic models |
| `src/fichero_backend/` | Briefcase entry point for the bundled backend app |
| `tests/` | `unit/`, `integration/`, `contracts/` |
| `pyproject.toml` | Package + Briefcase config; console scripts (`fichero`, `fichero-mcp`) |

## Install

The package runs from source on `PYTHONPATH`. From the repo root:

```bash
PYTHONPATH=fichero-engine/src .venv/bin/python -c "import fichero"
```

`PYTHONPATH=fichero-engine/src` is required for every Python command.

## Run

**The engine must serve HTTPS.** The SwiftUI app pins `https://127.0.0.1:8765`
fail-closed, so a plain-HTTP server is unreachable. Use the supported launcher —
it prepares loopback TLS material, persists the SPKI pin, and runs uvicorn with
`--ssl-*` (and scopes `--reload` to `fichero-engine/src`):

```bash
bash fichero-engine/scripts/start_backend.sh
```

> Do **not** run a bare `uvicorn fichero.api.main:app --port 8765` for the app —
> it serves HTTP and the pinned client cannot connect.

For remote / off-network access, the engine still binds loopback only and is
fronted by `tailscale serve` (never funnel) — see
`docs/architecture/` and `docs/remote-backend-tailscale.md`.

## Test

```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ \
  --ignore=fichero-engine/tests/unit/_archived
```

Lint:

```bash
ruff check fichero-engine/src/
```

## Contributing

Backend-specific working notes live in [AGENTS.md](AGENTS.md). For the repo-wide
workflow, see [CONTRIBUTING.md](../CONTRIBUTING.md) and
[docs/developer/setup-and-contributing.md](../docs/developer/setup-and-contributing.md).

## How it works — workflows + knowledge graph

- **Workflows (LangGraph).** A workflow is a graph of tool nodes built and run by
  the engine in `workflows/` — e.g. *load files → transcribe (vision model) →
  extract entities → summarize → catalogue → export*. The SwiftUI app exposes
  this as a visual node editor, but the graph executes server-side, step by step
  and reproducibly across many documents. Workflow runs stream progress over an
  SSE activity channel.
- **Providers (LiteLLM).** Models are addressed through LiteLLM, so the same
  workflow runs against 100+ providers — local (Ollama, LM Studio, MLX) or cloud
  with your own API key. API keys are stored in the macOS keychain.
- **Knowledge graph.** Extraction produces **entities** (people, places, orgs,
  dates) and **claims** (subject–predicate–object statements) with provenance
  back to the source document. The KG is engine-owned; clients render and curate
  it. Curation decisions persist as rules that subsequent imports obey.
- **Action registry.** Engine mutations flow through a single typed action layer
  (`registry.invoke`) that emits change events and writes an audit record —
  shared by the API, CLI, and (planned) chat/App-Intent tools. See
  `docs/developer/action-registry.md`.

## MCP server

`fichero-mcp` exposes engine capabilities to MCP-aware agents
(`src/fichero/mcp_server.py`; `fichero-mcp-simple` is a minimal variant).

## Keep the Swift client in sync

When routes or schemas change, regenerate and copy the OpenAPI schema into the
Swift package the app consumes:

```bash
./fichero-engine/scripts/sync_openapi_schema.sh
```

## Bundle the backend app

```bash
./fichero-engine/scripts/build_backend_bundle.sh
```

## Clean local generated artifacts

```bash
./fichero-engine/scripts/clean_local_artifacts.sh
```

## OCR vs HTR model guidance

- **OCR** (printed / typewritten pages): start with `Qwen/Qwen3-VL-8B-Instruct`
  or OCR-specialized models like `datalab-to/chandra-ocr-2` and
  `nanonets/Nanonets-OCR-s`.
- **HTR** (handwritten pages): prefer `gpt-5` first; `gemini-3-pro-preview` is a
  strong alternative.
- In `Transcribe (Auto-Detect)`, handwritten branches (`manuscript`, `htr`,
  `paleography`) should use HTR-capable vision models; printed branches
  (`typescript`) can prioritize OCR-specialized models.
