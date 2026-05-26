# STATE.md — Fichero

## 2026-05-26 EVENING — OVERNIGHT AUTONOMOUS HANDOFF (read first after compaction)

**Role:** f_manager, branch `0.0.2`, `~/code/fichero-0.0.2`. Daniel is out for the night, checks via phone (GitHub). Full-steam autonomous; 0.0.3 features are in-scope.

**REGIME — PACE FOR ~12 HOURS, DON'T SPRINT (Daniel's governing rule).** Both Claude AND OpenAI/Codex will run out of funds if hammered — steady all-night progress beats burning everything in 2 hours. THROTTLE: keep only ~2-3 lanes active at once (rotate), let lanes idle between tasks, refeed sparingly, use LONG ~60-min tick intervals. Claude quota was tight (92%→~61%); slightly prefer Codex but don't blast it either. Claude lanes sometimes show a spurious **"Upgrade your plan"** dialog (NOT real exhaustion) — reset with `1` then `continue`. Conserve manager context: light ticks, offload to lanes/subagents, read verdicts not logs. Re-pause lanes if any provider's quota climbs toward ~90%.

**LANES** (worktrees `~/code/fichero-<name>`, each commits to its own branch, manager/integrator merges):
- `f_sonnet` (Claude, branch sonnet): KG-spine COMMITTED — #1248 `92dd9635`, #1254+#1263 `2c40907b`, #1249 `6dd058ae`. Now: #1252 (RTF strip) → #1251 (progress) → validate Catalogue+Apple → #1237 (XLSX).
- `f_opus` (Claude, branch opus, OWNS Xcode): #1247 `4a4ad3cd`, #1245 `d9ec347d` committed (branch also carries held #1230 `4297740c`). Now: #1243 → #1244 → #1246 → #1253 → #1230 debug.
- `f_haiku` (Claude, branch haiku): #1260 `1a17cb8f` committed; extending #1260 (AI hook + tests) in its own module only.
- `f_codex53` (OpenAI, branch codex53): #1259 `1477b1e7` committed; now #462/#463 image-editing foundation (uncommitted WIP).
- `f_gpt` (OpenAI, branch gpt): #1262 `22dac9b3` committed; now #472/#473 export (uncommitted WIP).
- `f_gpt_mini` (OpenAI, branch gpt-mini): #1256 audit `bb00a461` + phase-1 WIP; REASSIGNED to **CLI end-to-end KG validation** — start engine from sonnet code on `:8799` + temp library, import→Catalogue(apple)→query KG, confirm #1248/#1254/#1249 work (don't disturb Daniel's `:8765`).
- Role lanes (Claude, reset from spurious dialog): `f_integrator` (merge gate), `f_reviewer` (review backlog), `f_planner` (image-epic decomposition → agent-work/proposals/). `f_bugtriage` idle.

**MERGE BACKLOG** (all off trunk `55e9aed0`, NONE merged yet). Pipeline: f_reviewer APPROVE → f_integrator verify in the **0.0.2 trunk worktree** → `git merge --no-ff <branch>` + `git push origin 0.0.2` (NEVER main) → comment/close issue. Order: **sonnet KG spine FIRST** → opus (#1247/#1245; carries #1230 — keep issue #1230 OPEN) → haiku #1260. Codex branches: merge each only after it reports its current task done. Backend verify: `/Users/danieltubb/code/fichero-0.0.2/.venv/bin/pytest` with `PYTHONPATH=<lane>/fichero-engine/src` (lane worktrees have no .venv).

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
