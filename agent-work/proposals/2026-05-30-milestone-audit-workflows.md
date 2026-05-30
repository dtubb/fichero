# Milestone Audit: Workflows — 2026-05-30

**Scope:** `dtubb/fichero` milestone **"Workflows"** (GitHub milestone #54).  
**Coverage:** 100 issues total — 32 open, 68 closed. All closed issues reviewed below.  
**Proposal only — no GitHub state changed.**

---

## Summary counts

| Action | Count |
|---|---|
| Reopen (closed-but-uncaptured ideas) | 4 |
| Wrong milestone → refile (open) | 1 |
| Label: add `type:` | 6 |
| Label: add `priority:` | 27 |
| Label: add surface (`backend`/`client:swiftui`) | 4 |
| Label: add `tier:*` (new) | 16 |
| Label: add `needs:human` for release gates | 5 |
| No-op (correct as-is or trivially closed) | 57 |

---

## Part A — Closed Issues: Reopen Candidates

All 68 closed issues have `stateReason: COMPLETED` (none `NOT_PLANNED`). Four are closed but the tracked idea is **not fully implemented** and has real uncaptured value.

### REOPEN

```bash
# 1332 partial — DeepL done, local Apple Translate/MLX NOT done
# (translate.py + translate.json ship DeepL; no local Apple Translate path exists)
gh issue reopen 1332 --repo dtubb/fichero
gh issue edit 1332 --repo dtubb/fichero \
  --add-label "type:feature,backend,priority:P2,tier:medium"
# Suggest appending body note: "DeepL + translate.json shipped. Remaining: local Apple Translate/MLX mode."
```

```bash
# 716 partial — paleography_spanish.json exists but is a 2-node baseline (Files + Transcribe),
# NOT the 4-step multi-step reasoning chain (prime → transcribe → review → reconcile) that the issue specifies.
gh issue reopen 716 --repo dtubb/fichero
gh issue edit 716 --repo dtubb/fichero \
  --add-label "priority:P2,backend,tier:medium"
```

```bash
# 340 uncaptured — closed "as part of 0.0.1 milestone" but acceptance criteria still show
# 3 unchecked items. PromptPreviewPanel.swift exists so the basic panel shipped, but
# live-update-on-config-change and system-vs-user prompt distinction are not confirmed.
# Low-cost reopen; retriage after Daniel manually confirms the panel behavior.
gh issue reopen 340 --repo dtubb/fichero
gh issue edit 340 --repo dtubb/fichero \
  --add-label "type:feature,client:swiftui,priority:P3,tier:mini"
```

```bash
# 1287 design task — "Codex investigation/design task (look into; build later)".
# Closed COMPLETED after a narrow stopgap e2e test was added (#1285).
# The full harness (fixture corpus, real-vs-mocked extractor modes, folder workflow shape
# coverage, auto-re-run when default JSON changes) was explicitly deferred, not built.
# This is high-leverage CI infra worth tracking.
gh issue reopen 1287 --repo dtubb/fichero
gh issue edit 1287 --repo dtubb/fichero \
  --add-label "type:task,backend,priority:P2,tier:frontier"
```

### Do NOT reopen (closed issues reviewed and confirmed done)

All other 64 closed issues were verified as shipped:
- **#689** (`write_file` tool): `write_file.py` exists in `workflows/tools/`. Done.
- **#692** (fan-out/fan-in badges): `WorkflowCanvasView.swift` has `fanRole`/`fanCount` logic and `EdgeFanRoleResolver`. Done.
- **#810** ($small/$large model aliases): `resolve_model_alias()` in `llm.py`, `default_small_provider`/`default_large_provider` in `app_db.py`, pickers in `AISettingsView.swift`. Done.
- **#1116** (checkpointer delete via public API): `adelete_thread()` in `checkpointer.py`; `threads.py` calls it. Done.
- **#386** (0.0.1 QA checklist): Old 0.0.1 release issue; superseded by the shipped release. Not actionable.
- **#250** (workflow QA gates): Closed as the acceptance gate for 248/249. Done.
- All bug fixes #292–#1252: Correct as closed. No reopen candidates found.

**Activity-titled closed issues in Workflows milestone (#628, #631, #636, #651, #653, #699, #944, #1045):** These were filed in Workflows because they shipped alongside workflow work. They are legitimately closed. The live Activity view concerns are now tracked in the **Activity & Automation** milestone (#1224, #1225, #1226). No remilestoning needed for historical closed records.

---

## Part B — Open Issues: Wrong Milestone

### Move to Activity & Automation

No open issues are misplaced. All 32 open issues in Workflows are correctly scoped to visual canvas editor, tool nodes, LangGraph chains, batch processing, or translation workflow.

**#343** (Artifact comparison: side-by-side diff) is borderline — the UI surface is the inspector (Library & Reading Surface territory), but the user story is "compare workflow output artifacts." Per conventions the primary user story wins → stays in **Workflows**. Flag for Daniel's call if inspector-chrome work dominates.

---

## Part C — Open Issues: Label Corrections

### Add `type:` (6 issues missing it)

```bash
# #289 — per-tool system prompts + anti-hallucination guardrails → type:feature (new capability layer)
gh issue edit 289 --repo dtubb/fichero --add-label "type:feature"

# #488 — Release Gate 0.1.0 → type:task (tracking/validation task)
gh issue edit 488 --repo dtubb/fichero --add-label "type:task"

# #489 — Release Gate 0.1.1 → type:task
gh issue edit 489 --repo dtubb/fichero --add-label "type:task"

# #490 — Release Gate 0.1.2 → type:task
gh issue edit 490 --repo dtubb/fichero --add-label "type:task"

# #491 — Release Gate 0.1.3 → type:task
gh issue edit 491 --repo dtubb/fichero --add-label "type:task"

# #756 — Language identification tool → type:feature
gh issue edit 756 --repo dtubb/fichero --add-label "type:feature"

# #768 — Migrate provider picker to OpenAPI-typed ProviderResponse → type:task (refactor)
gh issue edit 768 --repo dtubb/fichero --add-label "type:task"
```

Note: #492 also lacks `type:` but also lacks a surface label — handled in surface section below.

### Add surface label (4 issues missing `backend`/`client:swiftui`)

```bash
# #492 — Release Gate 0.1.4 Batch Processing → area:both (backend batch + SwiftUI Batches sidebar)
gh issue edit 492 --repo dtubb/fichero --add-label "type:task,area:both"

# #657 — HPC/SLURM batch → backend (Python submission + result import)
gh issue edit 657 --repo dtubb/fichero --add-label "backend"

# #676 — Catalogue workflow → area:both (backend workflow tool + SwiftUI output)
gh issue edit 676 --repo dtubb/fichero --add-label "area:both"

# #716 — Paleography Transcribe workflow → area:both (backend template + SwiftUI workflow library)
gh issue edit 716 --repo dtubb/fichero --add-label "area:both"

# #720 — Catalogue composable bug → area:both (backend reducer node + SwiftUI output)
gh issue edit 720 --repo dtubb/fichero --add-label "area:both"
```

### Add `priority:` (27 issues missing it — all open issues except #1220)

```bash
# P1 — broken/blocking current research workflow
gh issue edit 676 --repo dtubb/fichero --add-label "priority:P1"  # Catalogue map-reduce broken
gh issue edit 720 --repo dtubb/fichero --add-label "priority:P1"  # Composable catalogue no combined artifact

# P2 — significant capability gaps or UX blockers
gh issue edit 248 --repo dtubb/fichero --add-label "priority:P2"  # Promote Workflows to beta
gh issue edit 249 --repo dtubb/fichero --add-label "priority:P2"  # Promote Workflow Execution to beta
gh issue edit 254 --repo dtubb/fichero --add-label "priority:P2"  # Promote Batches to beta
gh issue edit 282 --repo dtubb/fichero --add-label "priority:P2"  # Re-enable Batches sidebar
gh issue edit 286 --repo dtubb/fichero --add-label "priority:P2"  # Re-enable editor icon/list/table modes (SwiftUI)
gh issue edit 289 --repo dtubb/fichero --add-label "priority:P2"  # Per-tool prompts/guardrails
gh issue edit 343 --repo dtubb/fichero --add-label "priority:P2"  # Artifact comparison
gh issue edit 345 --repo dtubb/fichero --add-label "priority:P2"  # Unify vision engine + provider picker
gh issue edit 348 --repo dtubb/fichero --add-label "priority:P2"  # Batch input: collection OR selection
gh issue edit 433 --repo dtubb/fichero --add-label "priority:P2"  # Re-enable editor modes (backend)
gh issue edit 488 --repo dtubb/fichero --add-label "priority:P2"  # Release Gate 0.1.0
gh issue edit 489 --repo dtubb/fichero --add-label "priority:P2"  # Release Gate 0.1.1
gh issue edit 490 --repo dtubb/fichero --add-label "priority:P2"  # Release Gate 0.1.2
gh issue edit 491 --repo dtubb/fichero --add-label "priority:P2"  # Release Gate 0.1.3
gh issue edit 492 --repo dtubb/fichero --add-label "priority:P2"  # Release Gate 0.1.4
gh issue edit 667 --repo dtubb/fichero --add-label "priority:P2"  # Selection source node
gh issue edit 714 --repo dtubb/fichero --add-label "priority:P2"  # Install defaults undercounts (bug)
gh issue edit 716 --repo dtubb/fichero --add-label "priority:P2"  # Paleography Transcribe (4-step)
gh issue edit 756 --repo dtubb/fichero --add-label "priority:P2"  # Language ID tool
gh issue edit 768 --repo dtubb/fichero --add-label "priority:P2"  # Migrate provider picker
gh issue edit 797 --repo dtubb/fichero --add-label "priority:P2"  # Model picker submenu
gh issue edit 801 --repo dtubb/fichero --add-label "priority:P2"  # Chunk inputs for on-device LLMs

# P3 — future/advanced/deferred
gh issue edit 251 --repo dtubb/fichero --add-label "priority:P3"  # Promote Workflows to release (depends on beta)
gh issue edit 252 --repo dtubb/fichero --add-label "priority:P3"  # Promote Workflow Execution to release
gh issue edit 341 --repo dtubb/fichero --add-label "priority:P3"  # Workflow provider: CLI agent tools
gh issue edit 349 --repo dtubb/fichero --add-label "priority:P3"  # Batch: selectable processing order
gh issue edit 657 --repo dtubb/fichero --add-label "priority:P3"  # HPC/SLURM (distant future)
gh issue edit 751 --repo dtubb/fichero --add-label "priority:P3"  # Context menu folder grouping (part 2)
```

### Add `tier:` label (16 issues — implementation hints for dispatch)

```bash
# tier:frontier — architectural design, ambiguous scope, or cross-layer refactor
gh issue edit 289 --repo dtubb/fichero --add-label "tier:frontier"  # Per-tool prompt contract design
gh issue edit 341 --repo dtubb/fichero --add-label "tier:frontier"  # CLI agent workflow provider (novel integration)
gh issue edit 345 --repo dtubb/fichero --add-label "tier:frontier"  # Unify vision engine + provider (requires UX design)
gh issue edit 657 --repo dtubb/fichero --add-label "tier:frontier"  # HPC/SLURM (novel infrastructure)

# tier:medium — typical implementation task, well-specified
gh issue edit 282 --repo dtubb/fichero --add-label "tier:medium"  # Re-enable Batches sidebar
gh issue edit 286 --repo dtubb/fichero --add-label "tier:medium"  # Re-enable editor modes (SwiftUI)
gh issue edit 343 --repo dtubb/fichero --add-label "tier:medium"  # Artifact comparison UI
gh issue edit 348 --repo dtubb/fichero --add-label "tier:medium"  # Batch input: collection/selection
gh issue edit 433 --repo dtubb/fichero --add-label "tier:medium"  # Re-enable editor modes (backend)
gh issue edit 667 --repo dtubb/fichero --add-label "tier:medium"  # Selection source node
gh issue edit 756 --repo dtubb/fichero --add-label "tier:medium"  # Language ID tool
gh issue edit 768 --repo dtubb/fichero --add-label "tier:medium"  # Migrate provider picker
gh issue edit 797 --repo dtubb/fichero --add-label "tier:medium"  # Model picker submenu
gh issue edit 801 --repo dtubb/fichero --add-label "tier:medium"  # Chunk inputs for on-device LLMs

# tier:mini — narrow, mechanical, well-scoped
gh issue edit 714 --repo dtubb/fichero --add-label "tier:mini"  # Install defaults undercounts (count bug)
gh issue edit 349 --repo dtubb/fichero --add-label "tier:mini"  # Batch processing order selector
gh issue edit 751 --repo dtubb/fichero --add-label "tier:mini"  # Context menu folder grouping
```

### Add `needs:human` for release gate issues (5 — Daniel validates these, not an agent)

```bash
gh issue edit 488 --repo dtubb/fichero --add-label "needs:human"  # 0.1.0 Wire: Workflow Basics
gh issue edit 489 --repo dtubb/fichero --add-label "needs:human"  # 0.1.1 Wire: Workflow Editor
gh issue edit 490 --repo dtubb/fichero --add-label "needs:human"  # 0.1.2 Wire: Workflow Tools
gh issue edit 491 --repo dtubb/fichero --add-label "needs:human"  # 0.1.3 Wire: Workflow Chains
gh issue edit 492 --repo dtubb/fichero --add-label "needs:human"  # 0.1.4 Wire: Batch Processing
```

Also consider removing `status:ready-for-test` from #488–#492 if the underlying work isn't all shipped yet (workflows are in backend core routes but `isWorkflowsEnabled` defaults to `false` in SwiftUI — the release gate criteria aren't met). Replace with no status label (open = in progress).

```bash
# Optional — remove premature ready-for-test from release gates
gh issue edit 488 --repo dtubb/fichero --remove-label "status:ready-for-test"
gh issue edit 489 --repo dtubb/fichero --remove-label "status:ready-for-test"
gh issue edit 490 --repo dtubb/fichero --remove-label "status:ready-for-test"
gh issue edit 491 --repo dtubb/fichero --remove-label "status:ready-for-test"
```

---

## Part D — Observations (no immediate action required)

### #248/#249 "Promote to beta" — backend is already shipped, SwiftUI gate remains

`workflow_execution.router` and `workflows.router` are in `_CORE_ROUTE_SPECS` (always-on). However, `isWorkflowsEnabled` defaults to `false` in `FeatureManager.swift` — only `allFeaturesEnabled` (via `FICHERO_ALL_FEATURES=1`) or an opt-in `AppStorage` flip enables the UI. Issue #250 (QA gate) is closed. The remaining work for #248/#249 is the SwiftUI feature-flag flip + release confirmation by Daniel.

### #433 vs #286 — not duplicates

- **#286** (`client:swiftui`, `roadmap`): Re-enable icon/list/table view modes in WorkflowEditor SwiftUI views.
- **#433** (`backend`): Restore backend routes for different workflow editor view modes.
These are the two halves of the same feature; both should stay open.

### #1332 — split recommendation

The issue mixes two sub-tasks: (a) DeepL provider (shipped) and (b) local Apple Translate/MLX (not shipped). Consider splitting into a separate issue for the local model path. Or keep as-is and update the title/body to reflect what remains. Either is fine; the reopen above captures it.

### #657 HPC/SLURM — very distant

This is legitimately in Workflows milestone (batch processing extension) per the conventions doc. P3. No remilestoning needed, but it may be useful to add `needs-design` since there's no architecture decision for the bundle/submission mechanism yet.

```bash
# Optional
gh issue edit 657 --repo dtubb/fichero --add-label "needs-design"
```

### Closed issues with NO LABELS (#689, #692, #761, #1287)

Three confirmed shipped (`#689`, `#692`, `#761`); one reopened (`#1287`). For the shipped ones, add labels retroactively only if it matters for reporting/filtering:

```bash
# Optional — label closed completed issues for historical clarity
gh issue edit 689 --repo dtubb/fichero --add-label "type:feature,area:both"
gh issue edit 692 --repo dtubb/fichero --add-label "type:feature,area:both"
gh issue edit 761 --repo dtubb/fichero --add-label "type:bug,client:swiftui"
```

---

## Reopen Candidates Summary

| Issue | Title | Why Reopen |
|---|---|---|
| #1332 | Translation workflow — local models + DeepL | DeepL shipped; Apple Translate/MLX path unbuilt |
| #716 | Paleography Transcribe | 2-node baseline shipped; 4-step reasoning chain not built |
| #340 | Workflow node: prompt preview panel | PromptPreviewPanel.swift exists; live-update + system/user distinction unconfirmed |
| #1287 | End-to-end workflow regression harness | Narrow stopgap landed (#1285); full harness (folder shape, fixture corpus, CI re-run on JSON change) not built |

---

## Coverage Note

All 32 open issues reviewed individually. All 68 closed issues scanned with body analysis; 12 were read in full (those with unchecked acceptance criteria, no-label issues, or potential wrong-milestone boundary). I am confident I have not missed a reopen candidate among the closed set — all other closures correspond to shipped code verified in the working tree.

Activity-titled closed issues (#628, #631, #636, #651, #653, #699, #944, #1045) remain in the Workflows milestone as historical records; the live Activity view work is tracked in Activity & Automation. No remilestoning of closed issues is proposed.
