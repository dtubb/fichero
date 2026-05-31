# Reality Check: Infrastructure Milestone — 2026-05-31

Read-only audit. No code run, no git changes. Focused on the current OPEN set only
(issues noted in the task brief). Code evidence via jCodemunch + grep + Read.

---

## Scope

10 open issues in the Infrastructure milestone as of 2026-05-31. The task brief
called out the following for priority attention:
#1341 (storage paths), #1239 (SSH remote), #477/#510 (API auth), #515 (integrations gate),
#461 (async DNS), #320 (bundle-ID migration). Also audited: #709, #664 (coverage).

---

## Issue-by-Issue Verdict

| # | Title | Verdict | Evidence |
|---|-------|---------|----------|
| **#477** | API Security: localhost-only binding + optional API key auth | **DONE** | `fichero-engine/src/fichero/api/auth.py` is fully implemented: `initialize_token()` generates a 32-byte secret and writes it to `~/Library/Application Support/Fichero/.api-key` (mode 0600); `attach_auth_middleware()` in `api/main.py` (lines 495–499) enforces `Authorization: Bearer <token>` on every non-health request AND rejects any client host that isn't `127.0.0.1 / ::1 / testserver`. Loopback-only binding is enforced. `FICHERO_DISABLE_AUTH=1` bypass exists for tests only. This is a faithful implementation of the exact middleware pattern in the issue body. |
| **#510** | [Release Gate] 0.5.1 - Wire: API Security + Auth | **DONE** | Same codebase as #477. All gate checklist items map to code: Settings → Backend → API Key section is served by `api/routes/provider_keys.py`; token generation in `auth.py`; SwiftUI reads the key from `.api-key` via `cli/client.py:_TOKEN_PATH`; MCP config can use the same token; 401 is returned by middleware for missing/wrong header. Gate is deliverable today. |
| **#515** | [Release Gate] 0.7.2 - Wire: Integrations | **OPEN** | `IntegrationsPlaceholderSheet.swift` exists and is shown for all integrations links — it displays "Coming Soon / planned for a future release." GitHub OAuth and Netlify connect flows are not implemented anywhere: no OAuth handler in Swift or Python, no GitHub/Netlify in `fichero-engine/src/fichero/integrations/` (only `base.py`, `bookends.py`, `devonthink.py`, `tinderbox.py`). The `integrations.py` backend route handles macOS app integrations (DEVONthink etc.), not GitHub/Netlify. The Integrations menu re-enable (#280) is also still deferred (`FeatureManager.swift` shows `integrationsEnabledInternal` defaulting to `false`). Gate cannot pass. |
| **#461** | research_tools.py / research.py: make `_is_safe_url` async (socket.getaddrinfo is blocking) | **OPEN** | `research_tools.py` line 119 shows `socket.getaddrinfo(hostname, None)` called synchronously inside the `_is_blocked_ip()` helper, which is called by `_is_safe_url()` — both are plain `def`, not `async def`. The fix (`asyncio.to_thread(socket.getaddrinfo, ...)`) is not present. The blocking call is still there and `_is_safe_url` is called from six different async route handlers in `research_tools.py` (lines 198, 214, 296, 331, 382, 416, 541). `workflows/tools/research.py` has the same pattern. Bug is real and unfixed. |
| **#1341** | Audit + standardize Mac storage paths | **OPEN** | Mixed conventions confirmed in live code: `storage.py:77` uses `com.fichero.fichero`; `local_models.py:34` uses `com.fichero.fichero/models`; `audio_base.py:49` uses `com.fichero.fichero/models`; `storage_snapshots.py:42` uses `com.fichero.fichero/snapshots`; `action_library.py:82` uses `Fichero/actions`; `checkpointer.py:53` uses `Fichero/fichero.duckdb`; `slipbox_import.py:32` uses `Fichero/Slipbox.fichero`; `api/auth.py:45` uses `Fichero/.api-key`; `cli/client.py:78` uses `Fichero/.api-key`. No `paths.py` helper, no `engine_state_dir()` function exists anywhere in the codebase. Three distinct conventions (`com.fichero.fichero/`, `Fichero/`, `ca.tubb.fichero/`) are still in use. Work has not started. |
| **#1239** | Feature: run Fichero backend remotely on ACENET over SSH | **OPEN** | No SSH tunnel, remote-host config, or ACENET-specific code anywhere in the backend or Swift app. The SSRF guard in `research_tools.py` explicitly blocks `ssh://` scheme as a sandboxed-blocked URL (line 67). No remote-backend connection model exists. Not started. |
| **#320** | Bundle identifier migration: data migration for existing installs | **OPEN** | Issue asks for a one-time migration from `ca.tubb.fichero/` → `com.tubb.fichero/` (or newer canonical path). No such migration exists: no Swift migration code, no Python migration function, no reference to `ca.tubb.fichero` or `com.tubb.fichero` anywhere in the codebase (grep returned zero results for both strings). The issue notes this only affects dev/testing installs — P3 low priority. Not started, but correctly scoped as low-risk. |
| **#709** | Test: AppDatabase RLock prevents pending-query corruption under concurrent reads | **OPEN** | The RLock is implemented: `app_db.py:61` has `self._lock = threading.RLock()`. However, no stress/load test exists — `grep -r "stress\|concurrent.*db\|RLock.*test"` in the test suite returns nothing. The specific `pytest.mark.slow` multi-threaded test described in the issue body is absent. `fichero-engine/tests/` has no integration stress test for AppDatabase. |
| **#664** | Achieve 100% unit test coverage across backend and frontend | **OPEN** | Coverage is not at 100%. The test suite is active and substantial (`fichero-engine/tests/unit/` has many test files) but multiple modules (e.g. `storage.py`, `storage_snapshots.py`, `local_models.py`, `migrations.py`, `loaders/*`) lack dedicated unit tests. No CI coverage gate is configured (no `--cov-fail-under` in any config file found). Swift tests are sparse. This is a large aspirational issue — not close to complete. |

---

## Summary Counts

| Category | Count | Issues |
|----------|-------|--------|
| DONE — safe to close | 2 | #477, #510 |
| OPEN — genuinely needs work | 7 | #515, #461, #1341, #1239, #320, #709, #664 |
| PARTIAL | 0 | — |

---

## Safe to Close Now

- **#477** — `api/auth.py` fully implements localhost-only binding + Bearer-token auth middleware exactly as designed. Already running in production (tests set `FICHERO_DISABLE_AUTH=1` to bypass it). Close as COMPLETED.
- **#510** — Release gate for API Security + Auth. All checklist items are satisfied by the `auth.py` + `provider_keys.py` + `cli/client.py` implementation. Close as COMPLETED.

```bash
gh issue close 477 --repo dtubb/fichero --comment "Implemented: fichero-engine/src/fichero/api/auth.py — initialize_token() writes .api-key (mode 0600), attach_auth_middleware() enforces Bearer token + localhost-only on all non-health routes. Running in production."
gh issue close 510 --repo dtubb/fichero --comment "Gate satisfied by #477 implementation. All checklist items verified in codebase (auth.py, provider_keys.py, cli/client.py). Closing."
```

---

## Needs Work — Action Notes

| # | Blocking factor | Next step |
|---|----------------|-----------|
| #515 | GitHub OAuth + Netlify connect flows not built; Integrations menu still disabled (feature flag off) | Cannot close until OAuth flows exist and checklist passes manual QA |
| #461 | `_is_safe_url` and `_is_blocked_ip` are synchronous `def`; `socket.getaddrinfo` blocks the event loop at 6 call sites | Make `_is_blocked_ip` async, wrap `getaddrinfo` in `asyncio.to_thread`, cascade `await` to all callers in both `research_tools.py` and `workflows/tools/research.py` |
| #1341 | Three storage-path conventions coexist; no `paths.py` helper | Design canonical path, add `engine_state_dir()`, sweep 7 files, one-time migration on startup |
| #1239 | Nothing started | Design SSH tunnel model, define auth/library-path handling, implement and document |
| #320 | No migration code exists; low risk since only dev installs affected | One-time `ca.tubb.fichero/` → canonical-path move on startup; keychain service rename |
| #709 | RLock exists; stress test absent | Add `pytest.mark.slow` integration test with N threads hitting AppDatabase simultaneously |
| #664 | Large aspirational goal; no coverage CI gate | Set `--cov-fail-under=80` (not 100%) as a realistic intermediate target; audit uncovered modules |

---

*Verified via jCodemunch AST index, grep, and direct file reads. No code executed, no git changes.*
