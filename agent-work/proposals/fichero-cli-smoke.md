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

---

## Phase 3 retry — 2026-05-15

Daniel started a single fresh backend on `:8765` from the `0.0.2` worktree,
which unblocked everything in the previous section: with one backend running,
the shared `.api-key` file matches the live in-memory token and the CLI
authenticates against every endpoint. The full Phase 3 flow ran end-to-end via
the CLI. Three real findings — two CLI bugs (now fixed in this commit) and one
backend bug that reproduces `#609`.

### Read surface — all green

```
fichero health                         → status: healthy, document_count: 0
fichero docs list                      → (empty, library was empty)
fichero workflow list                  → 4 workflows: Catalogue, NER per-page,
                                          Spanish Paleography, Transcribe
fichero activity --limit 3             → (empty pre-import)
fichero search test                    → results: (empty)
fichero kg search test                 → 0 hits, 0 of each category
fichero --json workflow list           → valid JSON
fichero docs get <bogus-id>            → 404 message on stderr, exit code 1
```

Authenticated `404` paths correctly print the upstream message on stderr and
exit non-zero — the previous section's claim about non-zero exit was right; my
follow-up confusion was about bash pipe-exit-code shadowing in my test script
(`head -5` always returns 0 even when the upstream command failed).

### Mutating flow — executed end-to-end

```
fichero --json import ~/Downloads/Abstract.pdf
→ doc_id 00d0dfa689a34130860f41281f5ea330
  status: pending, text_extracted: true, text_length: 2066
  name: fichero_upload_rgy9oy8u.pdf    ⚠ original "Abstract.pdf" was renamed

fichero workflow run Catalogue <doc-id> --wait
→ thread-dfe5c600261d
→ FIRST attempt: 404 from /workflow-execution/threads/.../status, CLI bailed
→ Backend log: workflow completed in 128ms, nodes_completed: 0,
                Files node output_files: 0
```

**Backend bug — `#609` reproduced from the CLI.** The workflow ran via HTTP
end-to-end, terminated successfully, but the `Files` node received an empty
selection despite the run request carrying `inputs: {"files": [<doc-id>]}`.
Zero downstream work, zero artifacts, zero KG rows. This is exactly the
`#609` symptom — and the CLI reproducing it independently confirms the bug
is in the backend (workflow input plumbing), not in the SwiftUI app. Not
fixed here per scope; flagged for the `0.0.2` loop.

### CLI bugs found and fixed in this commit

1. **`kg entities <doc-id>` / `kg claims <doc-id>` rejected the positional
   doc-id** ("unexpected extra argument"). The plan called for positional
   doc-id; the implementation had only `--query` / `--type` / `--doc` flags.
   Fixed by making doc-id a required positional argument and pointing
   `kg entities` at `/api/documents/{id}/inspector` (the same aggregate the
   SwiftUI inspector uses), filtered to the `entities` field so the output
   matches the command name. `kg claims` now passes the id as
   `source_document_id` to `/api/claims`. The rarely-useful `--query` flag
   on `kg claims` is dropped — silent breaking change, noted in the commit
   message.

2. **`workflow run --wait` blew up on a transient 404.** LangGraph creates
   the thread checkpoint asynchronously after the `/execute` POST returns,
   so the first poll routinely 404s with "No checkpoint found for thread";
   fast or empty runs may never produce one. The CLI now treats 404 as
   transient and keeps polling, but on poll-budget exhaustion raises a
   clear timeout error (pointing the user at `fichero activity`) rather
   than returning `None` silently. `FicheroError.status_code` lets pollers
   branch on the HTTP code without parsing message strings.

### Backend observations (recorded, not fixed)

- **`#609` Files-node-empty-selection** reproduced from the CLI (above). The
  payload the CLI sends matches what the SwiftUI app sends; the bug is
  downstream.
- **`artifacts` table missing** — `kg search` triggered a backend log line:
  `Catalog Error: Table with name artifacts does not exist! Did you mean
  "activities"?` The empty `Catalogue.fichero` library may not have run the
  migration that creates `artifacts`. Probably a per-library schema-init
  gap; harmless when artifacts/are produced via the SwiftUI flow because
  that path apparently creates the table on demand, but the CLI's
  read-only call surfaced the gap.
- **Filename rename on multipart import** — `Abstract.pdf` was stored as
  `fichero_upload_rgy9oy8u.pdf`. The CLI sends `file_path.name` (the
  original basename) in its httpx multipart upload; the rename happens
  server-side. Worth chasing in the `/api/documents/import` route.
- **`--wait` polling endpoint vs activity log are not unified.** The
  activity feed records `workflow_completed` events with the matching
  `thread_id` reliably; the `/workflow-execution/threads/.../status`
  endpoint 404s for fast or empty runs. A future iteration of `--wait`
  should poll activity instead of the checkpoint endpoint — activity is
  the source of truth.

### What still needs doing

End-to-end "import → run a workflow that actually processes the file →
inspect the artifacts/KG" remains blocked on `#609`. The CLI is now
sufficient to test that flow as soon as `#609` is fixed: no more CLI bugs
between Daniel and a real workflow run. The next non-`#609` CLI follow-up
would be a `fichero delete <id>` command so the harness can clean up test
imports without touching `Catalogue.fichero` by hand.
