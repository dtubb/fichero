# Issue Triage — 2026-05-30

~160 open issues. Snapshot covers all open items visible via `gh issue list`.

---

## 1. Stale / Parking-Lot (safe to defer, low noise)

These are roadmap placeholders or far-future release gates with no near-term action needed:

- **Release gates #488–#515** (Wire: 0.1.x–0.7.x milestones) — tracking stubs for milestones that don't exist yet. No action until those milestones are scoped.
- **#740** GraphRAG — explicitly parked in title.
- **#657** Remote HPC/SLURM batch — blocked on external infra.
- **#1092–#1095** Multi-user / web/iPad client architecture — roadmap-tier.
- **#1158–#1161** VisionPro, 3D mind palace, RealityKit roadmap — needs design first.
- **#374, #375, #378–#380** 0.1.0 epistemic platform — future milestone only.
- **#461** `_is_safe_url` async — backend hygiene, not blocking anything.

**Recommendation**: bulk-label these `roadmap` or `parking-lot` and hide from default board view.

---

## 2. Duplicates / Already-Closed Work

Issues that overlap recent closures (#1304–#1337 family):

| Open | Likely duplicate of |
|------|---------------------|
| #1327 Simplified MCP interface | #1301 (closed) MCP server follow-ups |
| #1326 CLI ↔ backend parity | #1318 (closed) CLI parity: full KG/inspector ops |
| #1303 extract_all oMLX structured output fails | #1308 (closed) medium cloud tier + context from MEMORY: oMLX can't do JSON Schema |

**#1303** specifically: root cause confirmed — oMLX returns non-OpenAI-compatible format and can't load the required model (memory ceiling). This is an environment constraint, not a code bug. Can be closed or converted to a "track oMLX compatibility" note.

**kg-ui-collapse batch (#1324–#1336)**: These were filed today as next-wave items. Most are distinct features, not duplicates — but #1327/#1326 overlap above.

---

## 3. High-Priority for Next 0.0.2 Push

**Release gates still open (0.0.2 milestone):**
- **#660** Dry-run release: install on Daniel's machine — *must happen before shipping*
- **#659** Build, sign, notarize 0.0.2 DMG — *blocks distribution*
- **#1151** Feature-gate audit: re-enable simple surfaces — needed for clean release state

**Active bugs with `priority:high`:**
- **#1225** Activity Viewer: consolidate tabs into single view with step completion — UI regression visible to Daniel now
- **#1224** Activity viewer: user-facing names instead of internal artifact names — visible regression
- **#1220** Workflow nodes/inspector appear miswired or feature-gated — blocks basic workflow UX
- **#1216** Large folder ingest: data missing after relaunch — data-loss class bug, high severity
- **#1215** Toolbar + View menu pane controls unreliable — daily driver annoyance

**Note:** #1217 (folder timestamp refresh) shows open but the fix landed in commit `73856f0d`. Verify and close.

---

## 4. Feature Requests (Batch These)

Group for a single planning pass rather than ad-hoc dispatch:

- **Workflow controls cluster**: #1226 (stop/pause/delete), #1223 (pause/resume) — file together
- **KG CRUD cluster**: #1258 (edit/delete claims), #916 (user-created entities/claims) — same backend surface
- **Citation cluster**: #1100 (citation extraction workflow), #1101 (BibTeX sidecar), #974 (citation graph) — sequential dependency
- **Activity window polish**: #1264 (standalone live Activity window), #1225/#1224 (already bugs) — one sprint
- **Transcription/OCR cluster**: #938 (transcribe-as-composable), #1145 (OCR model options), #1146 (MLX Swift embed)

---

## 5. Acute Bug Reports (Recently Surfaced, No Fix Yet)

- **#1216** Large folder ingest data missing after relaunch — confirmed open, no fix in recent commits
- **#928** PDF pages: missing loupe/magnifier tools (0.0.2, regression)
- **#721** Inspector shows *parent folder's* container artifacts — KG scoping bug
- **#720** Catalogue workflow finishes with no combined artifact — composable workflow regression
- **#713** Sidebar drag asymmetry (icon/name vs row-body) — broken drag session
- **#598** Sidebar drag-drop: drops always land on selected row not cursor target — longstanding

**Suggested dispatch order for worker**: #1216 (data loss) → #1224/#1225 (Activity UX, both same surface) → #720 (Catalogue artifact) → #928 (PDF tools).

---

---

## 6. Feature-Epic Reorganization

Each epic below: parent issue to use (or propose), child issues, duplicates to close.

---

### KG Single-Path
**Scope**: the read-path collapse + CRUD + scoping work that shipped as #1304–#1323 cluster. Active remainder is CRUD + quality gaps.

**Parent**: #1304 is closed. Propose a new parent "KG: post-consolidation polish + CRUD" OR promote #1258.
**Children (open)**:
- #1258 — Edit/delete KG claims (CRUD + UI) ← natural parent candidate
- #916 — User-created entities/claims (full CRUD parity)
- #1203 — KG entity inspector: temporal + geographic filtering on Map tab
- #1317 — E2E test: full book catalogue + KG end-to-end
- #721 — Bug: inspector shows parent folder's container artifacts (scoping)
- #720 — Bug: catalogue finishes without combined artifact

**Close/retire**: #1303 (oMLX env constraint, not a code bug). Retire milestones: "KG Entities" #31, "KG Claims List" #32, "KG Claim Inspector" #33, "Epistemology Graph" #35 — all have ≤1 open issue each.

---

### Mind Palace
**Scope**: RealityKit spatial library, 2D/3D page cards, Vision Pro/iPad surface. Recent burst (#1297–#1337) is all **closed** — remaining items are roadmap-only.

**Parent**: No active parent. #1158 (roadmap) exists but is future-milestone. Tag open items with Epic=Mind Palace in the Project board; no new parent issue needed until 0.0.4+ scoping.
**Children (open — all roadmap-tier)**:
- #1158 — RealityKit 3D/2D mind palace
- #1160 — Apple Vision Pro + iPad clients
- #511/#512 — Release gate stubs (0.6.0/0.6.1)

**Note**: #1153 (Roadmap: Fichero research-platform vision) is a broad parent for both Mind Palace and Researcher — keep as umbrella. Retire milestone "Spatial Knowledge Layer" #12 (9 open but all roadmap stubs).

---

### MCP
**Scope**: `mcp_server.py` tool surface for outside agents (Claude, MCP clients) + full agentic access.

**Parent**: **#1269** (open, 0.0.3) — "MCP access to the app + agentic chatbot". Use as parent.
**Children (open)**:
- #1338 — Full-featured MCP: complete Fichero tool surface (vision-multimodal hook) ← next major phase
- #1327 — Simplified MCP interface for outside agents ← **partial dupe** of closed #1301; the "simplified surface" angle is subsumed by #1338. Recommend close.
- #1335 — Researcher: next-phase agentic capabilities ← overlaps MCP + Researcher epics; keep as Researcher parent, not MCP child

**Retire**: milestone "0.5.0 - Wire: MCP Servers" #509 (release gate stub).

---

### Static Exporter
**Scope**: Export library to static sites (11ty/generic), plus document export formats. Backend infra is `export_service.py` + `api/routes/export.py`.

**Parent**: **#1334** (open, "Static site exporter 11ty/generic") — more specific than older #475.
**Children (open)**:
- #1336 — Continuous/incremental updates to static site export
- #475 — Export: static HTML website ← **dupe of #1334** (same goal, less specific). Close #475, point to #1334.
- #476 — Netlify deploy (follow-on to #1334)
- #470 — Shared export infrastructure and router (prerequisite)
- #471 — JSON format export
- #473 — Word (.docx) format
- #474 — Excel (.xlsx) format

**Retire**: milestones "Export: JSON + Markdown" #14 and "0.4.x Wire: Export" gate stubs #505–#508.

---

### Importers
**Scope**: Cloud-linked importers (Box, Dropbox), folder-metadata fusion, and drag-in UX polish.

**Parent**: **MISSING** — propose new parent issue: "Epic: Importers — cloud-linked + metadata fusion". Four open children exist.
**Children (open)**:
- #1328 — Drag-in folder/file import smooth UX
- #1329 — Box importer (link, not download)
- #1330 — Dropbox importer (link, not download)
- #1331 — Black folder + Maps folder metadata fusion
- #744 — Tinderbox importer (.tbx → vector DB + KG) ← different surface; could be its own sub-epic

---

### Translation
**Scope**: Workflow tool for document translation (Dutch → English, etc.) with local models + DeepL.

**Parent**: **#1332** (open) — "Translation workflow (Dutch → English, etc.)". Small enough to serve as its own parent.
**Children (open)**:
- #756 — Language identification (prerequisite to routing translation)

No milestone exists. Tag both issues Epic=Translation.

---

### NER (spaCy)
**Scope**: Fast on-device named entity recognition as an alternative/supplement to LLM extractors; model management UI.

**Parent**: **#1333** (open) — "NER with spaCy — fast on-device entity extraction". Use as parent.
**Children (open)**:
- #1152 — Model management UI: user-selectable spaCy/embedding models ← also touches Settings epic
- #753 — Detect AI Text tool
- #754 — Sentiment classifier
- #755 — Plagiarism/near-dupe detection
- #756 — Language identification ← shared with Translation epic

---

### Hermeneutics
**Scope**: Controlled predicate vocabulary, source-tied annotations, interpretations workspace.

**Parent**: #423 ("0.0.4 Interpretations Workspace") is stale and milestone-tagged. Propose new parent: "Epic: Hermeneutics — predicate vocab, annotations, interpretations workspace". Or close #423 and elevate #1124.
**Children (open)**:
- #1124 — Controlled predicate vocabulary distinct from KG verbs (P2, `priority:medium`) ← natural parent
- #1187 — Source-tied notes: per-claim annotation layer
- #375 — Interpretations workspace v1 (0.1.0 roadmap)
- #423 — 0.0.4 Interpretations Workspace ← **near-dupe of #375**. Propose closing #423 in favor of #375.

**Retire**: milestone "Hermeneutics" #37 (replace with Epic field in Project board).

---

### Researcher
**Scope**: Agentic research surface — AI-controlled browser, project tracking, RAG chat.

**Parent**: **#1335** (open, kg-ui-collapse) — "Researcher: next-phase agentic capabilities". Use as parent.
**Children (open)**:
- #1157 — Research agents: project tracking + AI-controlled browser for source discovery
- #1156 — Interactive RAG / graph-RAG chat agent
- #676 — Catalogue workflow: map entities/people/places/timeline per file, reduce

**Umbrella**: #1153 ("Roadmap: Fichero research-platform vision") spans Researcher + Mind Palace; keep as top-level roadmap note, not an active sprint item.

---

## 7. GitHub Projects v2 Reorganization Proposal

**Current state**:
- Project #5 "fichero" exists (private, 55 items), fields: Title + Assignees only — no Epic, Status, Priority.
- 30 milestones: mix of version-based (`0.0.2`, `0.0.3`) and feature-based (`Search v1`, `KG Entities`, `Hermeneutics`, etc.). Many feature milestones have 0 closed issues — never activated.

**Proposed change** (no GH mutations until approved):

### Add three custom fields to Project #5

| Field | Type | Options |
|-------|------|---------|
| **Epic** | Single-select | KG Single-Path, Mind Palace, MCP, Exporter, Importers, Translation, NER, Hermeneutics, Researcher, Onboarding, Settings, Infrastructure, Backlog |
| **Status** | Single-select | Backlog, Ready, In-Progress, Review, Done |
| **Priority** | Single-select | P0-Critical, P1-High, P2-Medium, P3-Low |

### Keep vs retire milestones

**Keep** (version milestones, useful for release tracking):
- `0.0.2 - Backend Merge + Bug Fixes`
- `0.0.3 - KG Navigation + Polish`
- `0.0.3 - Post-LLM-stack`
- `0.0.4 - Local RAG`

**Retire** (close with no-further-work note; issues migrate to Epic field in Project board):
- All `0.1.x–0.7.x Wire:` release gate milestones (#488–#515 stubs) — these were aspirational scaffolding, not a real plan
- Feature-based milestones with 0 closed issues: `KG Entities`, `KG Claims List`, `KG Claim Inspector`, `Epistemology Graph`, `KG Predictions`, `Chat v1`, `Chat v2`, `Local Models`, `Workflow Basics/Editor/Tools/Chains`, `Activity Monitor`, `Automation`, `Batch Processing`, `Ontology Browser`, `Search v2`, `Search v3`, `Providers + API Keys`
- `Spatial Knowledge Layer` (replace with Mind Palace epic)
- `Hermeneutics` (replace with epic field)
- `Export: JSON + Markdown` (replace with Exporter epic)

**Result**: ~8 active milestones (the version ones) instead of 30, with Epic field doing the feature-grouping work that milestones were misused for.

### Issue-to-epic mapping (bulk update targets)

| Epic | Issues |
|------|--------|
| KG Single-Path | #1258, #916, #1203, #1317, #721, #720 |
| Mind Palace | #1158, #1160, #511, #512 |
| MCP | #1269, #1338 |
| Exporter | #1334, #1336, #476, #470, #471, #473, #474 |
| Importers | #1328, #1329, #1330, #1331, #744 |
| Translation | #1332, #756 |
| NER | #1333, #1152, #753, #754, #755 |
| Hermeneutics | #1124, #1187, #375 |
| Researcher | #1335, #1157, #1156, #676 |
| Settings | #1325, #1200, #768, #1059 |

**To close as duplicates**: #1327 (→ #1338), #475 (→ #1334), #423 (→ #375), #1303 (env limitation, not a code bug).

---

*Generated by f_bugtriage, 2026-05-30. No code written. All GH mutations require Daniel's approval.*

## Closed-Issue Re-filing Log — 2026-05-30

**§6 execution by bugtriage lane**

### Summary
- 301 closed issues fetched from version milestones (0.0.2: 293 remaining, 0.0.3: 8 remaining; 0.0.1 already empty from manager)
- All 301 classified by title heuristic and moved to feature milestones
- 61 issues initially failed (milestone name "Onboarding" → renamed to "Library & Reading Surface") — fixed separately
- 57 remaining issues in 0.0.2 moved via Python loop (zsh word-splitting issue in first bash loop)
- 6 issues from closed Hermeneutics milestone → KG & Hermeneutics
- 1 issue from closed NER milestone → Infrastructure
- Total issues processed: ~365

### Feature milestone destinations (from 0.0.2 batch)
| Feature Milestone | Count |
|---|---|
| Infrastructure | 83 |
| Library & Reading Surface | 73 + 57 = 130 |
| KG & Hermeneutics | 48 + 6 = 54 |
| Workflows | 38 |
| Settings & Providers | 22 |
| Activity & Automation | 12 |
| Importers | 10 + 4 = 14 |
| Image Editing | 10 |
| Hermeneutics/NER (merged into above) | 8 |
| Exporter | 2 |
| Mind Palace | 1 |

### Milestones deleted
- 0.0.1 - Core Library (id 9) — was empty
- 0.0.2 - Backend Merge + Bug Fixes (id 8) — cleared 517→0 then deleted
- 0.0.3 (id 50) — cleared 41→0 then deleted
- 0.0.4 - Local RAG (id 49) — was empty
- Hermeneutics (id 37) — merged into KG & Hermeneutics, deleted empty
- Translation (id 58) — already empty, deleted
- NER (id 59) — cleared 1→0 then deleted
- PDF Viewer (id 61) — already empty, deleted

### Labels
All 33 current labels are canonical. No legacy labels found — manager's migration already completed before this run.

### Docs
Removed "Migration table" section from docs/agent-workflow/github-conventions.md (commit: `docs(gh-conventions): remove migration scaffolding`).
