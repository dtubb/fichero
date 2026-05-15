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
| 3 — live smoke test | ✅ Done (with one backend bug surfaced — `#609`) | initial transcript: `debe81a3`; full mutating retry + CLI bug fixes: `87a7d6e4` |

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

### Phase 3 (done — `fichero-cli-smoke.md` has both transcripts)
First run (`debe81a3`) was blocked on a shared-token-file last-writer-wins
problem across concurrent backends — see the first half of the smoke
transcript. With a single backend running, the auth mismatch goes away and
every endpoint authenticates correctly.

Phase 3 retry on 2026-05-15 ran the full flow end-to-end via the CLI:
`import` → `workflow run --wait` → `artifacts` / `kg entities` / `kg claims`.
The read surface is all green. The mutating flow ran but surfaced one
backend bug: **`#609` Files-node-empty-selection** reproduces from the CLI —
the workflow completes with `output_files: 0` even though the CLI sends
`{"files": [<doc-id>]}` in the run request, confirming the bug is in
backend workflow-input plumbing, not in the SwiftUI app.

Two CLI bugs were also surfaced and fixed in `87a7d6e4`:
1. `kg entities <doc-id>` / `kg claims <doc-id>` rejected the positional
   doc-id (the plan's signature) because they only accepted `--query`/`--doc`
   flags. Both now take positional doc-id; `kg entities` reads the
   document inspector endpoint and renders only the `entities` field.
2. `workflow run --wait` blew up on the first poll because the LangGraph
   checkpoint is created asynchronously and 404s briefly (or never, for
   fast/empty runs). `--wait` now tolerates 404 during polling and raises
   a clear timeout error on budget exhaustion instead of returning `None`.

## Outstanding / for a future loop

1. **`#609` blocks end-to-end "workflow actually does work."** The CLI is
   ready; the backend isn't. Once `#609` is fixed, the same CLI invocation
   used in the retry should produce non-empty artifacts and KG rows.
2. **Architecture gap: no typed response models.** The plan said "typed via
   `fichero.models` where a model exists" — the CLI as shipped uses raw
   dicts and infers field names from the OpenAPI spec at
   `fichero-engine/tests/contracts/openapi.json`. SwiftUI gets generated
   types; the Python CLI gets nothing. The right Python fix is direct
   `model_validate` against the shared Pydantic models (no codegen needed,
   since both halves are one Python project). Worth a follow-up.
3. **Backend observations** that need their own issues, not fixed here:
   - shared-token-file last-writer-wins across concurrent backends
     (the original Phase 3 blocker)
   - `artifacts` table missing on fresh libraries — surfaced by `kg search`
     ("Did you mean activities?")
   - import multipart renames the original filename
   - `--wait` polling endpoint vs activity log are not unified — activity
     is the actual source of truth; the checkpoint endpoint 404s for
     fast/empty runs
4. **A `fichero delete <id>` command** would close the harness loop —
   import → workflow → inspect → delete — and let it run repeatably
   without polluting Daniel's library.

## Notes

- One known pre-existing test failure on this branch:
  `test_routes_settings.py::test_reset_clears_all_settings` (`AssertionError` in
  backend settings code) — unrelated to this work, out of scope.
- `CONTINUE.md` in the worktree root is an untracked heartbeat file from
  another loop — left untouched.
