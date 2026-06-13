# STATE — handoff 2026-06-13 ~15:30 ADT (AUTONOMOUS BACKEND — Daniel out, Mac work deferred to tomorrow WITH him)

Branch `0.0.2` @ `be8c74f5`, pushed clean. Engine running on main tree with `--reload --reload-dir fichero-engine/src` → backend edits in WORKTREES only; integrate via cherry-pick of atomic commits; gate; never push red.

## ▶▶ NEW DIRECTION (Daniel, 2026-06-13 PM) — this supersedes the four-lane order below
**Daniel's lane = backend, autonomous, looped. Mac App Shell is DEFERRED to tomorrow when Daniel drives it — do NOT touch Mac/SwiftUI autonomously.**
My scope: **AI Infrastructure (milestone #83) + security + speed/efficiency + the model-comparison system.** Goals in Daniel's words: *good results AND cheap to run*; comparison working; **no cloud leaks**; **fallback clear & transparent**. Best practices: Pydantic, typed APIRouter endpoints, no hand-rolled endpoints, tests for everything. Use **codex workers** (not me hand-coding) + **Fable/Opus reviews**; make GOOD issues in the milestone, then work them with workers; use ICANH + the comparison endpoint to TEST results. Loop until the milestone is drained, then idle for the Mac session.

### Done this session (pushed clean)
- **compare-vision coroutine bug FIXED + pushed (`ae8d554a`)**: `_run_vision_model` wrapped async `vision()` in `asyncio.to_thread` → every model returned "object of type 'coroutine' has no len()". Now awaits directly + regression test. The `/api/model-comparison/compare-vision` endpoint is LIVE (smoke: gpt-4o-mini 16s/$0.0003). This is the bake-off / good-vs-cheap evaluation tool.
- **AI-infra architecture review (frontier agent) DONE** → `docs/architecture/ai_infrastructure.md` (on disk, UNCOMMITTED — Fable is appending to it; commit once Fable returns). Filed + milestoned (#83): **#2191** (cloud-leak: `chat_with_fallback` → paid cloud, no consent gate — HIGH), **#2192** (no global local-only perimeter), **#2193** (cloud embedding default ungated), **#2194** (no embedding model/pooling pin → silent search corruption).
- **Filed #2195** (AI-Infra): model-comparison CLI verbs + compare-a-transcribe/translate-WORKFLOW-across-models + estimate_cost coverage.

### SHIPPED (loop tick 1, all gated ALL PASS + pushed, never red) — 0.0.2 @ b629dfa0
- **#2195** (1acd1c74) comparison CLI (`fichero compare vision/models/tool/workflow`) + new typed `POST /compare-workflow` route + compare_workflow engine method + estimate_cost coverage + openapi regen + 4 new-endpoint guardrail baselines registered (CLI-only; UI=#1753/#1739).
- **#2189** (8c88b77c) transcribe presets honor configured vision provider (node workflows skip the generic backfill; pins dropped).
- **#2191 + #2192** (b629dfa0) symmetric paid-fallback consent gate on `chat_with_fallback` + `is_local_only()` perimeter at the model-access choke points — no silent cloud leak. Settings/UI exposure deferred to Mac session.
- Fable review done → ai_infrastructure.md has Efficiency + AI-test (T1–T12) plans; #2055 reopened, #2193/#2194 confirmed.

### SHIPPED (loop tick 2a, all gated ALL PASS + pushed, never red) — 0.0.2 @ 5e734aca
- **#2055 + #2062** (5e734aca) cached `get_langchain_model` remote LangChain clients + bounded in-flight chat/vision concurrency. Worker targeted checks passed; manager gate `bash scripts/verify_all.sh --standard` passed with `verify_all (standard): ALL PASS` (`4806 passed, 28 skipped, 21 xfailed, 1 xpassed`). Issues closed; `llm-efficiency` worktree/window removed.

### SHIPPED (loop tick 2b, all gated ALL PASS + pushed, never red) — 0.0.2 @ fc349b39
- **#2057** (fc349b39) added thin `chat_batch` / `vision_batch` wrappers over LangChain `.abatch()` with ordered per-item `LLMBatchItemError` results, `FICHERO_MAX_INFLIGHT_LLM` chunking, Apple bounded-gather fallback, and usage accounting. Worker targeted checks passed; manager gate `bash scripts/verify_all.sh --standard` passed with `verify_all (standard): ALL PASS` (`4811 passed, 28 skipped, 21 xfailed, 1 xpassed`). Issue closed; `batching-2057` worktree/window removed.

### SHIPPED (loop tick 2c, all gated ALL PASS + pushed, never red) — 0.0.2 @ be8c74f5
- **#2194 + #2193** (2c4d901a + be8c74f5) pinned current FastEmbed embedding space (`intfloat/multilingual-e5-large`, explicit mean pooling), stamped `embedding_model_id` on new Lance rows, added known mixed-space refusal with legacy unstamped warning, and gated `llm_embeddings.embed/aembed` behind local-only + paid-fallback policy. Initial worker targeted tests missed FastEmbed's typed `DenseModelDescription`/`ModelSource` contract; full gate failed; repair commit switched from dict-returning `list_supported_models()` to typed `_list_supported_models()` and added cache-isolation test coverage. Manager gate then passed: `bash scripts/verify_all.sh --standard` → `verify_all (standard): ALL PASS` (`4818 passed, 28 skipped, 21 xfailed, 1 xpassed`). Issues closed; `embeddings-pin` worktree/window removed. No real data was re-embedded.

### In flight (poll on wake) — tick 3
- None currently active. Next: dispatch programmatic guardrail for typed AI/model metadata, then continue #938 / AI-test gaps / design-doc lanes.

### Next waves (dispatch as lanes free up — all codex workers, disjoint file-sets)
1. **AI-backend tests** worker — implement Fable's test-gap checklist (workers write tests, manager runs full suite). Ties to #1987.
2. **Cloud-leak + transparent fallback**: **#2191** (symmetric paid-fallback consent gate on `chat_with_fallback`), **#2192** (global `is_local_only()` perimeter), **#2193** (gate cloud embedding default). llm.py — one worker, FULL suite (god-ish file).
3. **Embeddings**: **#2194/#2117/#2049** (pin bge-m3 model + pooling + stamp model-id on vectors). *Manager runs any re-embed deliberately — never a worker; do NOT re-embed real Marshall/ICANH data.*
4. **Efficiency**: **#2057** (.abatch fan-out), **#2055** (client/model reuse), **#2062** (bounded concurrency) per Fable's ranked wins.
5. **Multi-step transcribe**: **#938** (Transcribe multi-pass: small→large→combine) = the ICANH "Spanish Script (19th–20th c.)" preset. Needs my vision-judgment on prompts — I lead with a worker on plumbing. **#2190** (Paleography reference-search fails).
6. **MLX on-device** (#1814/#2066/#2071 Pi harness on mlx-lm-server) + **in-app Agent** (#2067 + #2068–#2074) — bigger/design-led; scaffold via a design-doc lane first.

### ICANH ground truth (my vision, for scoring bake-offs)
Doc `18590129.pdf` (`files/fi/aa82ab20_fichero_upload_ouazq1uq.pdf`), an 1859 Nóvita (Chocó) notarial deed: opening is **"En la ciudad de Nóvita a veintiuno de Enero del año de mil ochocientos cincuenta i nueve"**, notary **Adolfo Hurtado**, parties **Juan Catarino Ayrilla** + **Eduvijes Ibárgüen**, creditor **Pompeyo Guzmán**, sum **400 pesos fuertes = 250 castellanos de oro en polvo**. gpt-4o-mini HALLUCINATES the opening ("Con la utilidad de Xrito") + garbles all numbers → weak baseline. Score candidates vs this.

### HARD rules in force (unchanged)
codex workers in worktrees ONLY (`~/code/fichero-worktrees/`); never edit main-tree `fichero-engine/src` live; cherry-pick atomic commits; `verify_all --standard` gate (full suite for new endpoints/god-nodes/DB); never push red; migrations CHECKPOINT after ALTER; keep `0.0.2 == origin`. Don't touch worktrees `entitytable-2020` / `lan-tls-2157` (#2157 HELD). Never run xcodebuild test / verify_all --full (GUI).

## Resume prompt (paste after compact)
```
/loop Autonomous BACKEND manager — Daniel out, Mac work deferred to him tomorrow. Read STATE.md top block FIRST. Scope = AI Infrastructure (#83) + security + efficiency + the model-comparison system; goals = good-and-cheap, no cloud leaks, transparent fallback; best practices (Pydantic, typed endpoints, tests). Drive codex workers (not hand-coding) + Fable reviews. POLL: codex worktrees vision-provider-2189 (#2189) + compare-cli-2195 (#2195) for commits → integrate via cherry-pick + gate (FULL suite for #2195's new endpoint + openapi regen) → push (never red) → close issue. Fable fable-ai-efficiency returns a test-gap checklist + efficiency findings → dispatch a tests worker + #2191/#2192/#2193 cloud-leak worker (llm.py, full suite) + #2194 embeddings. Then #2057/#2055/#2062 efficiency, #938 multi-step transcribe (ICANH "Spanish Script 19th-20th c." — I lead prompts, score vs the ground truth in STATE), MLX #1814/#2066 + in-app agent #2067 (design-doc lane). Commit ai_infrastructure.md once Fable finishes. Do NOT touch Mac/SwiftUI, entitytable-2020, lan-tls-2157. Keep 0.0.2==origin.
```

---

# STATE — handoff 2026-06-13 ~14:50 ADT (Daniel at a party — run AUTONOMOUSLY)

Branch `0.0.2` @ `82c284d5`, pushed clean (local == origin). Daniel runs the engine himself
(`uvicorn --reload --reload-dir fichero-engine/src`) → **all backend edits in WORKTREES**, integrate as atomic commits, gate, never push red.

## ▶▶ AUTONOMOUS WORK ORDER — run until Daniel returns (this is the source of truth post-compact)

**Lane 1 — ICANH transcription bake-off (I LEAD; needs Opus vision-judgment).**
Library `~/Documents/Fichero-Libraries/ICANH-Andagoya.fichero` (15 PDFs, 19th-c Spanish notarial *cortesana* cursive). #2188 (save fix) shipped → transcription persists. Providers: OpenAI (gpt-4o / gpt-4o-mini), OpenRouter (qwen2.5-VL etc.), Apple Intelligence/Vision. Engine token: `~/Library/Application Support/Fichero/.api-key`. CLI: `PYTHONPATH=fichero-engine/src .venv/bin/python -m fichero --library <lib> <cmd>`. First PDF doc id `8c308569b2034510833f33598394ae8a` (18590129.pdf); page-1 doc `97817dc528e048a299d64785aaeaa5e9`.
DO: (a) **Read the actual PDF pages with my own vision** (Read tool supports PDF `pages=`) to get ground truth. (b) **Bake-off** one hard page across providers — Apple Vision OCR, gpt-4o, qwen2.5-VL — AND research+try **specialized HTR models** (handwritten-text-recognition, e.g. TrOCR/HTR endpoints, Transkribus-style) + other strong VLMs via OpenRouter (Qwen2.5-VL-72B, Gemini-2.x); score each vs what I read. (c) Build a **MULTI-STEP setup as a NEW workflow/preset** (e.g. vision-LLM transcribe → script-aware cleanup/refine; maybe a multi-step *script*). **IMPORTANT: this corpus is 19th–20th-century Spanish _script handwriting_, NOT 16th–17th-c Spanish paleography** — frame the new preset as "Spanish Script (19th–20th c.)", borrowing *technique* from Paleography but with era-appropriate prompts/conventions (modern-ish secretarial cursive, not early-modern abbreviations). (d) Fix **#2189** (Transcribe presets pin gpt-4o-mini, ignore configured vision provider) + **#2190** (Paleography fails at reference-search). (e) Update the Transcribe workflow/preset to the winner; re-run all 15 PDFs; then NER→SVO→catalogue. To force a model: edit the Transcribe node's provider/model (or the vision slot once #2189 makes presets honor it). Workflow defs live in the library DB; fetch via `curl -H "Authorization: Bearer $(cat ~/Library/Application\ Support/Fichero/.api-key)" "http://127.0.0.1:8765/api/workflows/<id>"`.

**Lane 2 — Fable/Opus AI-Infrastructure architecture review (opens the NEXT milestone).**
AI Infrastructure (EPIC **#2056**) is the next lane, design-led. Produce `docs/architecture/ai_infrastructure.md` + a sequenced build plan; file concrete bugs. Cover: ONE model-access layer (all providers in one place — OpenAI/OpenRouter/Apple/local-MLX) [#2059 Apple-vs-AI skills]; reuse/batching/concurrency + **cloud-leak** audit [#2065]; embeddings vector-space consistency — bge-m3 wiring [#2117] + CLS→mean pooling pin/re-embed [#2049]; on-device **MLX** agent [#1814, #2066]; in-app **Agent** [#2067 — manager-with-workers in sidebar; ties to action registry #1848]. Dispatch as a background review agent (Opus or Fable-style adversarial) so it runs while ICANH proceeds.

**Lane 3 — autonomous backend cleanup (codex worktree workers, disjoint file-sets).**
Backend issues that do NOT need Daniel's design call: **#2001** (Observable guardrail: non-route db.save emit guard), **#2049** (embedding pooling pin — capability only; *I* run any re-embed deliberately, never a worker), **#1090** (undo/rollback for artifacts — fits action layer #1848). Full-suite gate for god-node/DB changes.

**Lane 4 — Mac App Shell (START AFTER the autonomous backend lanes are exhausted; review `docs/ROADMAP.md` first).**
The macOS chrome around all features: File/Edit/View/Window/Help menus, About panel, keyboard-shortcuts cheat sheet, first-run flow, app launch, window-state restoration, notifications/toast UI, progress indicators, Sparkle auto-update. Milestone **"Mac App Shell"** (28 open). Frontend = `claude` workers in worktrees; register new `.swift` via `ruby scripts/add-swift-file.rb`; gate = **swiftlint + compile-only build ONLY** (NEVER `xcodebuild test` / `verify_all --full` — launches Fichero GUI windows on Daniel's Mac even while he's away). Make self-contained `#Preview`s (mock data) and use `RenderPreview` to visually verify static chrome. Pick a coherent slice from ROADMAP order; #1215-style View-menu work is a good early target.

**HELD for Daniel (do NOT autonomously resolve):** **#2157** (security-model call — its comment has the #2157-spec-vs-shipped-#2177-test conflict; recommend adopting #2157's tightening + updating the #2177 test), all multi-user/auth DESIGN (#2022, #1844, #969), on-device-agent design (#2066/#2059 `needs-design`). Do NOT touch worktrees `entitytable-2020` (his held lane) or `lan-tls-2157` (#2157 held @ f0e305f0).

## Resume prompt (paste after compact)
```
/loop Autonomous manager — Daniel's out; work the ▶▶ AUTONOMOUS WORK ORDER at the top of STATE.md until he returns. Read STATE.md FIRST (source of truth post-compact). Lane 1 (I LEAD, needs my vision-judgment): ICANH bake-off — read the PDF pages with my own vision, bake-off Apple Vision / gpt-4o / qwen2.5-VL + research+try specialized HTR models, score vs ground truth, build a NEW multi-step "Spanish Script (19th–20th c.)" preset (NOT paleography), fix #2189/#2190, run all 15 PDFs → NER→SVO→catalogue. Lane 2: dispatch a Fable/Opus AI-Infrastructure review (EPIC #2056) → docs/architecture/ai_infrastructure.md + build plan + filed bugs. Lane 3: codex worktree workers on #2001/#2049/#1090. Lane 4 (after backend exhausted): review docs/ROADMAP.md → Mac App Shell milestone via claude frontend workers (swiftlint + compile-only, NEVER xcodebuild test). HELD: #2157, multi-user/auth design (#2022/#1844/#969), on-device-agent design (#2066/#2059); don't touch entitytable-2020 / lan-tls-2157 worktrees. RULES: backend edits in WORKTREES only (he runs --reload on main); gate verify_all --standard, full suite for new endpoints/god-nodes/DB; never push red; migrations CHECKPOINT after ALTER; keep 0.0.2 == origin; integrate worker commits via cherry-pick after verifying.
```

## Done earlier today (all pushed clean, never red)
- **#2188** transcribe-save regression fixed (`_doc_lookup` helper) — verified on real ICANH data, closed.
- **#2187** integration-test rot repaired (pure test rot, no product bugs), closed.
- ICANH judged → **#2189** (presets ignore vision provider) + **#2190** (Paleography reference-search) filed.
- **#2157** LAN-TLS built but HELD (branch `feat/lan-tls-listener-2157` @ f0e305f0; gate caught the #2177 auth-contract conflict).

---

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
