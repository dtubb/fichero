# fichero-cli — Phase 3 live smoke test

**Date:** 2026-05-14
**Branch:** `fichero-cli` (worktree `~/code/fichero-cli`)
**Backend:** running on `127.0.0.1:8765` (PID 7373, pre-existing — not started by this session)
**Library:** `/Users/danieltubb/Documents/Catalogue.fichero`
**CLI invocation:** `PYTHONPATH=fichero-engine/src .venv/bin/python -m fichero ...`

## Summary

This is the first time the backend has been exercised through the CLI. The CLI
itself works correctly — it connects, reads the auth token file, and sends a
well-formed `Authorization: Bearer` header. But the **first real run
immediately surfaced an environment/infra fragility**: the shared per-launch
token file (`~/Library/Application Support/Fichero/.api-key`) does not match
the running backend's in-memory token, so every authenticated endpoint returns
`401`. The unauthenticated `health` path works.

The authenticated read paths and the full mutating path (`import` →
`workflow run --wait` → `artifacts` / `kg entities`) are **blocked on this auth
mismatch** — they cannot be smoke-tested against a backend whose token does not
match the key file.

## What ran

### ✅ `fichero health` — works (unauthenticated path)

```
$ fichero --library /Users/danieltubb/Documents/Catalogue.fichero health
status: healthy
library_path: /Users/danieltubb/Documents/Catalogue.fichero
database: /Users/danieltubb/Documents/Catalogue.fichero/fichero.duckdb
document_count: 0
```

`--json` produces the same payload as raw JSON. The CLI's base-URL discovery,
library-path header, request construction, and the formatter all work against
a live backend. Note `document_count: 0` — the `Catalogue.fichero` library is
currently empty.

### ❌ Authenticated endpoints — `401 missing or invalid Authorization header`

```
$ fichero ... workflow list
GET /api/workflows -> 401: {"detail":"missing or invalid Authorization header"}

$ fichero ... docs list --limit 5
GET /api/documents -> 401: {"detail":"missing or invalid Authorization header"}

$ fichero ... activity --limit 3
GET /api/activity/recent -> 401: {"detail":"missing or invalid Authorization header"}
```

The CLI surfaces the error cleanly (clear message, non-zero exit) — the error
handling is correct. The 401 is the *backend* rejecting the token.

## Observation — shared per-launch token file is unreliable with concurrent backends

This is the headline finding. **It is an infrastructure observation, not a CLI
bug, and not fixed here** (per the plan: note observations, do not fix backend
issues in this loop).

Diagnosis steps:

1. `fichero.cli.client._read_token()` correctly reads the 43-char token from
   `~/Library/Application Support/Fichero/.api-key`.
2. The CLI correctly sends `Authorization: Bearer <token>`.
3. A **raw `curl`** with the *exact same token* also gets `401`:
   ```
   curl -H "Authorization: Bearer <file-token>" .../api/workflows
   -> {"detail":"missing or invalid Authorization header"}
   ```
   → The fault is **not** in the CLI. The token in the key file does not match
   the running backend's in-memory token.

Root cause, from `fichero-engine/src/fichero/api/auth.py:49-69`:
`initialize_token()` is called once per engine startup and **"overwrites any
prior token"** with a fresh `secrets.token_urlsafe(32)`. The validating
middleware (`auth.py:79-102`) compares against the in-memory token of *that*
launch.

So the key file is last-writer-wins across backend processes. The moment more
than one backend exists on the machine — the SwiftUI app's embedded engine, an
autonomous-loop's `uvicorn`, a CLI verification backend — whichever launched
**last** owns the file, and clients reading the file are rejected by every
*other* running backend. That is exactly the situation this CLI project
creates, and it is precisely the kind of "works in pytest, breaks in a real
run" gap the CLI was built to catch.

### Why the mutating path was not run

The full Phase 3 flow (`import` a born-digital PDF → `workflow run --wait` →
`artifacts` / `kg entities`) was **not executed**:

- It is blocked by the auth mismatch above — `import` and `workflow run` are
  authenticated endpoints.
- Even if auth worked, the only available library is Daniel's primary
  `Catalogue.fichero` on a backend that may be serving Daniel or the `0.0.2`
  loop. The Phase 1 CLI has no `delete` command, so an imported test PDF and
  its artifacts/KG rows could not be cleaned up. Mutating a shared library
  autonomously, with no cleanup path, was judged out of bounds for this
  session.
- Starting a fresh backend from this worktree would call `initialize_token()`
  and overwrite the shared `.api-key` again — making the concurrent-backend
  problem worse and risking breaking Daniel's app. Not done.

## Recommendations (for a future loop / Daniel — not fixed here)

1. **The verification harness needs a deterministic auth path.** Options:
   - Backend honors an explicit `FICHERO_API_KEY` from the environment as its
     token (instead of always generating one), so a harness can launch a
     backend and a CLI with a known shared secret.
   - Or the CLI/backend support a per-backend token file path so concurrent
     backends don't collide on one file.
2. **A throwaway test library** (e.g. a temp `.fichero` package) so the mutating
   smoke path can run without touching `Catalogue.fichero`.
3. **A `fichero delete <id>` command** would make the harness self-cleaning and
   let the import → workflow → inspect loop run repeatably.

Once a backend the CLI can authenticate against is available, re-run the full
Phase 3 flow and append the transcript here.
