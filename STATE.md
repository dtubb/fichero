# STATE.md — Fichero

## 2026-05-28 ~16:30 — OVERNIGHT RUNBOOK (Daniel away; full autonomy; prefer Codex; 30-min ticks)

**Daniel's overnight goals:** (1) integrate all lane work into 0.0.2; (2) **enable ALL feature-gated features in the UI** (Research, Mind Palace, +) so he can see/test them → promote dev→release tier + fix the NodeDef→Input/Output Swift break (#1298); (3) audit backend features not surfaced in UI (#1288, gpt_mini running); (4) triage GitHub backlog (200 open) systematically newest→oldest: each issue ends done / completed / closed-wontfix; (5) prefer LOCAL models (oMLX) for fichero inference (won't run out); (6) gate everything: test + Xcode build + `sync_openapi_schema.sh` + design standards.

**OVERNIGHT END-GOAL (Daniel): everything WORKING for morning testing + actually GENERATE KG on his book chapters so he can explore it.**
- KG-GEN PLAN (do after integration + a working free/local extraction model): run the **Catalogue** workflow (extract_all node writes KnowledgeEntity+KnowledgeClaim — see [[project_catalogue_writes_kg]]) on his book docs. Candidate libraries on disk: `~/Documents/5 Fichero/CLI Preface+Ch1 Clean 20260523-063533.fichero` (book Preface+Ch1, English → Apple Intelligence works, FREE, no cap), `EAP1740 Paleography V7` (archival). GUARDRAILS: (1) confirm the LIVE/open library first (don't guess); (2) use a FREE model — Apple Intelligence for English, or oMLX local — NOT OpenRouter (weekly-capped → 403 spam) and NOT a paid fallback; (3) run a 1–2 doc subset, verify KG rows land (`fichero kg ...` needs FICHERO_LIBRARY_PATH header), THEN scale; (4) it's additive (appends KG), low risk. CLI: `PYTHONPATH=fichero-engine/src FICHERO_LIBRARY_PATH=<pkg> .venv/bin/fichero workflow run <id> <doc_or_folder> --wait`.
- BUG found: `GET /api/registry` (`fichero library list`) wrongly requires the X-Fichero-Library-Path header → can't list libraries without already knowing one. File + fix (backend, Codex).

**PRIORITY (Daniel 2026-05-28 ~16:40): INTEGRATE everything first → clear → THEN continue. Don't pile new tasks while commits sit unmerged. Tick every 15 min until the queue is integrated, then slow to 30+. Review `gh issue list` so dispatch targets are known.**
**Per-lane reconciliation notes:** gpt_mini's earlier KG-MCP commit is SUPERSEDED by opus's MCP (already in trunk) — SKIP/drop it on merge (cherry-pick #1278 + #1288 only, not the KG-MCP one). The 3 book-extractors (#1277 codex53 / #1278 gpt_mini / #1279 gpt) likely touch overlapping extractor files — expect conflicts, resolve by union. Merge each lane only when it's IDLE (committed, not mid-task).
**Dispatch-ready BACKEND issues (Codex, non-openapi where possible):** #1295 date-entity filter (gpt, in flt), #1239 remote-backend-SSH (gpt_mini, in flt), #1283 startup-403 (gpt, DONE 7f8e398d), #1301 MCP follow-ups, #1257/#1258-backend KG. Swift/UI issues (#1264/#1261/#1255/#1253/#1241) → Codex-writes + manager Xcode-gates, or defer to Sat.

**INTEGRATION ORDER (merge to 0.0.2, gate each, then forward-sync+clear that lane):**
1. **MCP reconciliation** (DECISION LOCKED): adopt opus `origin/opus` `04a764b8` `fichero_mp_*` (24 tools) as canonical; **revert my `ce89deb5` `fichero_palace_*`** first to avoid dup tools; skip gpt_mini's older KG-MCP commit (superseded). Then `git merge origin/opus`; gate `pytest test_mcp_server.py test_cli_client.py`. No openapi/Swift change.
2. **codex53**: #1277 citation-usage, #1258 claim-CRUD, **oMLX provider** (verify committed; touches openapi+Swift picker → regen + manager BuildProject).
3. **gpt**: #1279 book-structure, provider-quota-resilience, #1283 startup-403.
4. **gpt_mini**: #1278 book-index, #1288 audit (.md, just commit).
5. After ALL merged + green: **promote dev→release tier** as ONE openapi change + fix NodeDef Swift break + BuildProject; flip any frontend gates ON.
6. **Forward-sync** opus/haiku/sonnet/gpt/gpt_mini/codex53 → reset --hard origin/0.0.2 (ONLY after their work is merged). Clear session-ended lanes (opus/haiku/sonnet done per Daniel).
7. Re-dispatch Codex lanes (currently idle/paused) on next backlog issues.

**GATE CMDS:** ruff `~/code/fichero-0.0.2/.venv/bin/ruff check fichero-engine/src/`; pytest `PYTHONPATH=fichero-engine/src .venv/bin/python -m pytest fichero-engine/tests/unit/ -q` (known-red: dedup test); Swift `mcp__xcode__BuildProject(windowtab1)`; openapi `bash fichero-engine/scripts/sync_openapi_schema.sh` + commit. Never push main; never FicheroUITests.

---

## 2026-05-28 ~16:10 — INTEGRATION QUEUE + TIER-PROMOTION (resume here)

**Division of labor (Daniel):** Codex = implementation (uncapped, Pro); Claude manager = integration/merge/gate/review/Swift-build. Claude worker lanes (opus/sonnet/haiku) **session-ended by Daniel** — parked till Sat.

**Already in trunk (verified):** #1296 (`d65ae322`), sonnet Researcher + 4-bug fix (`15d08b17`/`724ce50c`), my `fichero_palace_*` MCP (`ce89deb5`), Mind Palace A1, oMLX-provider in flight.

**UNMERGED lane commits to integrate (gate: ruff + trunk-venv pytest; Swift⇒manager BuildProject):**
- `codex53`: #1277 citation-usage + #1258 claim-CRUD-backend + **oMLX-provider (in flight, bg becdx747w)**
- `gpt`: #1279 book-structure + provider-quota-resilience/`$large` configurable base
- `gpt_mini`: #1278 book-index + KG-MCP-read-tools
- `opus` (`04a764b8`): **MCP superset** (`fichero_mp_*` 21 CRUD + 3 KG reads). RECONCILE: adopt this as canonical; supersede/revert my `fichero_palace_*` + gpt_mini's KG-tools to avoid duplicate tools for the same endpoints.
- `haiku` (`5ed6082b`): "router promotion" checkpoint — inspect; feeds the tier directive below.

**NEW DIRECTIVE (Daniel, priority):** promote dev-tier (Mind Palace, Research, MCP, new extractors) → **RELEASE tier** so he can review in-app ("turn off later if it doesn't work"). REQUIRES fixing the **NodeDef→NodeDefInput/Output** Swift break that forced the #1298 revert (regen `sync_openapi_schema.sh` + fix `WorkflowServiceGenerated.swift`). Do as ONE openapi change **after oMLX merges** (never 2 concurrent openapi lanes). Code→Codex, Swift gate→manager.

**oMLX wired:** local OpenAI-compatible server at `http://127.0.0.1:8000/v1`, key `coCuQ…` (see [[reference_omlx_via_pi]]). Bug found: `lmstudio`/`ollama` discovery hardcodes `:1234` (provider_models.py:456) — codex53's oMLX task fixes discovery to be base-aware. Daniel wants a first-class **oMLX** entry in the provider picker (#1300 has onboarding ideas too).

---

## 2026-05-28 LATE-MORNING — HANDOFF (where we are; resume here)

**Trunk `0.0.2` @ `ce89deb5`, all gates green, pushed.** Worked independently ~7:45am→noon May 28. Researcher + #1296 brought in & fixed; Mind Palace MCP shipped.

**SHIPPED this morning (gate-verified, in trunk, pushed):**
- **Researcher** (cherry-picked sonnet's 4 commits — branch was based pre-Mind-Palace, so cherry-pick not merge; see [[feedback_agent_worktree_base]]). Build gate caught 6 integration gaps (pbxproj union, `@ViewBuilder` early-return, `.research` exhaustive cases, `.inProgress` enum) → `15d08b17`.
- **Researcher 4 runtime bugs** the FE↔BE review found (raw APIClient = runtime, not compile, failures): GET `/projects/{id}/tasks` 404 (added project-level tasks aggregation route), POST notes path 404 (fixed Swift path → `/notes`), `library_destination_folder_id` dropped on create+update (added to request models + handlers). Direct-handler regression tests (routes are dev-tier gated out of TestClient). → `724ce50c`.
- **#1296** haiku KG keyword-claim entity_ids test → `d65ae322`.
- **Mind Palace MCP tools (#1269 slice)** — 7 `FicheroClient.palace_*` + `@mcp.tool()` (rooms, scene, place/move/connect/arrange/focus) so the AI can drive the palace. MockTransport tests. → `ce89deb5`.
- **Mind Palace FE↔BE wiring reviewed CLEAN** (generated typed client, no changes needed).

**RESUME — next contained work, in priority order:**
1. **#1299 visual verification** — add self-contained mock-data `#Preview` to new Researcher/Mind-Palace views so `mcp__xcode__RenderPreview` can snapshot them (Daniel wants to "look at pictures"). Watch the @EnvironmentObject-timeout gotcha — inject a mock service.
2. **#1269 remainder** (large, needs Opus/Codex frontier): the *agentic chatbot* + full-app MCP surface beyond Mind Palace. The thin FastMCP server (`mcp_server.py`) is the place to extend (one tool per real client method — NOT the removed `fichero_mp_*` fantasy surface, see acd349a2).
3. Researcher INFO-level polish: web-search response drops `source_name`/`published_date`/`relevance_score` (wire when UI needs them).

**LANES (reconfigured 2026-05-28 ~12:35):** Daniel bought **Codex Pro** → Codex UNCAPPED (live-verified: codex53 replied READY). **Claude worker lanes PARKED until Saturday (May 30)** per Daniel — do NOT dispatch to opus/sonnet/haiku/planner/integrator/reviewer/bugtriage; they sit idle (zero cost); autoloop already terminated. Manager (this session) keeps coordinating Codex + gates/merges their backend work.
- **DISPATCHED to Codex (backend-only, dev-tier, no openapi/Swift — Claude can't gate Swift while parked):** codex53→**#1277** (in-text citation USAGE extraction), gpt→**#1279** (book STRUCTURE chapters/sections), gpt_mini→**#1278** (back-of-book index→topic entities). All three confirmed Working. They commit to their lane branch, do NOT push/PR; manager gates (ruff + trunk-venv pytest) + merges.
- **STILL QUEUED:** #1258 KG-claim CRUD (has a Swift UI part — defer the UI until Claude lanes return Saturday; Codex can do backend CRUD if a lane frees up).
- **Gate Codex work via trunk venv (lanes have no .venv):** `/Users/danieltubb/code/fichero-0.0.2/.venv/bin/ruff check ~/code/fichero-<lane>/fichero-engine/src/` and `PYTHONPATH=~/code/fichero-<lane>/fichero-engine/src .venv/bin/python -m pytest ~/code/fichero-<lane>/fichero-engine/tests/unit/ -q`.

**HELD:** #1298 S0 core-tier promotion reverted (regen splits NodeDef→Input/Output, breaks WorkflowServiceGenerated.swift; tag `s0-core-promotion`=bc8c6e75; NOT needed for dev-tier testing). XCUITest #1230/#1242 BLOCKED on Daniel's one-time macOS TCC grant (Accessibility+Automation).

**RULES:** never push main; tests/gates in this trunk worktree; independently re-run gates ([[feedback_independently_verify_lane_test_claims]]); never FicheroUITests (TCC hang); any openapi/schema/router-tier change ⇒ trunk Swift BuildProject; cross-feature merges that extend an enum ⇒ Swift build is the real gate (catches non-exhaustive switches a pytest-only gate misses); don't pollute :8765 (Daniel's live backend); verify GH issue # before closing; Codex caps ⇒ queue, not Claude-pile; conserve context + usage.

---

## 2026-05-27 ~10:45 — CONSOLIDATED (everything merged into 0.0.2)

**All lane work is merged into `0.0.2` (`c51054cf`) and all 6 worktrees forward-synced to it.** Trunk Swift build green; full Python verify run as the final gate (~3200 tests). HISTORY.md has the full landing list.

**Merged today (overnight + morning):** all 0.0.2 reading-surface bugs; KG spine (#1248/#1249/#1254) + page-order #1271; backend #1252/#1251/#1237/#1260; chat #1262 / export #472 / large-PDF #1273 / image-only-OCR #1274 / researcher #1256 / image ops #462-#468 / notes #1259; **KG evidential model #1266** (+ cross-doc claim regression fix); **KG editor #1135**; **rich search #1270**; **KG timeline+map #1267**; **color-code #1052**; **annotations #1276** + image-editing UI #469/#1265; **model-comparison backend #1268**; **slipbox import CLI #1231**; **#1275 OpenAPI determinism fix** (NodeDef/EdgeDef pinned — ends per-merge Swift-build breaks).

**LANES:** all idle + synced to `c51054cf` (sonnet/opus/haiku/gpt/gpt-mini). **codex53 = Codex usage-capped (resets ~12:25pm)** — endpoint↔frontend coverage audit is its parked task. Next: when tokens/Ollama are set up + Codex resets, sync 0.0.2 → workers and dispatch new tasks.

**HELD / pending:** endpoint-enable audit (codex53, capped); maps/archivo-afro import #1232 (needs real `~/code/maps` path); #1230 UITests (one-time macOS TCC grant); big architectural features — MCP+chatbot #1269, GraphRAG wiring, model-comparison UI — reserved for Opus/Codex frontier once API tokens + Ollama tier are live. Planner backlog filed: #1277/#1278/#1279.

**MODEL POLICY:** reserve Opus + Codex-GPT for big/architectural work; route bulk (audit/import/tweaks/tests/triage) to Ollama open-source (runs inside the codex/claude CLIs). If Codex/Claude caps, STOP and ask Daniel. openapi-touching merge ⇒ trunk Swift BuildProject (NodeDef now deterministic via #1275). Never run FicheroUITests (TCC). Never push main.

---

## 2026-05-27 MORNING — earlier handoff (superseded by CONSOLIDATED above)

**Role:** f_manager, branch `0.0.2`, `~/code/fichero-0.0.2`. Daniel active, goes to office ~11am.

**REGIME (Daniel's current rules):** PREFER CODEX for new work; conserve Claude (was 77% weekly, resets May 30) AND manager context. **If Codex caps, STOP and ask Daniel — do NOT fall back onto Claude.** Don't stop lanes mid-path; ensure they keep updating. Session-end + forward-sync each lane to trunk before retasking. Delegate heavy merges to f_integrator. Merge gate: backend ⇒ ruff+pytest; **any openapi change ⇒ trunk Swift `BuildProject(windowtab1)`; if NodeDef drops, re-run `sync_openapi_schema.sh` (flaky emission, #1275)**. NEVER run FicheroUITests (hangs on TCC, #1230 held). Never push main.

**MERGED to 0.0.2 overnight+morning (trunk green, verify 3204+ pass):** all 0.0.2 reading-surface bugs; KG spine (#1248/#1249/#1254); page-order #1271; backend #1252/#1251/#1237; text-reflow #1260; chat-compare #1262; export #472; large-PDF #1273; image-only OCR #1274; researcher #1256; image ops #462-#468; per-doc notes #1259; **KG evidential model #1266** (+ regression fix: persist claims from all docs on dedupe); **in-app KG editor #1135**; **rich search anchors #1270**; **KG timeline+map #1267**; **color-code entities #1052**. Filed #1275 (flaky NodeDef openapi).

**IN FLIGHT (~11am deadline = annotations):**
- `sonnet` (Claude): **#1276 annotations BACKEND** — Annotation model (doc+page_index+bbox+note+color+tag) + CRUD `/api/annotations` + 18 tests + openapi regen + `annotations_source` workflow tool. Done/wrapping (commits 0c59ab6a/73248862/201e9356). MERGE FIRST (gated).
- `opus` (Claude): **#1276 annotations SWIFT UI** on its branch on top of image-editing **#469/#1265** (AnnotationService + DocumentAnnotation + Annotations inspector tab + annotate-region-from-marquee; ~7 commits). MERGE AFTER backend → brings image UI + annotations together → close #469/#1265/#1276.
- `gpt-mini` (Codex, lighter model): **#1231 slipbox CLI import** (~/code/slipbox + ~/code/slipbox-tinderbox .tbx → new catalogue; 2 commits) — may cap soon; relay its survey (does integrations/sync need enabling?); don't merge till it reports done.
- `f_planner` (Claude): shaping 3 book-extraction ideas → issues + `agent-work/proposals/2026-05-27-book-structure-extraction.md` (in-text citation-usage; back-of-book index→topic entities; chapter/section structure).

**HELD / BLOCKED:**
- `gpt` #1268 model-comparison backend — DONE on gpt branch, **merge after annotations** (gated, openapi).
- `codex53` endpoint↔frontend coverage audit (→ `agent-work/proposals/2026-05-27-endpoint-frontend-coverage.md`) — BLOCKED, Codex capped, resets **12:25 PM**.
- `~/code/maps` import (#1232) — path missing, deferred pending Daniel.
- #1230 UITests — needs Daniel's one-time macOS TCC automation grant.

**NEXT after annotations:** merge #1268; when Codex resets 12:25 re-task codex53 (audit) + gpt-mini (slipbox/maps). Daniel strategy: "get it all up, then test + bugfix" — the endpoint audit feeds enabling backend-only features in the frontend (#1151/#1072). Feature backlog: #1266/#1267 done; remaining KG/feature ideas #1268(merge)/#1269 MCP+chatbot/#1187 notes/#1124 hermeneutics + the 3 planner issues.

---

## 2026-05-26 EVENING — OVERNIGHT AUTONOMOUS HANDOFF (superseded by the morning block above)

**Role:** f_manager, branch `0.0.2`, `~/code/fichero-0.0.2`. Daniel is out for the night, checks via phone (GitHub). Full-steam autonomous; 0.0.3 features are in-scope.

**REGIME — PACE FOR ~12 HOURS, DON'T SPRINT (Daniel's governing rule).** Both Claude AND OpenAI/Codex will run out of funds if hammered — steady all-night progress beats burning everything in 2 hours. THROTTLE: keep only ~2-3 lanes active at once (rotate), let lanes idle between tasks, refeed sparingly, use LONG ~60-min tick intervals. Claude quota was tight (92%→~61%); slightly prefer Codex but don't blast it either. Claude lanes sometimes show a spurious **"Upgrade your plan"** dialog (NOT real exhaustion) — reset with `1` then `continue`. Conserve manager context: light ticks, offload to lanes/subagents, read verdicts not logs. Re-pause lanes if any provider's quota climbs toward ~90%.

**✅ MERGED TO 0.0.2 OVERNIGHT (as of ~21:00, 2026-05-26 — supersedes the "NONE merged" note below):**
- `18c34f46` KG spine — #1248 two-stage KG write + #1254/#1263 guardrail fallback + #1249 page-child claims (closed)
- `6ca8ce7e` sonnet backend — #1252 RTF strip + #1251 progress logging + #1237 xlsx import (closed)
- `8201cffe` docs — PDF fidelity audit + KG evidential-model design
- `8ccdb9e4` #1271 whole-PDF page-order fix (the "weird text" root cause — closed)
- `8a8db2d8` #1272 KG silent-failure fix (optional `_EntitiesOnly` grammar fields → Apple returned `{}` → Stage 2 skipped silently; now required + fail-loud — closed)
- `2db78819` #1260 text reflow/cleanup tool (closed)

**STILL OPEN / WATCHING:** #1272 fix is merged but an **end-to-end KG-populates-on-real-PDF confirmation** (salas2015 via f_backend trunk engine) is still pending — the fix removes the silent-empty path but a real run should confirm entities now appear. PDF audit also filed #1273 (443pp stalls engine) + #1274 (image-only PDF no OCR). New feature issues from Daniel tonight: #1266/#1267 (KG temporal+spatial+ranges+provenance), #1268 (model-comparison UI abstract+per-node), #1269 (MCP + agentic chatbot), #1270 (rich search results). gpt's KG evidential-model design → `agent-work/proposals/2026-05-26-kg-evidential-model.md`.

**CAPACITY:** Codex (OpenAI) hit its usage cap ~8pm, recovers ~21:43 — one-shot cron `5538969a` at 22:02 re-tasks the 3 Codex lanes (codex53→#466 enhance, gpt→#1273, gpt-mini→#1274). Claude lanes carried the night meanwhile.

**LANES** (worktrees `~/code/fichero-<name>`, each commits to its own branch, manager/integrator merges):
- `f_sonnet` (Claude): all 6 KG/backend items MERGED; then #1271 + #1272 MERGED. Idle — next: confirm #1272 end-to-end, or #1250 (catalogue-stall, likely already fixed by KG spine).
- `f_opus` (Claude, Xcode): #1247/#1245 committed (unmerged, Swift — needs three-leg tick); now working reading-surface cluster #1243 (`deae1172` done) → #1244 → #1246. Branch carries held #1230 UITest — keep #1230 OPEN.
- `f_haiku` (Claude): #1260 MERGED. Idle.
- Codex lanes: see CAPACITY above.
- `f_sonnet` (Claude, branch sonnet): KG-spine COMMITTED — #1248 `92dd9635`, #1254+#1263 `2c40907b`, #1249 `6dd058ae`. Now: #1252 (RTF strip) → #1251 (progress) → validate Catalogue+Apple → #1237 (XLSX).
- `f_opus` (Claude, branch opus, OWNS Xcode): #1247 `4a4ad3cd`, #1245 `d9ec347d` committed (branch also carries held #1230 `4297740c`). Now: #1243 → #1244 → #1246 → #1253 → #1230 debug.
- `f_haiku` (Claude, branch haiku): #1260 `1a17cb8f` committed; extending #1260 (AI hook + tests) in its own module only.
- `f_codex53` (OpenAI, branch codex53): #1259 `1477b1e7` committed; now #462/#463 image-editing foundation (uncommitted WIP).
- `f_gpt` (OpenAI, branch gpt): #1262 `22dac9b3` committed; now #472/#473 export (uncommitted WIP).
- `f_gpt_mini` (OpenAI, branch gpt-mini): #1256 audit `bb00a461` + phase-1 WIP; REASSIGNED to **CLI end-to-end KG validation** — start engine from sonnet code on `:8799` + temp library, import→Catalogue(apple)→query KG, confirm #1248/#1254/#1249 work (don't disturb Daniel's `:8765`).
- Role lanes (Claude, reset from spurious dialog): `f_integrator` (merge gate), `f_reviewer` (review backlog), `f_planner` (image-epic decomposition → agent-work/proposals/). `f_bugtriage` idle.

**MERGE BACKLOG** (the per-lane queues just above this and the "NONE merged" framing are SUPERSEDED by the ✅ MERGED ledger near the top of this block). REMAINING to merge: **opus reading-surface** (#1247/#1245 + the #1243/#1244/#1246 cluster) — SWIFT, needs a dedicated three-leg tick (swiftlint + Xcode build + RunAllTests), carries the held #1230 UITest so keep #1230 OPEN. Codex image/export branches merge after each reports its task done. Pipeline: verify in the **0.0.2 trunk worktree** → `git merge --no-ff <branch>` + `git push origin 0.0.2` (NEVER main) → close issue. The 3-way merge of a lane branched from old trunk shows scary housekeeping noise in `git diff` but resolves clean (merge-base handles it) — always verify STATE.md handoff + proposal docs survive + stale root files stay deleted. Backend verify: `/Users/danieltubb/code/fichero-0.0.2/.venv/bin/pytest` with `PYTHONPATH=fichero-engine/src` (trunk has the .venv).

**HELD (need Daniel):** #1230 merge held on a one-time macOS TCC automation grant (run FicheroUITests scheme in Xcode + Allow, or pre-grant Xcode in Privacy&Security→Accessibility+Automation); imports #1231–#1239; #1239 SSH backend (not 0.0.2).

**FILED THIS SESSION (through ~#1265):** bugs #1243-1254 (reading-surface, KG pipeline, guardrail, RTF, progress, incremental save #1263); 0.0.3 features #1256 researcher / #1257 KG-viz-suite (+RealityKit stretch) / #1258 claim CRUD / #1259 notes / #1260 text reflow / #1262 chat+graphrag+model-comparison / #1264 activity window / #1265 image nav+rubber-band; image-editing epic = #462-#469/#1161/#1176/#928. Architect proposals for #1256/#1257/#1262 in `agent-work/proposals/`. KEY: backend already has researcher scaffolding, chat RAG, model-comparison — RE-ENABLE not rebuild.

**RULES:** never push main; authoritative tests in the 0.0.2 worktree; don't touch TCC; don't hardcode user-editable model/config; plan before non-trivial.

**NEXT:** loop every 30–45 min — refeed finished Codex lanes (preferred) disjoint work, let reviewer→integrator land the backlog (KG spine first), update GitHub issues as they close (Daniel's phone view), re-pause Claude if quota spikes.

---

## 2026-05-26 PM — Manager session (Daniel @ dentist, autonomous)

Engineering queue cleared except the last item. All merged + pushed to `origin/0.0.2`:
- **#1229** (`1e769aff`) inspector toggle polish (`sidebar.right`) + filterable/artifact-aware attribute strip (@AppStorage). Review APPROVE, three-leg green. Closed. Deferred Part 3 (selector unify) + window-corner toggle → **#1241**.
- **#1240** (`38cb2482`, #874 follow-up) entity-type registry wired into extraction runtime + provenance KnowledgeClaim. Review REQUEST CHANGES → all fixed (`ccb0e54e`). ruff clean; trunk backend suite 555-pass. Closed.
- **#874** registry endpoints already shipped (`c07474a3`); **#1054** search threshold already fixed (`37a1ceb7`) — both verified, not redone.

**In flight:** **#1230** (f_opus, branch `opus`, owns Xcode) — FicheroUITests target, scoped to **Option 2**: foundation + flow1 (launch/ClaimFocusState) + flow5 (view-mode rail) on empty library + accessibilityIdentifiers groundwork. Flows 2-4 (seeded backend + PDF fixture + library-override launch arg) split → **#1242**.

**Needs your decision (held, NOT run autonomously):** import cluster **#1231-#1239** — release-data/infra tied to your real corpora (slipbox, XLSX catalogues, ACENET-over-SSH). These need your data access + mapping/reconciliation decisions; #1239 needs a design pass. Ready to dispatch on your go-ahead.

Lane state: f_opus building #1230; f_sonnet idle/reserve (resynced to 38cb2482); haiku/codex53/gpt/gpt-mini idle reserve. No BLOCK.md anywhere.

## Snapshot

**Branch:** `0.0.2`

## Current Focus

Daniel testing 0.0.2. If passes, release checklist (#157–#165) in order.
Multi-agent split active: frontend Claude (#1202/#1204/#1181), backend Codex (#1054/#1173/#1198), pi CLI (imports).
SwiftLint file_length violations: **ALL CLEARED** (8 files split across 2 sessions). Build green. NodeDef schema variant fix committed.
Active pi work is in the shared `~/code/fichero-0.0.2` trunk checkout for this pass; the dedicated `~/code/fichero-pi` desk is not the live lane. Codex is paused.

**Reminder for 2026-05-25 23:30 ADT:** bring `f_claude_worker` and `f_codex_worker` back online together; both are currently out of context and need a fresh session start before any further coordination.

## Next Session — Start Here

1. Rehydrate `f_claude_worker` and `f_codex_worker` at 23:30 ADT before assigning more work.
2. Treat the shared `~/code/fichero-0.0.2` checkout as the live lane when checking the pi worker.
3. Re-run or inspect the backend gate only after the engine is in a clean single-writer state.
4. Pick up the WebKit knowledge pane issue `#1228` once the worker lanes are back in context.

**POST-INTEGRATION STATUS (2026-05-25 ~12:55p) — RESUME HERE (run manager on Sonnet 4.6 200k; Opus burns tokens).**
✅ BOTH lanes MERGED into trunk: pi (`231900db`: #1205 + #1085) and codex (`ffe2625b`: #1198, #1118 NER,
#1115 kg_writer, #1111 paragraph, #1206 test-iso, #1179, #1145, #1098). claude frontend (#1180 + 8 closed)
was already on trunk. Coordination-doc conflicts resolved to trunk's version (--ours).
Sonnet review + verify ran. **2 FIX-FORWARD items + 1 open bug remain — DO THESE FIRST on restart:**
1. ❌ `test_validate_simple_workflow` fails (workflow-validation regression from codex's new kg_writer/NER
   node types) — investigate `test_tool_registry.py::TestWorkflowValidation` + the new node defs; fix-forward.
2. ❌ OpenAPI schema drift — run `./fichero-engine/scripts/sync_openapi_schema.sh` + commit the regenerated
   `openapi.json`/`endpoints.json` (new `kg_render.py` route not in committed contract).
3. 🔴 **#1207 NER runaway still UNFIXED** (codex didn't guard it) — fix direction in the issue comment:
   cap items/section/page in `_write_kg_rows`, dedup by normalized name, validate count in `LLMNERProvider`.
THEN: re-run verify (green) → restart `:8765` (backend changed) → forward-sync lanes
(`git -C ~/code/fichero-codex merge 0.0.2`; same for pi) → clear worker contexts → start next run.
Also filed today: #1206 (codex FIXED it), #1207, #1208 (vision fallback). Backend `:8765` is RUNNING on
slightly-stale code (pre-merge) — restart after fix-forward.

--- (original consolidation plan, mostly executed) ---
Execute this sequence ON RESTART, COMMIT-BY-COMMIT, claude/pi lanes FIRST then codex (it worked most):

1. **Snapshot each lane**: `git log 0.0.2..pi`, `git log 0.0.2..codex`, and trunk `git log` (claude_worker
   committed frontend straight to trunk — e.g. #1180 `2dca41f0`; verify which landed). Check each lane
   worktree clean (`git -C ~/code/fichero-<lane> status`); note leftover AGENTS.md/CLAUDE.md/.bak dirt
   (uncommitted, do NOT merge).
2. **pi lane**: confirm #1205 fix (`head-30` → `head -30` in `sync_openapi_schema.sh`) landed → review
   commit with a code-review agent → `git merge --no-ff pi` into 0.0.2.
3. **codex lane**: confirm #1198 conftest fix (`_digest_library_database` in `dependency_overrides`)
   + any queue commits (#1118/#1115/#1111) → **code-review EACH commit** with an agent → `git merge --no-ff codex`.
4. **For each backend commit, decide if frontend SwiftUI needs a matching change** (e.g. #1198 digest
   route → Swift client/export UI). Go systematically, one commit at a time. File/assign as issues.
5. **Integration verify**: ONE serial `verify_python.sh` on trunk via test-runner subagent. Fix bugs.
6. **Forward-sync**: `git -C ~/code/fichero-codex merge 0.0.2` and same for `~/code/fichero-pi`. Clear
   their contexts. Restart `:8765` (backend changed).
7. **Then** start another independent run — ideally drive via ISSUES that claude_worker picks up,
   review-agents audit, pi_worker takes small disjoint tasks.

**Filed today (track these):** #1206 test-DB isolation · #1207 catalogue NER runaway-repeat (degenerate
loop, dedup+stop-cap) · #1208 tiered vision models (small→large fallback + fail-warn, not silent).
**Known infra gripes:** pi_worker kept going idle (thin agent:pi queue — give it disjoint small backend);
the `f_bugs_and_features` codex session blocks the /bug,/feature skills; **Opus context exhaustion is
the real blocker — run the manager on Sonnet 4.6 200k.**

**Testing division (confirmed with Daniel 2026-05-25):** workers write code + a single targeted
check only — they do NOT run `verify_python.sh`/full suite (separate worktrees + DuckDB single-writer
= concurrent runs DEADLOCK → false RED; filed **#1206** for per-run temp-DB isolation). The MANAGER
owns audit (review subagents) + the authoritative full verify, run SERIALLY at integration time.

**Earlier triage (8:13a):** labelled #1175→both/#1145→backend/#1146→frontend; verified-and-closed
#1147/#1148; filed #1205. **All 255 open issues now lane-labelled** (subagent): FE 87 / BE 115 /
both 53 — note this OVER-includes roadmap/legacy/release, so hand-feed in-scope bugs (don't trust raw
`label:frontend`). Frontend 0.0.2 priority bugs: #1180 #1032 #605 #721 #718 #717 #715 #702 #928 #958
#1048 #1045 #1044 #330.

## Agent split + worktree topology (2026-05-25)

Issues labelled `frontend` / `backend` / `both` / `agent:pi` on GitHub.

| Agent | Worktree / branch | Does | Filter |
|---|---|---|---|
| **Frontend Claude** | `~/code/fichero-0.0.2` / `0.0.2` (shared trunk) | SwiftUI: #1202, #1204, #1181, KG polish | `label:frontend` |
| **Manager Claude** (me) | `~/code/fichero-0.0.2` / `0.0.2` (shared trunk) | Coordinate, own :8765, review+merge lanes. No code. | n/a |
| **Backend Codex** | `~/code/fichero-codex` / `codex` (durable desk) | Python: #1173, #1054, #1198 | `label:backend` |
| **pi worker** | `~/code/fichero-pi` / `pi` (durable desk) | Simple code fixes (#1205 first) | `label:agent:pi` |

Durable desks named by agent (not milestone) → no `fichero-engine` source-dir name clash,
survive milestone bumps. `codex`/`pi` branches persist; retarget merges to the new trunk at
each milestone (0.0.2 → 0.0.3 …).
| **pi CLI** | no worktree → talks to :8765 | data ops / imports, no code | n/a |

**Manager protocol (survives memory-runout — also in auto-memory `multiagent-coordination`):**
1. Own `:8765` — ONE persistent backend on trunk code + real lib. Agents never bind :8765;
   they verify in-process (pytest/EngineHarness) or on :8766 + scratch lib.
2. Lane done → agent commits on its branch (`codex`/`pi`) + drops `.ai/inbox/done-<lane>-DATE.md`.
3. Manager: `git diff 0.0.2...<lane>` → review subagents (`code-reviewer` +
   `silent-failure-hunter`, +backend/contract for Python) + targeted tests →
   ALIGNED → `git merge --no-ff <lane>` into trunk (restart :8765 if backend changed);
   MISALIGNED → kick back via `.ai/inbox/review-<lane>-DATE.md`.
4. Resync: `git -C ~/code/fichero-<lane> merge 0.0.2` (disjoint files → no conflicts).
5. Frontend commits straight to trunk (un-gated, self-verifies 3-leg Swift check); ask it
   to commit before I integrate (shared working tree).

Full plan: `agent-work/proposals/four-agent-worktree-topology.md`.
Start sessions: frontend `/session-start-swiftui`, backend `/session-start-engine`,
manager `/session-start-manager`, pi CLI `/session-start-cli`, pi worker `/session-start-pi-worker`.

## Next Session — Start Here (MANAGER)

Infra is built; the job now is the gate + merges. On cold start:
0. **FIRST — check in on codex + pi worker** (left running autonomous queues at 2026-05-25 ~10:30a):
   capture their tmux panes (`tmux capture-pane -t f_codex_worker -p -S -15`, same for `f_pi_worker`)
   and check `~/code/fichero-codex/.ai/inbox/` + `~/code/fichero-pi/.ai/inbox/` for fresh `done-*.md`.
   - **codex** queue: push #1198 conftest fix (register `_digest_library_database` in
     `dependency_overrides`), then #1118 → #1115 → #1111 (KG/workflow lane).
   - **pi** queue: push #1205 fix (`head-30` → `head -30` in `sync_openapi_schema.sh`), then #1085
     (maps importer, ingest lane — disjoint from codex).
   - **claude_worker**: paused (frontend 0.0.2 largely clear); **pi_cli/pi_worker on `qwen/qwen3-coder`**.
   Then gate any lane that reports done (step 1). Relaunch the lane-inbox watcher
   (`find ~/code/fichero-{codex,pi}/.ai/inbox -name 'done-*.md'`, 30s poll, 10-min tick).
1. **Watch `.ai/inbox/`** for `done-<lane>-DATE.md` (codex/pi). For each: `git diff 0.0.2...<lane>`
   → review subagents (`code-reviewer` + `silent-failure-hunter`) → `git merge --no-ff <lane>` →
   **post-merge integration verify on trunk (test-runner subagent, SERIAL)** →
   restart `:8765` if backend changed → tell the lane to resync (`git merge 0.0.2`).
2. **You own `:8765`** (Daniel starts it). Agents never bind it.
3. **Bugs/features** filed via `/bug` `/feature` auto-label the lane (`frontend`/`backend`/`agent:pi`/`both`)
   so workers self-pick. Filed by you or a dedicated bug/feature session — not the workers.
4. **Verify-before-close** any "done" issue (strong fixed-but-not-closed pattern). pi's first task: **#1205**.
5. jcodemunch MCP is single-source at the pipx binary — see auto-memory `jcodemunch-mcp-single-source`
   if any lane's code-nav breaks (don't re-debug from scratch).
6. **Uncommitted in trunk** (left intentionally): `AGENTS.md`/`CLAUDE.md` + `.bak` are jcodemunch's
   `claude-md`/`init` policy injection — decide with Daniel whether to keep before committing.

## Completed this session (2026-05-25 morning)

- ✅ #1186 Navigation history — back/forward chevron buttons + Cmd+' / Cmd+Shift+' in OntologyBrowser
- ✅ OpenAPI freshness gate fixed — NodeDef-Input orphan schema removed from both contract files
- ✅ Chains router promoted to core tier (#1151) — Swift FeatureManager, OpenAPI re-synced
- ✅ Filed #1202 (biography text), #1203 (geo/temporal map), #1204 (click-to-sync)
- ✅ GitHub issues labelled frontend/backend/both
- ✅ 4 specialized session-start skills + .ai/inbox/ messaging infrastructure
- ✅ #1205 Delete dead generated Python CLI client + its regen step
- ✅ #1085 Maps importer: pair sidecar .iffy.json files with their image/PDF on ingest

## Completed overnight (2026-05-24 → 2026-05-25)

1. ✅ **Phase 1 — Dependabot liquidjs** — bumped to ≥ 10.25.7 via `overrides` in `site/package.json`.
2. ✅ **Phase 2 — SwiftLint** — zero warnings across all 334 Swift files (Codex, 6 commits).
3. ✅ **Phase 3 — #1201 OpenAPI freshness gate** — step 7 in `verify_python.sh`; gate implemented and issue closed.
4. ✅ **Phase 4 — KG entity library (#1183/#1191)** — `entity inspector` CLI command + `getEntityInspector()` Swift service method + `EntitySourceGroupsView` wired into `EntityDetailView`.

## Next Session — Start Here (frontend Claude)

**#928 PDF loupe — Tasks 1–6 complete. Task 7 = Daniel's manual test.**

**Queue Status (2026-05-25 ~8:00p):**
- ✅ **#928 PDF loupe** — Tasks 1–6 done; committed `11c118ab`
  - Toggle loupe button in PDFPageWithToolbar toolbar; loupe overlay renders on PDF
  - Lock/unlock, magnification slider wired; AppStorage syncs settings across views
  - Task 7 (manual test): Daniel opens PDF, toggles loupe, verifies cursor tracking + lock + magnification
- Pre-existing build errors (NodeDefOutput/NodeDefInput OpenAPI drift) still present — not introduced by loupe work

**On resume:**
1. Confirm Daniel tested Task 7 (manual loupe test on real PDF)
2. If #928 passes testing → close the issue
3. Next frontend priority: pick from `label:frontend` open issues (see list in State below)

## Next Session — Start Here (backend Claude / Codex)

```bash
gh issue list --label backend --state open --limit 20
```

Top priorities:
- **#1054** search relevance threshold — `fichero-engine/src/fichero/api/search.py`, add min-score filter
- **#1173** KG pronoun coreference — post-extraction resolver in `fichero-engine/src/fichero/kg/`
- **#1198** entity digest export (PDF/MD/text) — new endpoint + CLI command

## Known issues / gotchas

- `add-swift-file.rb` required a monkey-patch for xcodeproj 1.27.0 incompatibility with Xcode 16+ project format (Array shellScript value). The patch is in the script.
- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.

## Global rules

- Canonical gate: `bash scripts/verify_all.sh`
- Register every new `.swift` file with `ruby scripts/add-swift-file.rb fichero/fichero/Path/To/File.swift`
- GitHub Issues is the canonical backlog; commit directly to `0.0.2`
- Never hand-edit `openapi.json` or generated `fichero-api-client` sources

## 2026-05-28 ~17:10 — OVERNIGHT PROGRESS (durable checkpoint)

**SHIPPED to 0.0.2 tonight (all gated+pushed):** opus MCP (24 `fichero_mp_*` tools) · codex53 oMLX provider + #1277 citation-usage + #1258 claim-edit backend · gpt #1279 book-structure + provider-quota resilience + #1283 startup-auth + #1295 date-entity filter · gpt_mini #1278 book-index + #1288 audit + #1239 ACENET docs · **NodeDef Swift fix** · **TIER PROMOTION dev→release (#1298)** — ALL gated features (Mind Palace/Research/MCP/local-models/iiif/citation/actions/integrations/orchestration/schedules/triggers) now in `_CORE` · **#1302 KG WebKit click→inspector + sidebar-KG retired**. Trunk `928608b9`. All 6 lanes cleared.

**IN FLIGHT:** codex53=#1257 KG-viz · gpt=#1275 NodeDef determinism harden · gpt_mini=triage #1150-1240.

**KG-GEN (Daniel's headline):** running Catalogue on `tubb2020shift - Preface.pdf` (lib `CLI Preface+Ch1 Clean 20260523-063533.fichero`) — **changed that library's `large_provider/large_model` → apple/apple-intelligence** (was openrouter/sonnet-4.6, capped) so extraction is FREE on-device (English book; aligns with Daniel's "local models won't run out"). Verify KG rows when bg `b0uxswxoh` done, then scale to Chapter 1. NOTE: revert large→openrouter if Daniel prefers, but apple is cap-safe.

**GH triage:** gpt_mini closed 6 (#1277/#1278/#1255/#1257-partial etc.); manager REOPENED #1289 (onboarding not built) + #1258 (UI not built) — over-closed. Be conservative closing multi-part features.
