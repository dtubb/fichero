# Milestone Audit — Settings & Providers
**Date:** 2026-05-30  
**Scope:** All 55 issues (19 open, 36 closed) in the "Settings & Providers" milestone  
**Canonical labels:** type:{bug,feature,task} · priority:{P0-P3} · status:{blocked,ready-for-test} · needs:human · tier:{frontier,medium,mini,local} · client:{swiftui,cli,html} · backend · mcp · area:both · roadmap · needs-design · documentation  

---

## Summary Counts

| Action | Count |
|---|---|
| Re-milestone to correct bucket | 5 |
| Reopen (closed, real unfinished work) | 3 |
| Label fixes (add missing type:/priority:/surface) | 18 |
| Close as obsolete/superseded | 3 |
| No change | 26 |

---

## SECTION A — Re-milestone (wrong bucket)

These issues are about sidebar drag-drop and sidebar structure — they belong in **Library & Reading Surface**, not Settings & Providers.

```bash
gh issue edit 572 --repo dtubb/fichero --milestone "Library & Reading Surface"
# "Add sort_order to Document; wire sidebar reorder via drag-drop" — pure sidebar/document feature, not settings

gh issue edit 580 --repo dtubb/fichero --milestone "Library & Reading Surface"
# "Restore between-row drops with safer mechanism" — sidebar SwiftUI bug, not settings

gh issue edit 583 --repo dtubb/fichero --milestone "Library & Reading Surface"
# "Sidebar test coverage sprint" — sidebar tests, not settings

gh issue edit 585 --repo dtubb/fichero --milestone "Library & Reading Surface"
# "Sidebar structural cleanup: split SidebarItemRow" — sidebar refactor, not settings
```

Issue #799 (fm-bridge GenerationSchema) belongs in **Workflows** — it is a workflow extraction-quality backend concern, not a settings/provider management concern. The Apple Intelligence work in this milestone is about provider config; #799 is about structured output in extractors.

```bash
gh issue edit 799 --repo dtubb/fichero --milestone "Workflows"
# "fm-bridge: GenerationSchema for guaranteed structured output" — workflow extraction quality, not provider management
```

---

## SECTION B — Reopen (closed but unfinished ideas — be generous)

### B1. #843 — Apple Intelligence structured output: polish
**Reopen.** Closed as COMPLETED, but the body lists 4 explicit follow-up items, none of which have tracking issues:
1. `includeSchemaInPrompt: false` when schema is already in instructions (token savings in 4K window)
2. Typed `guardrailViolation` enum detection in fm-bridge (currently string-matched at llm.py:445)
3. Token usage telemetry from `Response<GeneratedContent>.transcriptEntries` (cost-tracking parity with cloud providers)
4. Pre-validate schema tree before `GenerationSchema(root:dependencies:)` (better error messages)

Items 2–4 in particular are real gaps. #799 covers item 1 partially but not the others. Reopen to track these, or create a dedicated follow-up issue.

```bash
gh issue reopen 843 --repo dtubb/fichero
gh issue edit 843 --repo dtubb/fichero --add-label "backend" --add-label "priority:P3"
# Rationale: 4 concrete follow-up sub-items in the body have no tracking; token usage telemetry and typed guardrail enum are real improvements with no child issues
```

### B2. #853 — Apple Intelligence: prewarm() + contentTagging useCase for keywords
**Reopen.** Closed as COMPLETED, but the body describes two *distinct features* that are actionable and have no child tracking:
1. `prewarm(promptPrefix:)` — warm model at backend startup for lower first-token latency. Not implemented (no corresponding code change in fm-bridge main.swift for `--prewarm` flag).
2. `SystemLanguageModel(useCase: .contentTagging)` — specialized tagging model for keywords extraction quality. An A/B experiment worth running.

```bash
gh issue reopen 853 --repo dtubb/fichero
gh issue edit 853 --repo dtubb/fichero --add-label "backend" --add-label "priority:P3"
# Rationale: Both prewarm() and contentTagging are Apple-documented APIs with concrete implementation paths that were deferred, not done
```

### B3. #937 — Two Apple Vision providers listed (consolidate or label, prevent duplicate-add)
**Reopen.** Closed as COMPLETED, but the issue was recently moved back into this milestone (per task instructions: "the new model-centralization #1342 is here too; #1078/#937 Apple Vision provider bugs were just moved here"). The duplicate-add dedup guard and the labelling/consolidation of Apple Vision OCR vs Apple Vision Transcribe entries are core UX improvements worth tracking — especially now that #1342 (model centralization) is being designed, this should be a tracked requirement feeding into that design.

```bash
gh issue reopen 937 --repo dtubb/fichero
gh issue edit 937 --repo dtubb/fichero --add-label "type:bug" --add-label "priority:P2" --add-label "client:swiftui"
# Rationale: Duplicate-add dedup guard + clear labelling of Apple Vision sub-models are unresolved UX gaps; feeds directly into #1342 model centralization design
```

---

## SECTION C — Close as Obsolete / Superseded

### C1. #239 — Promote Providers from dev to beta
**Close.** Created 2026-03-02 as a process gate for the early dev→beta promotion workflow. The branch model has since collapsed to single-trunk `main` with no dev/beta/release channel distinction. "Providers" has shipped in production for months. This gate no longer maps to anything in the current workflow.

```bash
gh issue close 239 --repo dtubb/fichero --comment "Obsolete: the dev→beta→release channel model was retired when we collapsed to single-trunk main (2026-05-30). Provider management shipped and is live. No action required."
```

### C2. #240 — Promote AI Providers UI from dev to beta
**Close.** Same rationale as #239 — same day, same pattern, same obsolete promotion-gate model.

```bash
gh issue close 240 --repo dtubb/fichero --comment "Obsolete: the dev→beta→release channel model was retired. Provider UI is live on main. Companion issue to #239."
```

### C3. #243 — Promote Providers to release if ready
**Close.** Same rationale as #239 and #240. Third in a trio of "promote" process issues that no longer apply.

```bash
gh issue close 243 --repo dtubb/fichero --comment "Obsolete: the dev→beta→release channel model was retired. Companion to #239 and #240 — all three can be closed."
```

---

## SECTION D — Label Fixes

### D1. Add `type:` label (missing entirely)

```bash
gh issue edit 242 --repo dtubb/fichero --add-label "type:task"
# "Add provider QA checklist" — it's a task (write a checklist), not a feature or bug

gh issue edit 484 --repo dtubb/fichero --add-label "type:task"
# "[Release Gate] 0.0.6" — release gate = type:task

gh issue edit 485 --repo dtubb/fichero --add-label "type:task"
# "[Release Gate] 0.0.7" — release gate = type:task

gh issue edit 752 --repo dtubb/fichero --add-label "type:feature"
# "Settings → Local Models tab" — new UI feature

gh issue edit 1152 --repo dtubb/fichero --add-label "type:feature"
# "Model management UI: user-selectable spaCy/embedding models" — new UI capability
```

(Issues #762, #763, #1290 are CLOSED; label gaps on closed issues are lower priority — skip.)

### D2. Add `priority:` label to open issues

```bash
gh issue edit 239 --repo dtubb/fichero --add-label "priority:P3"
# Obsolete promote gate — P3 before closing

gh issue edit 240 --repo dtubb/fichero --add-label "priority:P3"
# Obsolete promote gate — P3 before closing

gh issue edit 242 --repo dtubb/fichero --add-label "priority:P3"
# Provider QA checklist — nice-to-have documentation, P3

gh issue edit 243 --repo dtubb/fichero --add-label "priority:P3"
# Obsolete promote gate — P3 before closing

gh issue edit 283 --repo dtubb/fichero --add-label "priority:P2"
# "Re-enable AI Advanced settings sub-tab" — real user-facing feature that's still gated off; P2

gh issue edit 284 --repo dtubb/fichero --add-label "priority:P2"
# "Re-enable Settings tabs (General/Backend/Models)" — settingsBackend + settingsModels are still false in FeatureManager; P2

gh issue edit 484 --repo dtubb/fichero --add-label "priority:P1"
# "[Release Gate] Providers + API Keys" — core functionality, P1

gh issue edit 485 --repo dtubb/fichero --add-label "priority:P2"
# "[Release Gate] Local Models" — important but less blocking than providers; P2

gh issue edit 572 --repo dtubb/fichero --add-label "priority:P2"
# Sidebar sort_order — will be re-milestoned but needs priority before move

gh issue edit 580 --repo dtubb/fichero --add-label "priority:P2"
# Sidebar drop restore — same

gh issue edit 583 --repo dtubb/fichero --add-label "priority:P3"
# Sidebar test coverage — quality, P3

gh issue edit 585 --repo dtubb/fichero --add-label "priority:P3"
# Sidebar structural cleanup — quality, P3

gh issue edit 732 --repo dtubb/fichero --add-label "priority:P1"
# "Surface provider-side errors in UI" — 429/auth failures silently show "N failures"; this is a real usability gap when workflows fail

gh issue edit 752 --repo dtubb/fichero --add-label "priority:P2"
# "Settings → Local Models tab" — needed for Ollama/local inference path

gh issue edit 799 --repo dtubb/fichero --add-label "priority:P2"
# fm-bridge GenerationSchema — will be re-milestoned but priority needed

gh issue edit 854 --repo dtubb/fichero --add-label "priority:P3"
# Proactive token budgeting — blocked on SDK 26.4; P3 until SDK lands

gh issue edit 1152 --repo dtubb/fichero --add-label "priority:P3"
# Model management UI — needs-design, P3

gh issue edit 1200 --repo dtubb/fichero --add-label "priority:P3"
# Model browser (OpenRouter catalogue) — nice-to-have; P3
```

### D3. Add missing surface label (open issues without client: or backend)

```bash
gh issue edit 485 --repo dtubb/fichero --add-label "area:both"
# "[Release Gate] 0.0.7 — Local Models" — requires both SwiftUI settings panel AND backend discovery

gh issue edit 572 --repo dtubb/fichero --add-label "area:both"
# "Add sort_order to Document; wire sidebar reorder" — backend schema + SwiftUI drag-drop (will be re-milestoned too)

gh issue edit 732 --repo dtubb/fichero --add-label "area:both"
# "Surface provider-side errors in UI" — backend error propagation + SwiftUI display
```

### D4. Additional label corrections

```bash
gh issue edit 242 --repo dtubb/fichero --remove-label "status:ready-for-test"
# "Add provider QA checklist" is open unwritten work, not something ready for test; remove premature status label

gh issue edit 484 --repo dtubb/fichero --remove-label "status:ready-for-test"
# [Release Gate] 0.0.6 — not yet tested/complete; status:ready-for-test implies done

gh issue edit 485 --repo dtubb/fichero --remove-label "status:ready-for-test"
# [Release Gate] 0.0.7 — same as 484

gh issue edit 243 --repo dtubb/fichero --remove-label "backend"
# Promoting providers is not purely backend; label was misleading
```

---

## SECTION E — Issues to Watch / Design Sequencing Notes

These issues are correctly filed, correctly labelled (or nearly so), and open — no commands needed, but worth calling out for sequencing:

**#1342** (model downloads → Application Support/Fichero/models, `needs-design`, P2) is the umbrella for model centralization. It should explicitly track/block #752 (Local Models tab), #1152 (model management UI for spaCy/embeddings), and #485 (release gate for local models). Suggest adding `area:both` and these as linked sub-issues once design is approved.

**#854** (proactive token budgeting, waiting on SDK 26.4) is correctly marked open and `backend`. Once macOS 26.4 SDK ships (expected WWDC 2026 or shortly after), this becomes P1. No label change needed now.

**#799** (fm-bridge GenerationSchema) — re-milestoned to Workflows above, but it unblocks `#842`'s remaining follow-ups in #843. That dependency should be called out in the issue body.

**#283 / #284** (re-enable AI Advanced tab + Settings tabs) — FeatureManager confirms `settingsBackendTabEnabledInternal = false` and `settingsModelsTabEnabledInternal = false`. These are real open work items, not stale. P2 is right.

**#484 / #485** (release gates) — the 0.0.6/0.0.7 version refs in the titles are stale (we collapsed to single-trunk `main`). Suggest renaming:
```bash
gh issue edit 484 --repo dtubb/fichero --title "[Release Gate] Wire: Providers + API Keys"
gh issue edit 485 --repo dtubb/fichero --title "[Release Gate] Wire: Local Models"
```

---

## Full Executable Checklist (copy-paste order)

```bash
# === SECTION A: Re-milestone ===
gh issue edit 572 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 580 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 583 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 585 --repo dtubb/fichero --milestone "Library & Reading Surface"
gh issue edit 799 --repo dtubb/fichero --milestone "Workflows"

# === SECTION B: Reopen ===
gh issue reopen 843 --repo dtubb/fichero
gh issue edit 843 --repo dtubb/fichero --add-label "backend" --add-label "priority:P3"

gh issue reopen 853 --repo dtubb/fichero
gh issue edit 853 --repo dtubb/fichero --add-label "backend" --add-label "priority:P3"

gh issue reopen 937 --repo dtubb/fichero
gh issue edit 937 --repo dtubb/fichero --add-label "type:bug" --add-label "priority:P2" --add-label "client:swiftui"

# === SECTION C: Close obsolete ===
gh issue close 239 --repo dtubb/fichero --comment "Obsolete: the dev→beta→release channel model was retired when we collapsed to single-trunk main (2026-05-30). Provider management shipped and is live."
gh issue close 240 --repo dtubb/fichero --comment "Obsolete: the dev→beta→release channel model was retired. Provider UI is live on main. Companion to #239."
gh issue close 243 --repo dtubb/fichero --comment "Obsolete: the dev→beta→release channel model was retired. Companion to #239 and #240."

# === SECTION D: Label fixes — add type: ===
gh issue edit 242 --repo dtubb/fichero --add-label "type:task"
gh issue edit 484 --repo dtubb/fichero --add-label "type:task"
gh issue edit 485 --repo dtubb/fichero --add-label "type:task"
gh issue edit 752 --repo dtubb/fichero --add-label "type:feature"
gh issue edit 1152 --repo dtubb/fichero --add-label "type:feature"

# === SECTION D: Label fixes — add priority: ===
gh issue edit 283 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 284 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 484 --repo dtubb/fichero --add-label "priority:P1"
gh issue edit 485 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 732 --repo dtubb/fichero --add-label "priority:P1"
gh issue edit 752 --repo dtubb/fichero --add-label "priority:P2"
gh issue edit 854 --repo dtubb/fichero --add-label "priority:P3"
gh issue edit 1152 --repo dtubb/fichero --add-label "priority:P3"
gh issue edit 1200 --repo dtubb/fichero --add-label "priority:P3"

# === SECTION D: Label fixes — add surface ===
gh issue edit 485 --repo dtubb/fichero --add-label "area:both"
gh issue edit 732 --repo dtubb/fichero --add-label "area:both"

# === SECTION D: Label fixes — remove incorrect status ===
gh issue edit 242 --repo dtubb/fichero --remove-label "status:ready-for-test"
gh issue edit 484 --repo dtubb/fichero --remove-label "status:ready-for-test"
gh issue edit 485 --repo dtubb/fichero --remove-label "status:ready-for-test"
gh issue edit 243 --repo dtubb/fichero --remove-label "backend"

# === SECTION E: Rename stale version refs in release gate titles ===
gh issue edit 484 --repo dtubb/fichero --title "[Release Gate] Wire: Providers + API Keys"
gh issue edit 485 --repo dtubb/fichero --title "[Release Gate] Wire: Local Models"
```

---

## Reopen Candidates — Summary for Daniel

| # | Title | Why Reopen |
|---|---|---|
| #843 | Apple Intelligence structured output: polish | 4 concrete deferred sub-items (typed guardrail enum, token usage telemetry, includeSchemaInPrompt, schema pre-validation) — none tracked elsewhere |
| #853 | Apple Intelligence: prewarm() + contentTagging | 2 Apple-documented APIs (prewarm at startup, contentTagging for keywords) never implemented — only filed and closed without code |
| #937 | Two Apple Vision providers listed | Duplicate-add dedup guard + clear sub-model labelling are unresolved; feeds into #1342 model centralization design |
