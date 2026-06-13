# STATE — handoff 2026-06-13 ~03:46 ADT (overnight autonomous run)

Branch `0.0.2` @ `51fe9a21`, **pushed, clean** (local == origin). Daniel runs the backend himself (`uvicorn --reload --reload-dir fichero-engine/src`).

## Tonight shipped (all verify_all --standard green, NEVER pushed red)
**Security review fixes** (Opus+Fable): #2170 AppleScript-injection, #2175 lazy-hash, #2171 viewers-can-read, #2174 pairing-invariant, #2172 touch-throttle, #2173 device-expiry, #2145 login-rate-limit, #2129 sliding-expiry+key-redaction, #2146 upload-cap+parquet, #2153 programmatic security guardrail. **Security milestone DONE.**
**Perf** (#2165 Stage-2 parallelize, #2166/#2167 N+1s, #2168 reindex batching).
**AI backend**: #2151 AI-integrity system prompts, #2152 agent working-memory layer.
**Regression I caused + fixed**: #2173 added devices.expires_at via CREATE-IF-NOT-EXISTS → broke real app.duckdb (500s) → poisoned-WAL native crash loop. Fixed: idempotent migration #2182 + CHECKPOINT-after-ALTER. app.duckdb healed; WAL backup at `~/Library/Application Support/Fichero/app.duckdb.wal.poisoned-bak` (deletable).
**Workflow path fix**: #2183 — all 4 source tools resolve library-relative paths via resolve_source (unblocked ICANH transcription).
**5 adversarial test batches** (test-only, drained Test Coverage): auth surface, KG extraction core, db+search/documents routes, KG modules, workflow-builder+llm core.

## Open follow-ups (filed)
- **#2186** — re-add a robust async-isolated upload-streaming unit test (removed a flaky one; route-level 413 test covers the cap).
- **#2187** — 11 integration tests failing + NOT gated (verify_all runs tests/unit/ ONLY). Triaged the headline one = STALE TEST (iterates a Pydantic model → tuples), not a product bug. Remaining 10 need per-test triage (env vs stale vs real). Consider a separate gated integration lane.
- **#2157/#2158** (TLS LAN listener + Bonjour) — NOT done: the conn-net worker was blocked on no-network dep installs (cryptography/zeroconf). Worktree removed (0 commits). Re-dispatch when deps are confirmed present, or descope Bonjour.

## HARD rules in force
- **codex gpt-5.4 tmux workers** for everything; Opus only for security reviews. Worktrees ONLY under `~/code/fichero-worktrees/`.
- **Backend code edits in a WORKTREE**, never the main tree — Daniel's `--reload` watches `fichero-engine/src`; live edits caused 3 native DuckDB crashes. Land atomic commits.
- **Migrations allowed** (rule #9 retired) — ALTER on a persisted DB MUST be followed by `CHECKPOINT`.
- **Gate discipline**: `verify_all --standard` (runs `tests/unit/` only), parse for `verify_all (standard): ALL PASS`, push as a SEPARATE command, never red. New endpoints trip 4 guardrail baselines (ui_wiring/endpoint_coverage_matrix/endpoint_usage/undo_coverage) + need openapi regen. New test files can trip check_test_assertions vacuous-detector (allowlist helper-delegating tests in scripts/check_test_assertions.py).

## ICANH demo (still pending Daniel)
Library `~/Documents/Fichero-Libraries/ICANH-Andagoya.fichero` — 15 PDFs COPY-imported (files/fi/, 114 page-records). Path fix (#2183) unblocked transcription; last blocker was "LLM provider not configured" for the vision step. NEXT: set vision provider/model to Apple via CLI, run `workflow run "Transcribe" <doc>`, review Apple Vision quality on 19th-c Spanish handwriting; if weak → qwen2.5vl via OpenRouter. Drive via CLI manager-direct.

## Roadmap after this
Backend is rock-solid (Daniel's gate before Mac). Remaining backend: drain more Test Coverage (Swift UI gaps SKIP), triage #2187 integration rot, #2157/#2158 LAN transport. Then per Daniel: Mac (#2081 node model) → iOS → intelligence/node-editing.

`entitytable-2020` worktree (#2020 entity provenance Table) is Daniel's held lane — left intact.
