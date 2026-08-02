# CLI + MCP live round-trip verification (#4465) — 2026-08-02

Not a test run: a real engine, a real library, real bytes on disk. Isolated
from Daniel's data throughout (`FICHERO_BASE_PATH=/tmp/fichero-4465/base`,
scratch library `/tmp/fichero-4465/Test4465.fichero`, torn down after).

**Verdict in one line: the CLI works end to end once you get past the front
door — which no documented configuration gets you past; the MCP server works
for reads and note-writes, but its workflow tool is a silent no-op and its
mutations are attributed to the owner, not the agent.**

## Setup (reproducible)

```bash
# engine: production-style TLS on 8765, isolated base path, beta tier (what the app spawns)
PYTHONPATH=fichero-server/src FICHERO_BASE_PATH=/tmp/fichero-4465/base \
FICHERO_BOOTSTRAP_TOKEN=test-token-4465 FICHERO_MULTIUSER=0 FICHERO_FEATURE_TIER=beta \
FICHERO_TLS_CERTFILE=<Remote Access material>/server.crt FICHERO_TLS_KEYFILE=.../server.key \
python -m uvicorn fichero_server.api.tcp_transport:app --host 127.0.0.1 --port 8765 \
  --ssl-certfile ... --ssl-keyfile ... --ws websockets-sansio

# CLI env that finally worked:
export FICHERO_API_URL=https://127.0.0.1:8765 FICHERO_API_KEY=test-token-4465 \
       SSL_CERT_FILE=<that same server.crt> FICHERO_LIBRARY_PATH=/tmp/fichero-4465/Test4465.fichero
```

## CLI — command by command

| Step | Command | Result |
|---|---|---|
| health, default config | `fichero health` (no env) | ✗ "Server disconnected without sending a response" — `http://` default vs TLS engine |
| health, https | `FICHERO_API_URL=https://…` | ✗ "Cannot connect… Is the engine running?" — actually a cert-verify failure, misreported |
| health, + SSL_CERT_FILE | undocumented workaround | ✓ healthy |
| create library | `fichero library create /tmp/fichero-4465/Test4465.fichero` | ✓ created + registered |
| list libraries | `fichero library list` | ✓ |
| import | `fichero import test-fixtures/files/multipage.pdf` | ✓ doc + 3 pages, text extracted. ⚠ pages named `fichero_upload_….pdf - Page N`, `source_path` = temp file (persisted #4416-family leak) |
| list docs | `fichero docs list` | ✓ 5 rows |
| search | `fichero search "Page 2"` | ✓ 3 hits, highlights |
| workflow list, release tier | `fichero workflow list` | ✗ 404 — `/api/workflows` is tier-gated to beta; release-tier engine registers only ingest+search of the gated groups |
| workflow list, beta tier | same | ✓ 39 workflows (defaults present in a fresh library — #4450 holds) |
| workflow run | `fichero workflow run "Convert to Markdown" <doc> --wait` | ✓ completed, 3 artifacts |
| artifacts | `fichero artifacts list/get` | ✓ content retrieved (apple-vision conversion) |
| export | — | ✗ **no CLI command exists.** Server side proven separately: `POST /api/export/parquet` → 200, wrote 3 parquet files + manifest |

## MCP — over real stdio, real client

- 25 tools listed, **all with descriptions** (the July finding of blank
  descriptions applied to `fichero_mcp.full`, which remains entry-point-less).
- Reads work: `fichero_health`, `fichero_search` returned live data.
- Mutation works but is misattributed: `fichero_create_note` → note created,
  and the `/api/actions/audit` row says **`actor: "owner"`**, note
  `author_type: "user"`. An agent write is indistinguishable from Daniel's.
- The agent-actor path (`_agent_client`, as_user="agent") covers ONLY the four
  `fichero_workspace_*` tools and hard-fails without `fichero auth login agent`
  (which needs FICHERO_MULTIUSER=1): "No stored session for agent".
- `GET /api/kg/mutations` (MutationLog) stayed **empty** the whole session. The
  audited KG mutation routes `/api/mcp/tools/knowledge/*` — the ones that DO
  stamp `request_actor` into MutationLog — are called by nothing in
  fichero-mcp/src. Built-but-unwired.
- **`fichero_workflow_run` is a silent no-op.** It sends `{"files": [doc_id]}`;
  the files-source node only reads `selected_doc_ids` (the CLI's own comment
  documents this). Live result: `status: completed`, `error: null`,
  `files-source: {documents: [], count: 0}`, zero artifacts. The engine
  completed green on nothing.

## Issues filed

- **#4467** (P0, Workflows) — MCP workflow_run silent no-op + engine completes
  green on zero resolved inputs.
- **#4468** (P1, Connection & Transport Hygiene) — CLI/MCP have no TLS trust
  path; http default; misleading connect error.
- **#4469** (P1, Accounts & Multi-user) — MCP mutations audit as owner; agent
  path unreachable by default; `/api/mcp/tools/knowledge/*` wired to nothing.
- **#4470** (P1, API Surface & Test Harness) — release tier hides 20 route
  groups; bare 404s; AGENTS.md "dev gates only iiif" is false.
- **#4471** (P2, Bugs Testing Lint Engine) — no export command; `engine stop`
  graceful path can't work (`import requests`, plain http vs TLS); import
  persists temp-upload name as source.

## What this means for the "is the CLI any good" question

The plumbing is genuinely there — import, search, workflows, artifacts,
defaults-in-every-library, parquet export all executed correctly on a fresh
library over the production transport. What is broken is the *rim*: connection
bootstrap (trust, tier, error text) and the two places a client resolved scope
its own way (workflow inputs key; agent-vs-owner credential). Both rim defects
are the same shape as the week's twelve: a complete mechanism with a wrong or
missing feed, invisible to unit tests, found only by dialing the real socket.
The transport-tests harness (#4437) should grow exactly this round trip as a
scripted asset so it never regresses silently; the harness booted this engine
in seconds and none of this needed Xcode.
