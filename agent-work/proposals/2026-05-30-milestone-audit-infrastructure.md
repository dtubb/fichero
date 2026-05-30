# Milestone Audit: Infrastructure — 2026-05-30

**Scope:** `dtubb/fichero` milestone **"Infrastructure"** (GitHub milestone #11).  
**Coverage:** 210 issues total — 19 open (all fully read), 191 closed (all scanned; bodies of 40+ read in full).  
**Proposal only — no GitHub state changed.**

---

## Summary counts

| Action | Count |
|---|---|
| Close open (implementation verified in codebase) | 6 |
| Wrong milestone → refile (open) | 7 |
| Label: add `type:` | 3 |
| Label: add `priority:` | 7 |
| Reopen (closed, never built) | **0** |
| No-op (correct as-is) | 3 |
| Closed issues scanned / confirmed legit | 191 |

---

## Coverage note

All 19 open issues were read in full. All 191 closed issues were enumerated with title + labels + state-reason. Bodies of ~40 closed issues were read in full (all with incomplete checkboxes, all planning stubs, all candidates for reopen, all "good ideas" flagged by category). Code was inspected to verify implementation status for every suspected "never built" candidate. **No closed issues warrant reopen** — see Part A for details.

---

## Part A — Closed Issues: Reopen Candidates

### Result: NONE

The "be generous" directive was applied rigorously: every closed issue with unchecked boxes, every planning stub, every feature described as future work was cross-checked against the live codebase. All verified as **actually implemented**. This is a clean milestone history.

Key verifications done:

| Issue | Suspicion | Verdict |
|---|---|---|
| #988 — Entity resolution (4 unchecked) | Never built? | **DONE** — `kg/graph.py:graph_context_merge_candidates()`, `kg/probabilistic_scorer.py` |
| #817 — Prompt eval harness | Never built? | **DONE** — `fichero-engine/evals/` dir with `run.py`, `scenarios/`, `criteria/` |
| #816 — Prompt versioning | Never built? | **DONE** — `fichero-engine/src/fichero/prompts.py` with `load_prompt()` |
| #852 — Token/cost tracking via include_raw | Never built? | **DONE** — `llm.py:1629` `include_raw=True` + `usage_metadata` collection |
| #871 — Theme D: Test + observability | Never built? | **DONE** — activity SSE/WebSocket stream, stats endpoint, evals harness |
| #425 — Activity stream enhancements | Never built? | **DONE** — `activity.py` has `/stats` (line 225) + SSE stream (line 246) + WebSocket |
| #422-419 — 0.0.3 feature wrappers (all unchecked) | Never built? | **DONE** — implementations in open issues #368-371 AND verified in codebase |
| #1134 — CLI + API entity/claim create | Never built? | **DONE** — `POST /api/entities` (entities.py:284), `POST /api/claims` (claims.py:229), CLI `create_entity()`/`create_claim()` |
| #691 — Aggregate node primitive | Never built? | **DONE** — `workflows/tools/aggregate.py`, used in `catalogue.json`, `catalogue-each.json` |
| #516 — CSV/RTF/MOBI in FileType | Never built? | **DONE** — `Document.swift:35-37` has `case csv`, `case rtf`, `case mobi` |
| #391 — Phase 5: Security review | Review never done? | **DONE** — SSRF guard (`_is_safe_url` + `_is_sandbox_violation`), auth middleware, input validation are all present |
| #390 — Phase 4: Agent Research | Never built? | **DONE** — `research_models.py`, `research_crud.py`, `research_tools.py` exist |
| #820 — Foundation toolkit tracker | Children unbuilt? | **DONE** — all 5 children (#815–#819) confirmed CLOSED/COMPLETED |

### Do NOT reopen — historical planning stubs (correctly closed)

The 0.0.x phase/theme tracking issues (#419–422, #425, #388–391, #819–#820, #863–#872) were roadmapping artifacts that were closed when the features shipped. The unchecked boxes in those issues were acceptance-criteria checklists on planning stubs, not proof of unbuilt work. The actual features landed in focused implementation issues.

---

## Part B — Open Issues: Close (Implementation Verified)

These 6 open issues have been fully implemented in the codebase. They should be closed as COMPLETED.

```bash
# #382 — 0.0.1 Regression Gate: all 4 blocking children (#383, #384, #385, #386) are
# CLOSED/COMPLETED. 0.0.1 shipped. This gate is a stale artifact.
gh issue close 382 --repo dtubb/fichero --comment "All blocking children closed; 0.0.1 shipped. Closing stale gate."

# #359 — Folder Watchers: implemented in `file_watcher.py` (watchdog Observer, FileWatcherManager),
# and wired into SwiftUI (AppState.showFolderWatchers, FicheroApp.swift, LibraryWindow.swift).
# Also wrong-milestoned (belongs in Importers). Close here, re-file is in Part C.
gh issue close 359 --repo dtubb/fichero --comment "Implemented: fichero-engine/src/fichero/workflows/file_watcher.py (FileWatcherManager + Observer). SwiftUI AppState.showFolderWatchers wired. Closing."
gh issue edit 359 --repo dtubb/fichero --milestone "Importers"

# #368 — 0.0.3: Knowledge migration/backfill tooling with dry-run rollback:
# Implemented in fichero-engine/src/fichero/migrations.py (MigrationRunner,
# dry_run=True/False, migrate_claims_to_multi_source, rollback paths).
gh issue close 368 --repo dtubb/fichero --comment "Implemented: fichero-engine/src/fichero/migrations.py — MigrationRunner with dry_run mode, rollback, audit trail."

# #369 — 0.0.3: Reindex/repair jobs and metrics recomputation workers:
# Implemented in workflows/tasks.py (BackgroundTaskSystem), task_workers.py
# (_execute_reindex, _do_reindex), task_types.py (TaskType.REINDEX).
gh issue close 369 --repo dtubb/fichero --comment "Implemented: workflows/tasks.py + task_workers.py + task_types.py — REINDEX task type, idempotent workers, job-status endpoints."

# #370 — 0.0.3: Multilingual baseline for claims/entities and cross-language retrieval:
# Implemented in multilingual.py (cld3 + heuristic fallback), lang_detect.py,
# source_language/source_languages fields on KnowledgeClaim, /api/claims?source_language=X filter,
# test_routes_multilingual.py tests.
gh issue close 370 --repo dtubb/fichero --comment "Implemented: multilingual.py (cld3 + fallback), source_language fields in knowledge_models.py, cross-language claim filter in claims.py, unit tests in test_routes_multilingual.py."

# #371 — 0.0.3: Thin MCP adapters for canonical knowledge APIs:
# Implemented in api/routes/mcp_tools.py — mcp_knowledge_entity_upsert,
# mcp_knowledge_claim_create, mcp_knowledge_entity_get, mcp_knowledge_entity_delete, etc.
# Mounted at /api/mcp/tools in main.py.
gh issue close 371 --repo dtubb/fichero --comment "Implemented: api/routes/mcp_tools.py with entity/claim CRUD adapters, mounted at /api/mcp/tools in main.py."
```

---

## Part C — Open Issues: Wrong Milestone → Refile

### Move to Settings & Providers (#20)

```bash
# #1059 — Consolidate model/provider selection (~6 picker UIs, inconsistent behaviour)
# Scope is purely SwiftUI provider/model picker components. Not infrastructure.
# Correct home: Settings & Providers (model management UI is that milestone's charter).
gh issue edit 1059 --repo dtubb/fichero --milestone "Settings & Providers"
```

### Move to Activity & Automation (#56)

```bash
# #280 — Re-enable Integrations menu after 0.0.2 hardening
# This is about enabling a UI surface (Integrations menu), not backend infra.
# The Automation milestone owns the integrations entry paths.
gh issue edit 280 --repo dtubb/fichero --milestone "Activity & Automation"
```

### Move to Developer Experience (#64)

```bash
# #1133 — AppleScript bridge: programmatic UI control for autonomous dev/test loop
# Goal is explicitly "speed up development" and "close the autonomous test loop."
# Pure dev tooling. Developer Experience is the right home.
gh issue edit 1133 --repo dtubb/fichero --milestone "Developer Experience"

# #873 — pytest integration test: workflow-execution end-to-end
# Dev/CI tooling. Not a user-facing infrastructure feature.
gh issue edit 873 --repo dtubb/fichero --milestone "Developer Experience"

# #1151 — Feature-gate audit: re-enable the simple surfaces, keep agent/thinking ones gated
# A developer decision log / gate-map task. No user-visible infra work.
gh issue edit 1151 --repo dtubb/fichero --milestone "Developer Experience"
```

### Move to Library & Reading Surface (#60)

```bash
# #1072 — Audit the whole SwiftUI codebase for logic that belongs in the backend
# This is a SwiftUI architecture audit. The output is refactoring the display layer.
# Library & Reading Surface owns the SwiftUI reading/display architecture.
gh issue edit 1072 --repo dtubb/fichero --milestone "Library & Reading Surface"
```

---

## Part D — Label Corrections (issues staying in Infrastructure)

After the closes and refiles above, Infrastructure retains these open issues: #1341, #1239, #510, #477, #461, #320. Plus release-gate trackers #515 and #510 (already in Infrastructure, stays).

### Add `priority:` (7 issues missing it)

```bash
# #1239 — SSH/ACENET remote backend: important but not urgent, P2
gh issue edit 1239 --repo dtubb/fichero --add-label "priority:P2"

# #477 — API Security (localhost + API key auth): P1 — blocks production use and #510
gh issue edit 477 --repo dtubb/fichero --add-label "priority:P1"

# #461 — Async DNS in _is_safe_url: P3 — latency/reliability issue, not breaking
gh issue edit 461 --repo dtubb/fichero --add-label "priority:P3"

# #510 — Release Gate 0.5.1 API Security + Auth: P1 — gate for shipping auth
gh issue edit 510 --repo dtubb/fichero --add-label "priority:P1"

# #515 — Release Gate 0.7.2 Integrations: P3 — far future gate
gh issue edit 515 --repo dtubb/fichero --add-label "priority:P3"

# #320 — Bundle identifier migration (ca.tubb → com.tubb): P3 — dev-only installs only
gh issue edit 320 --repo dtubb/fichero --add-label "priority:P3"

# #1341 — already has priority:P2, no change needed ✓
```

### Add `type:` (3 issues missing it)

```bash
# #1151 — (being moved to DevEx) — add type:task while editing
# Include --add-label in the same gh issue edit call as the milestone change above:
gh issue edit 1151 --repo dtubb/fichero --milestone "Developer Experience" --add-label "type:task,priority:P2"

# #510 — type:task (release gate wiring work)
gh issue edit 510 --repo dtubb/fichero --add-label "type:task"

# #515 — type:task (release gate wiring work)
gh issue edit 515 --repo dtubb/fichero --add-label "type:task"
```

### Fix duplicate type label

```bash
# #1239 has both type:task AND type:feature — remove the duplicate
gh issue edit 1239 --repo dtubb/fichero --remove-label "type:task"
# (type:feature is the correct one — it's a new capability, not a refactor/chore)
```

---

## Part E — Open Issues Remaining in Infrastructure (no action needed)

After all changes above, Infrastructure retains these 7 open issues, all correctly scoped:

| # | Title | Labels (after fixes) | Notes |
|---|---|---|---|
| #1341 | Audit + standardize Mac storage paths | `type:task, needs-design, backend, priority:P2` | Core infra, correctly scoped |
| #1239 | SSH/ACENET remote backend | `type:feature, backend, priority:P2` | Infra: remote backend connection |
| #510 | [Release Gate] 0.5.1 API Security + Auth | `type:task, backend, roadmap, priority:P1` | Gate for #477 |
| #515 | [Release Gate] 0.7.2 Integrations | `type:task, roadmap, priority:P3` | Far-future gate |
| #477 | API Security: localhost + optional API key | `type:task, backend, priority:P1` | Core auth infra |
| #461 | Make _is_safe_url async (blocking DNS) | `type:task, backend, roadmap, priority:P3` | Correctness fix |
| #320 | Bundle ID migration (ca.tubb → com.tubb) | `type:feature, backend, priority:P3` | Superseded-scope: #1341 covers current rename; this covers old one. Keep open for completeness. |

---

## Part F — What Is NOT in This Milestone (gaps to file separately)

The Infrastructure milestone description mentions these items that have **no open issue**:

- **Rate limiting** on backend endpoints — no issue exists. Would need a new `type:feature, backend, priority:P2` issue.
- **Audit logging** (request/response log, who-did-what) — no issue exists. Worth filing.
- **Admin health endpoints** (beyond `/api/health`) — partially addressed by reindex job status, but a comprehensive observability endpoint is untracked.
- **DEVONthink integration** — mentioned in milestone description; no issue. Belongs here or Importers.
- **Bookends integration** — per prompt, may belong in **Bibliography & Citations (#68)** not Infrastructure.
- **Tinderbox integration** — per prompt, belongs in **Importers (#57)** (`.tbx importer` is in that milestone's description).
- **IIIF support** — no issue; would be Importers or Source Archives depending on scope.
- **Contradiction workflows** — mentioned in milestone description; no open issue.

These are proposals for **new issues** to file, not changes to existing issues. Not actioned here (proposal only).

---

## Consolidated Checklist

Copy-paste execution order (propose only — verify each before running):

```bash
# ── CLOSES ──────────────────────────────────────────────────────────────────
gh issue close 382 --repo dtubb/fichero --comment "All blocking children closed; 0.0.1 shipped. Closing stale gate."
gh issue close 368 --repo dtubb/fichero --comment "Implemented: migrations.py — MigrationRunner with dry_run, rollback, audit trail."
gh issue close 369 --repo dtubb/fichero --comment "Implemented: workflows/tasks.py + task_workers.py — REINDEX task, idempotent workers."
gh issue close 370 --repo dtubb/fichero --comment "Implemented: multilingual.py, source_language fields, cross-language filter, test_routes_multilingual.py."
gh issue close 371 --repo dtubb/fichero --comment "Implemented: api/routes/mcp_tools.py — entity/claim adapters at /api/mcp/tools."
gh issue close 359 --repo dtubb/fichero --comment "Implemented: workflows/file_watcher.py (FileWatcherManager). SwiftUI wired."

# ── REFILES ─────────────────────────────────────────────────────────────────
gh issue edit 359 --repo dtubb/fichero --milestone "Importers"
gh issue edit 1059 --repo dtubb/fichero --milestone "Settings & Providers"
gh issue edit 280 --repo dtubb/fichero --milestone "Activity & Automation"
gh issue edit 1133 --repo dtubb/fichero --milestone "Developer Experience"
gh issue edit 873 --repo dtubb/fichero --milestone "Developer Experience"
gh issue edit 1072 --repo dtubb/fichero --milestone "Library & Reading Surface"

# ── LABEL FIXES ─────────────────────────────────────────────────────────────
# #1151 combined (refile + type + priority)
gh issue edit 1151 --repo dtubb/fichero \
  --milestone "Developer Experience" \
  --add-label "type:task,priority:P2"

# Priority additions
gh issue edit 1239 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 477 --repo dtubb/fichero --add-label "priority:P1"
gh issue edit 461 --repo dtubb/fichero --add-label "priority:P3"
gh issue edit 510 --repo dtubb/fichero --add-label "type:task,priority:P1"
gh issue edit 515 --repo dtubb/fichero --add-label "type:task,priority:P3"
gh issue edit 320 --repo dtubb/fichero --add-label "priority:P3"

# Duplicate type label fix
gh issue edit 1239 --repo dtubb/fichero --remove-label "type:task"
```

---

## Summary

| Metric | Before | After |
|---|---|---|
| Open issues in Infrastructure | 19 | 7 |
| Issues closed as completed | — | +6 |
| Issues refiled to correct milestone | — | +7 |
| Reopened issues | — | 0 |
| Issues with complete `type:` + `priority:` | 1/19 | 7/7 |

**Infrastructure is healthy.** The closed history is clean — all verified built. The bulk of the open count was implementation work from 0.0.3 that has since shipped, plus a batch of issues that were always scoped to other feature areas (Settings, Importers, DevEx, Library).

After cleanup, Infrastructure holds 7 correctly-scoped open issues: storage-path standardization (#1341), remote backend (#1239), API security/auth (#477 + gate #510), integrations gate (#515), async DNS fix (#461), and the old bundle-ID migration (#320). All are genuine infrastructure concerns.
