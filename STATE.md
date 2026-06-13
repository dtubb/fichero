# STATE — handoff 2026-06-13 ~03:46 ADT (overnight autonomous run)

Branch `0.0.2` @ `51fe9a21`, **pushed, clean** (local == origin). Daniel runs the backend himself (`uvicorn --reload --reload-dir fichero-engine/src`).

## Tonight shipped (all verify_all --standard green, NEVER pushed red)
**Security review fixes** (Opus+Fable): #2170 AppleScript-injection, #2175 lazy-hash, #2171 viewers-can-read, #2174 pairing-invariant, #2172 touch-throttle, #2173 device-expiry, #2145 login-rate-limit, #2129 sliding-expiry+key-redaction, #2146 upload-cap+parquet, #2153 programmatic security guardrail. **Security milestone DONE.**
**Perf** (#2165 Stage-2 parallelize, #2166/#2167 N+1s, #2168 reindex batching).
**AI backend**: #2151 AI-integrity system prompts, #2152 agent working-memory layer.
**Regression I caused + fixed**: #2173 added devices.expires_at via CREATE-IF-NOT-EXISTS → broke real app.duckdb (500s) → poisoned-WAL native crash loop. Fixed: idempotent migration #2182 + CHECKPOINT-after-ALTER. app.duckdb healed; WAL backup at `~/Library/Application Support/Fichero/app.duckdb.wal.poisoned-bak` (deletable).
**Workflow path fix**: #2183 — all 4 source tools resolve library-relative paths via resolve_source (unblocked ICANH transcription).
**5 adversarial test batches** (test-only, drained Test Coverage): auth surface, KG extraction core, db+search/documents routes, KG modules, workflow-builder+llm core.

## 2026-06-13 daytime continuation (Daniel's queue: ICANH → #2187 → #2157/8 → Mac)
- **#2188 DONE (812d3819):** transcription artifacts were silently discarded (regression from #2183: absolute file_path vs library-relative Document.path). Fixed via `_doc_lookup` helper. verify_all 4779 passed. Verified on real ICANH data.
- **ICANH judged (see section below):** transcription works; presets pin gpt-4o-mini → Apple unreachable (#2189); Paleography fails at reference-search (#2190).
- **#2187 DONE (de4c7198/df0d55fd):** integration-test rot — pure test rot, NO product bugs. Stale tests repaired vs current API (envelope #1148, ingest db-param, seeder count) + env/model/hang cases skip-guarded. 494 ins / 1058 del. Closed. *Backlog idea: a gated integration lane so it can't silently rot again.*
- **#2157 BUILT but HELD for Daniel (branch feat/lan-tls-listener-2157 @ f0e305f0, worktree lan-tls-2157 — NOT merged, main stays clean).** Off-by-default TLS LAN listener + self-signed cert + loopback-only SPKI endpoint + auth middleware. 21 targeted tests pass; I security-reviewed it (bootstrap secret stays loopback-only; off-loopback tokens require the TLS listener; refuses 0.0.0.0; key 0600). **Gate caught a real security-CONTRACT conflict** (see #2157 comment): the new policy 401s a valid session/device token from non-loopback-non-TLS, but shipped #2177 test `test_auth_fork_accepts_valid_session_and_valid_device` asserts that is *accepted* (200). #2157-spec vs #2177-contract conflict = Daniel's security-model call (recommend adopting #2157's tightening + updating the #2177 test). I reverted the local cherry-pick rather than autonomously flip an auth-perimeter adversarial test.
- **#2158 DEFERRED:** Bonjour needs `zeroconf` — NOT installed and NOT declared in pyproject; needs a dep add (+network). Descoped until deps land.
- **#2186** — still open: re-add a robust async-isolated upload-streaming unit test.

## HARD rules in force
- **codex gpt-5.4 tmux workers** for everything; Opus only for security reviews. Worktrees ONLY under `~/code/fichero-worktrees/`.
- **Backend code edits in a WORKTREE**, never the main tree — Daniel's `--reload` watches `fichero-engine/src`; live edits caused 3 native DuckDB crashes. Land atomic commits.
- **Migrations allowed** (rule #9 retired) — ALTER on a persisted DB MUST be followed by `CHECKPOINT`.
- **Gate discipline**: `verify_all --standard` (runs `tests/unit/` only), parse for `verify_all (standard): ALL PASS`, push as a SEPARATE command, never red. New endpoints trip 4 guardrail baselines (ui_wiring/endpoint_coverage_matrix/endpoint_usage/undo_coverage) + need openapi regen. New test files can trip check_test_assertions vacuous-detector (allowlist helper-delegating tests in scripts/check_test_assertions.py).

## ICANH demo — transcription UNBLOCKED + working (2026-06-13 ~12:05)
Library `~/Documents/Fichero-Libraries/ICANH-Andagoya.fichero` — 15 PDFs (files/fi/, 114 page-records).
- **#2188 FIXED + shipped (812d3819):** transcription artifacts were silently discarded — `save_artifact`'s doc-lookup + `vision_base` `path_to_doc` matched `file_path` against `Document.path`, but #2183 made files_tool emit ABSOLUTE paths while Document.path is library-relative (`files/fi/...`). New `_doc_lookup` helper (`find_document_by_path` + `resolve_path_to_doc`) normalizes absolute↔relative on both the DB query and the path map. verify_all --standard 4779 passed. **Verified on real data:** doc 18590129.pdf → 4 pages transcribed + PERSISTED.
- **Apple Vision NOT reachable from presets (#2189):** all Transcribe presets node-pin `openai/gpt-4o-mini`, overriding the configured `vision_provider=apple`. "Point vision at apple" needs a per-node provider edit (or the preset should honour the vision slot). Base Transcribe + Paleography both ran gpt-4o-mini.
- **Quality on 1850s Spanish *cortesana* cursive (gpt-4o-mini):** flawed-but-readable. Base Transcribe garbles numerals/abbrevs ("inuenra"→noventa, "Xrito"→Cristo). **"Transcribe Paleography" has a much better prompt** (emits hand/script metadata + `[bracketed-uncertain]` readings) — clearly the best wired option — but the preset FAILS at its downstream `reference-search` node (#2190; transcription still saved).
- **Recommendation for Daniel:** for this corpus the quality ladder is qwen2.5-VL / HTR > gpt-4o-mini(+paleography prompt) > Apple Vision OCR (printed-text engine, weak on cursive). To actually eval qwen2.5-VL via OpenRouter (key present), the Transcribe node's pinned provider/model must be changed — best done in-app with the node editor (UI provider picker + rendered-page review). #2189 would make this a Settings-level switch.

## Roadmap after this
Backend is rock-solid (Daniel's gate before Mac). Remaining backend: drain more Test Coverage (Swift UI gaps SKIP), triage #2187 integration rot, #2157/#2158 LAN transport. Then per Daniel: Mac (#2081 node model) → iOS → intelligence/node-editing.

`entitytable-2020` worktree (#2020 entity provenance Table) is Daniel's held lane — left intact.
