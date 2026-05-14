# Plan: `fichero-cli` — a separate command-line client to the backend

**Branch:** `fichero-cli` (isolated worktree at `~/code/fichero-cli`). **Never** work on `0.0.2` here — a separate autonomous loop owns that branch concurrently.

## Why

The hard part of all Fichero work has been: *we don't know if the backend actually works.* Every fix this milestone is "pytest-green but NOT verified by a real run." The SwiftUI app is the only live client, and it's slow to build/verify.

A thin CLI client fixes this. It:
1. Lets the backend be exercised live — import, run workflows, query the KG, search — without the SwiftUI app.
2. Becomes the **real-run verification harness** that's been missing.
3. Is the reference **"dumb client"**: if a CLI can drive the whole catalogue pipeline over HTTP, the backend by-construction owns all the logic — which is the architectural principle (`feedback_kg_logic_in_backend`: backend is logic, frontend only displays).

`pyproject.toml` already declares the entry points (`fichero = "fichero.__main__:main"`, `fichero-mcp = "fichero.mcp_server:main"`) — they were scaffolded but never implemented. `typer` + `httpx` are already dependencies. No new deps needed.

## Hard constraints — READ FIRST

- **HTTP-only client. Never touch backend logic.** This loop may CREATE/EDIT only:
  - `fichero-engine/src/fichero/cli/` (new package)
  - `fichero-engine/src/fichero/__main__.py`
  - `fichero-engine/src/fichero/mcp_server.py`
  - `fichero-engine/tests/unit/test_cli_*.py` (and `test_mcp_server.py`)
- It **may IMPORT** `fichero.models` / `fichero.knowledge_models` for typed response shapes.
- It **MUST NOT** import from or edit anything under `fichero/api/`, `fichero/workflows/`, `fichero/db*`, `fichero/kg/`, `fichero/llm*`, or any other backend module. No backend logic, ever. If a response shape isn't in `fichero.models`, define a small local Pydantic model in `cli/` — do not reach into backend internals.
- One logical unit per commit, to the `fichero-cli` branch. Every commit gated: `pytest` + `ruff` via a test-runner subagent. See `docs/agent-workflow/parallel-execution.md`.

## Architecture

```
fichero/cli/
  client.py   — FicheroClient: thin httpx wrapper. Base URL :8765, reads the
                Bearer auth token (the 0600 token file the Swift app uses — see
                fichero/api/auth.py for where it's written), sets the
                library-path header. Sync httpx. Returns parsed JSON, typed via
                fichero.models where a model exists.
  formatters.py — render results as human-readable text OR raw JSON (--json).
fichero/__main__.py — typer app: the command tree on top of FicheroClient.
fichero/mcp_server.py — (phase 2) MCP server exposing the same client ops as tools.
```

## Phase 1 — client core + CLI

`client.py` + `__main__.py` with these commands (each is a thin call to one or
two backend endpoints — consult `fichero-engine/tests/contracts/openapi.json`
for the exact routes/shapes):

- `fichero health` — `GET /api/health`
- `fichero import <path> [--mode copy|link|move]` — ingest a file/folder
- `fichero docs list` / `fichero docs get <id>` — list / inspect documents
- `fichero workflow list` / `fichero workflow run <name> <doc-id> [--wait]` —
  run a workflow; `--wait` polls activity until the run completes/fails
- `fichero artifacts <doc-id>` — list a document's artifacts
- `fichero kg entities <doc-id>` / `kg claims <doc-id>` / `kg search <query>`
- `fichero search <query>` — document/semantic search
- `fichero activity` — recent workflow runs + status

Every command supports `--json`. Auth + library-path handled automatically by
`client.py` (CLI takes `--library <path>` or reads a sensible default).

Tests: mock the HTTP layer (`httpx.MockTransport` or `respx`) — do NOT require a
live backend for unit tests. Cover: auth header is set, library-path header is
set, each command builds the right request, `--json` vs human output.

## Phase 2 — MCP server

`fichero/mcp_server.py` — exposes the same operations as MCP tools, reusing
`client.py` (do NOT reimplement the HTTP layer). One tool per CLI command.
Tests: tool registration + arg passthrough, HTTP layer mocked.

## Phase 3 — live smoke test

With a real backend running on `:8765`: run a real catalogue workflow on a
born-digital PDF end-to-end via the CLI (`import` → `workflow run --wait` →
`artifacts` / `kg entities`). Capture the transcript to
`agent-work/proposals/fichero-cli-smoke.md`. This is the real-run verification
the project has never had — note anything that looks wrong (empty KG, garbage
transcription, hangs) as observations, do NOT fix backend issues here.

## When done

Open a PR `fichero-cli` → `0.0.2`. The files are disjoint from the `0.0.2`
loop's work (that loop touches backend logic + SwiftUI; this touches only
`cli/` + entry points + cli tests), so the merge is clean.

If all phases complete and there's nothing left: write a short status note to
`agent-work/proposals/fichero-cli-status.md` and stop. Do not invent scope.
Stop if `BLOCK.md` first line says `BLOCKED`.
