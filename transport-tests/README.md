# Fichero transport tests & profiling

Standalone, headless assets for the transport work (UDS-embedded + TCP/TLS).
They boot the **real engine** on a plain-HTTP Unix-domain socket (and a plain
TCP loopback port for profiling) and exercise it end-to-end. Nothing here
touches the repo packages — the manager integrates later.

## Prereqs

- Shared dev venv (repo root: `source .venv/bin/activate`; py3.12, has
  `httpx` + `uvicorn`).
- Engine source on `PYTHONPATH`. The venv is a **stale non-editable** copy of
  `fichero_server`, so newer modules (`fichero_server.api.uds_transport`) are
  missing from site-packages — you MUST prepend the engine `src`:

  ```
  export PYTHONPATH=fichero-server/src   # relative to the repo root
  ```

  `_engine_harness.py`'s `engine_src()` already defaults to
  `fichero-server/src` resolved relative to its OWN file location, so this
  works in any worktree without editing anything — the export above is
  belt-and-braces for the parent interpreter. Override with
  `FICHERO_ENGINE_SRC` if the engine lives elsewhere.

## How the harness boots the engine (`_engine_harness.py`)

`fichero_server.api.uds_transport:app` wraps the main ASGI app and stamps
`scope["fichero.transport"] = "uds"` so `_is_loopback_request` trusts a UDS
connection as loopback-owner (TLS is exempt — there is no network listener).
The harness launches uvicorn on that app with:

| env | why |
|-----|-----|
| `FICHERO_UDS_PATH=<sock>` | bind the plain-HTTP UDS server (short path in `/tmp`, mind the ~104-byte `sun_path` limit) |
| `FICHERO_BASE_PATH=<tmp>` | point `app.duckdb` / `global.fichero` at a fresh temp dir so it never fights a **live engine** for the `app.duckdb` lock |
| `FICHERO_BOOTSTRAP_TOKEN=<tok>` | pin the bootstrap secret to a known value (no need to scrape the 0600 `.api-key`) |
| `FICHERO_MULTIUSER=0` | single-user mode: the loopback bootstrap token IS the owner credential |

The TCP transport binds `fichero_server.api.main:app` on a plain-HTTP
`127.0.0.1` port **for profiling convenience only** — the production engine
mandates TLS on the TCP path; `/api/health` is unauthenticated so no token is
needed to profile it.

## Asset 1 — UDS live round-trip test

Run from the repo root, with the shared venv activated:

```
PYTHONPATH=fichero-server/src python -m pytest \
    transport-tests/pytest/test_uds_roundtrip.py -v
```

Asserts, over a real UDS:
- `GET /api/health` → **200** (unauthenticated path works)
- `GET /api/settings/model-profiles` **without** a token → **401** (auth enforced over UDS)
- same **with** the bootstrap token → **200** (loopback-owner grant works over UDS — the CRITICAL-1 regression at the engine level)
- a **wrong** token → **401**

(The auth endpoint was `/api/actions/registry` pre-#4227; that route no
longer exists. `/api/providers/catalog` looked like a replacement but
404'd live — `/api/providers` turned out to be feature-tier-gated to
`beta`, not registered at the default `release` tier this harness boots
with; confirmed via the live engine's own `/openapi.json`, not guessed.
`/api/settings/model-profiles` is genuinely app-wide — reads the app-level
DB, not a per-library one — and is not tier-gated at all.)

## Asset 2 — profiling harness

Run from the repo root, with the shared venv activated:

```
PYTHONPATH=fichero-server/src python \
    transport-tests/profile_transports.py --n 200 --out results.json
```

Flags: `--n` requests per transport, `--out` JSON path, `--skip-tcp`,
`--import-repeats` (reports the min cold-import time).

Measures and prints a table + writes `results.json` (diffable):
- **Cold import**: wall time to `import fichero_server.api.main` in a fresh interpreter.
- **Per-request p50/p95**: over N `GET /api/health` for `uds` and `tcp`.
- **Streaming TTFB**: UDS vs TCP if a drivable streaming endpoint exists.

### Out of scope (noted, not measured)
- **In-memory ASGI** (Swift/PythonKit `AsyncHTTPClientTransport` driving the app
  in-process) — not reachable from a pure-Python harness.
- **Streaming TTFB** currently reports "none available": the one real
  candidate, `/api/changes/stream` (#1863; the pre-#4227 harness pointed at
  `/api/activity/stream`, which does not exist), requires a provisioned
  `.fichero` library via `X-Fichero-Library-Path`, which this lean profiling
  harness's fresh `FICHERO_BASE_PATH` does not set up. Add a seeded library +
  the header to enable it.
- The app-side **launch-to-first-authenticated-response p95** layers on top of
  these numbers later.
