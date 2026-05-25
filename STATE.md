# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

Daniel testing 0.0.2. If passes, release checklist (#157–#165) in order.
Multi-agent split active: frontend Claude (#1202/#1204/#1181), backend Codex (#1054/#1173/#1198), pi CLI (imports).

**Manager gate status (2026-05-25 10:25a) — RESUME HERE:**
Two lanes are mid-gate, each with ONE small fix kicked back (workers fixing on their branches):
- **codex / #1198** (entity digest export): 3 review blockers RESOLVED (route exposed in OpenAPI,
  uses shared `get_library_database` resolver, negative-path tests). Last fix: register
  `_digest_library_database` in `conftest.py` `dependency_overrides` (or use `get_library_database`
  directly in `Depends()`) — positive tests currently pass by a db-cache coincidence, not isolation.
  Commits on `codex`: 0436ddd8 + 49ff32f5. #1173/#1054 verified already-fixed (no change).
- **pi / #1205** (delete dead Python CLI client): correct EXCEPT a typo — `head -30` → `head-30`
  on the swift-build line of `sync_openapi_schema.sh`. Restore the space. Commit on `pi`: 971586dd.

Next: when both refresh their done-notes → re-confirm diffs → `git merge --no-ff` BOTH into trunk →
run ONE integration verify on trunk (test-runner subagent, serial) → restart :8765 (backend changed)
→ resync codex/pi (`git merge 0.0.2`) → clear worker contexts.

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

## Completed overnight (2026-05-24 → 2026-05-25)

1. ✅ **Phase 1 — Dependabot liquidjs** — bumped to ≥ 10.25.7 via `overrides` in `site/package.json`.
2. ✅ **Phase 2 — SwiftLint** — zero warnings across all 334 Swift files (Codex, 6 commits).
3. ✅ **Phase 3 — #1201 OpenAPI freshness gate** — step 7 in `verify_python.sh`; gate implemented and issue closed.
4. ✅ **Phase 4 — KG entity library (#1183/#1191)** — `entity inspector` CLI command + `getEntityInspector()` Swift service method + `EntitySourceGroupsView` wired into `EntityDetailView`.

## Next Session — Start Here (frontend Claude)

**PAUSED — manager consolidating before context reset. Resume after manager clears backend gate.**

**14-issue queue status (2026-05-25 ~10:35a):**
- ✅ #1180 fixed + pushed (`2dca41f0`) — `DisplayAttributesStrip` wired into `documentDetail`
- ✅ Closed with evidence: #605 (startup clean in Swift), #958 (structured output already rendered), #718 (portrait aspect), #1044 (processing spinner), #717 (handleTap), #715 (NSTextView shortcuts native), #1032 (searchable toolbar)
- 🔴 **#1045** REAL — `documentProgressList` is flat file list, needs doc×step grid in `ActivityOverviewView.swift`
- 🔴 **#1048** REAL — no timing summary UI in any Activity view
- ❓ **#928** NEEDS VERIFY — loupe exists for images; check PDF page children coverage
- ⏳ **#702, #721** — 0.0.3 milestone, skip
- ⏳ **#330** — old milestone, skip

**On resume:**
1. Fix #1045 first (ActivityOverviewView.swift — replace flat file list with doc×step grid)
2. Fix #1048 (add timing summary to activity stats card)
3. Verify #928 (PDF page loupe)
4. Three-leg check: swiftlint + Xcode build; CAUTION do NOT RunAllTests (Daniel live-testing :8765)

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
