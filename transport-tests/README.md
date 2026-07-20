# Fichero transport tests & profiling

Standalone, headless assets for the transport work (UDS-embedded + TCP/TLS).
They boot the **real engine** on a plain-HTTP Unix-domain socket (and a plain
TCP loopback port for profiling) and exercise it end-to-end. Nothing here
touches the repo packages — the manager integrates later.

## Prereqs

- Dev venv: `/Users/danieltubb/code/fichero/.venv` (py3.12, has `httpx` + `uvicorn`).
- Engine source on `PYTHONPATH`. The venv is a **stale non-editable** copy of
  `fichero`, so newer modules (`fichero.api.uds_transport`) are missing from
  site-packages — you MUST prepend the engine `src`:

  ```
  export PYTHONPATH=/Users/danieltubb/code/fichero/fichero-engine/src
  ```

  Override the engine location with `FICHERO_ENGINE_SRC` if it lives elsewhere.

## How the harness boots the engine (`_engine_harness.py`)

`fichero.api.uds_transport:app` wraps the main ASGI app and stamps
`scope["fichero.transport"] = "uds"` so `_is_loopback_request` trusts a UDS
connection as loopback-owner (TLS is exempt — there is no network listener).
The harness launches uvicorn on that app with:

| env | why |
|-----|-----|
| `FICHERO_UDS_PATH=<sock>` | bind the plain-HTTP UDS server (short path in `/tmp`, mind the ~104-byte `sun_path` limit) |
| `FICHERO_BASE_PATH=<tmp>` | point `app.duckdb` / `global.fichero` at a fresh temp dir so it never fights a **live engine** for the `app.duckdb` lock |
| `FICHERO_BOOTSTRAP_TOKEN=<tok>` | pin the bootstrap secret to a known value (no need to scrape the 0600 `.api-key`) |
| `FICHERO_MULTIUSER=0` | single-user mode: the loopback bootstrap token IS the owner credential |

The TCP transport binds `fichero.api.main:app` on a plain-HTTP `127.0.0.1` port
**for profiling convenience only** — the production engine mandates TLS on the
TCP path; `/api/health` is unauthenticated so no token is needed to profile it.

## Asset 1 — UDS live round-trip test

```
PYTHONPATH=/Users/danieltubb/code/fichero/fichero-engine/src \
/Users/danieltubb/code/fichero/.venv/bin/python -m pytest \
    pytest/test_uds_roundtrip.py -v
```

Asserts, over a real UDS:
- `GET /api/health` → **200** (unauthenticated path works)
- `GET /api/actions/registry` **without** a token → **401** (auth enforced over UDS)
- same **with** the bootstrap token → **200** (loopback-owner grant works over UDS — the CRITICAL-1 regression at the engine level)
- a **wrong** token → **401**

## Asset 2 — profiling harness

```
PYTHONPATH=/Users/danieltubb/code/fichero/fichero-engine/src \
/Users/danieltubb/code/fichero/.venv/bin/python \
    profile_transports.py --n 200 --out results.json
```

Flags: `--n` requests per transport, `--out` JSON path, `--skip-tcp`,
`--import-repeats` (reports the min cold-import time).

Measures and prints a table + writes `results.json` (diffable):
- **Cold import**: wall time to `import fichero.api.main` in a fresh interpreter.
- **Per-request p50/p95**: over N `GET /api/health` for `uds` and `tcp`.
- **Streaming TTFB**: UDS vs TCP if a drivable streaming endpoint exists.

### Out of scope (noted, not measured)
- **In-memory ASGI** (Swift/PythonKit `AsyncHTTPClientTransport` driving the app
  in-process) — not reachable from a pure-Python harness.
- **Streaming TTFB** currently reports "none available": the streaming endpoints
  (`/api/changes/stream`, `/api/activity/stream`) require a provisioned
  `.fichero` library via `X-Fichero-Library-Path`, which a lean profiling
  harness does not set up. Add a library + candidate path to enable it.
- The app-side **launch-to-first-authenticated-response p95** layers on top of
  these numbers later.
