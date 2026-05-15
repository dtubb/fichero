# fichero-cli — status

**Date:** 2026-05-14
**Branch:** `fichero-cli` → PR target `0.0.2`

## What this is

A thin, HTTP-only command-line + MCP client for the Fichero backend. It drives
the same FastAPI endpoints the SwiftUI app uses, so the backend can be
exercised live without the app — the "real-run verification harness" the
project has lacked. No backend logic: every operation is one or two HTTP calls
through `fichero.cli.FicheroClient`.

## Phase completion

| Phase | Status | Commits |
|---|---|---|
| 1 — client core + CLI | ✅ Done | `b9596d32` (FicheroClient HTTP wrapper), `136b0979` (typer command tree + formatters) |
| 2 — MCP server | ✅ Done | `acd349a2` (rewrote `mcp_server.py` as a thin FastMCP wrapper over `FicheroClient`) |
| 3 — live smoke test | ⚠️ Partial — blocked on auth environment | transcript: `agent-work/proposals/fichero-cli-smoke.md` |

### Phase 1 (done)
`fichero/cli/client.py` + `fichero/cli/formatters.py` + `fichero/__main__.py`.
Command tree: `health`, `import`, `docs list/get`, `workflow list/run [--wait]`,
`artifacts`, `kg entities/claims/search`, `search`, `activity`. Every command
supports `--json`. Auth + library-path headers handled automatically. Unit
tests mock the HTTP layer (`httpx.MockTransport`) — no live backend needed.

### Phase 2 (done)
`fichero/mcp_server.py` rewritten from a stale divergent implementation (its own
`X-API-Key` HTTP layer routing to a large fantasy API surface) to a thin
`FastMCP` wrapper that reuses `FicheroClient` — one MCP tool per CLI command,
13 tools. Errors propagate as `FicheroError` (FastMCP → `isError=True`) instead
of being swallowed into `{"error": ...}` dicts. Startup warning when no auth
token is discovered. `TestMCPAuthorization` in `test_integration_security.py`
re-pointed at the new Bearer-token model (it imported the deleted
`FicheroAPIClient`). Gated: full pytest suite + ruff + independent
code-reviewer and silent-failure-hunter review.

### Phase 3 (partial — see `fichero-cli-smoke.md`)
First live run against the backend on `:8765`. `health` works. The CLI's auth
is correctly implemented (verified — reads token file, sends Bearer header).
But **authenticated endpoints return 401**: the shared per-launch token file
(`~/Library/Application Support/Fichero/.api-key`) does not match the running
backend's in-memory token. `auth.py:initialize_token()` overwrites the file on
every engine startup, so the single shared file is last-writer-wins across
concurrent backend processes. This is an infra observation, **not a CLI bug**,
and not fixed here.

The mutating path (`import` → `workflow run --wait` → `artifacts` / `kg`) was
not executed: blocked by the auth mismatch, and the only available library is
Daniel's primary `Catalogue.fichero` (the Phase 1 CLI has no `delete` command,
so an imported test doc could not be cleaned up).

## Outstanding / for a future loop

1. Re-run the full Phase 3 mutating flow once the CLI can authenticate against
   a backend (see recommendations in `fichero-cli-smoke.md`: deterministic auth
   for the harness, a throwaway test library, and a `fichero delete` command).
2. The shared-token-file fragility (`fichero-cli-smoke.md`) is worth a backend
   issue on `0.0.2` or later — it affects anything that runs alongside the
   SwiftUI app's engine.

## Notes

- One known pre-existing test failure on this branch:
  `test_routes_settings.py::test_reset_clears_all_settings` (`AssertionError` in
  backend settings code) — unrelated to this work, out of scope.
- `CONTINUE.md` in the worktree root is an untracked heartbeat file from
  another loop — left untouched.
