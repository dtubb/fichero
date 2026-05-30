# GitHub Conventions — Fichero

This is the source of truth for how issues, milestones, branches, and labels are organized in `dtubb/fichero`. Last updated 2026-05-30.

## Milestones — feature-area only, no versions

We do **not** use version-numbered milestones (`0.0.1`, `0.0.2`, etc.). Versions are tags applied at release time, not buckets for work.

Active feature milestones (each has a description on GitHub):

| Milestone | Scope |
|---|---|
| **KG Single-Path** | Typed entity layer, claim/entity CRUD, claim inspector, ontology browser, epistemology graph, predictions, contradiction triage |
| **Mind Palace** | RealityKit spatial library (Mac → iOS AR → Vision Pro), notes, drag/connect, viewport persistence |
| **MCP** | MCP server surface for outside agents, in-app catalog + run, vision-multimodal scene-render hook |
| **Researcher** | AI-controlled browser, project tracking, autonomous workflow agents, RAG/graph-RAG chat |
| **Exporter** | Word/PDF/Excel/JSON/Markdown/static-HTML/Netlify export |
| **Importers** | Cloud-linked importers (Box/Dropbox), release-data import flows, XLSX, drag-in polish, pre-catalogued ingest |
| **Translation** | Document translation workflow (DeepL + local), language identification |
| **NER** | spaCy on-device NER + AI-text/sentiment/plagiarism detection |
| **Hermeneutics** | Interpretation frameworks, hermeneutic circle, controlled predicate vocab, source-tied annotations |
| **Search** | Hybrid BM25 + dense retrieval, filters, semantic map, saved searches |
| **Image Editing** | Crop/rotate/enhance/remove-background/segment, edit chains (non-destructive) |
| **Chat** | Document-scoped chat, multi-model comparison |
| **Workflows** | Visual canvas editor, tool nodes, LangGraph chains, batch processing |
| **Activity & Automation** | Real-time execution view, log stream, triggers, schedules |
| **Infrastructure** | Auth, rate limiting, audit logging, migrations, observability, integrations (DEVONthink/Bookends/Tinderbox) |
| **Settings & Providers** | Provider mgmt, API keys, model catalog, local model discovery |
| **Onboarding** | Reading-surface polish, toolbar/pane controls, first-run flow, app-startup quality |
| **Epistemic Platform Expansion** | Long-term KG research umbrella (graph reasoning, latent inference, IIIF) |

Closed historical milestones (`0.0.1`, `0.0.2`, `0.0.3`, `0.0.4`) are preserved with their closed-issue history for release-record searchability. Do not reopen them.

Roadmap-tier items (release gates, far-future targets) carry the `roadmap` label, not a milestone.

## Labels — canonical set

GitHub Issues uses these labels and only these. Anything else is being phased out.

### `type:*` — what kind of work (exactly one)
- `type:bug` — observed broken behavior
- `type:feature` — new capability
- `type:task` — implementation work that's not bug/feature (refactor, test, chore)
- `type:qa` — human QA verification request
- `type:question` — needs a decision from Daniel

### `priority:*` — how urgent (exactly one)
- `priority:P0` — critical, ship-blocking, drop everything
- `priority:P1` — high, this milestone
- `priority:P2` — medium, next milestone
- `priority:P3` — low, eventual

### `status:*` — workflow state (exactly one — usually managed by lane)
- `status:ready` — scoped, ready to dispatch
- `status:in-progress` — actively being worked on by a lane
- `status:blocked` — blocked on external dep
- `status:blocked-human` — waiting on Daniel
- `status:ready-for-test` — code merged, awaiting Daniel QA
- `status:done` — completed and verified
- `status:superseded` — replaced by a newer issue

### `area:*` — where the change lives (one or more)
- `area:backend` — Python / FastAPI / DuckDB / LanceDB
- `area:frontend` — SwiftUI / macOS app
- `area:cli` — `fichero` CLI
- `area:both` — frontend + backend touch points

### Cross-cutting
- `roadmap` — far-future; hidden from active board (`-label:roadmap`)
- `needs-design` — needs brainstorm→spec→plan before any lane picks it up
- `release-gate` — must close before next release tag
- `legacy-reenable` — parked legacy work (visited on 0.1.0+)
- `good first issue`, `help wanted`, `documentation`, `duplicate`, `invalid`, `question`, `wontfix` — GitHub defaults; keep.

### Phasing out (bugtriage migrates → canonical)
| Legacy | Migrate to |
|---|---|
| `bug` | `type:bug` |
| `enhancement` / `feature` | `type:feature` |
| `chore` / `refactor` / `polish` | `type:task` |
| `High` / `priority:high` / `Urgent` / `P0` / `P1` | `priority:P0` (Urgent) or `priority:P1` (High) — judgment per-issue |
| `Medium` / `priority:medium` / `P2` | `priority:P2` |
| `Low` / `priority:low` | `priority:P3` |
| `agent:claude` / `agent:codex` | `owner:claude` / `owner:codex` (kept as ownership) |
| `agent:ollama` / `agent:pi` | drop (lane-internal noise) |
| `swiftui` / `frontend` / `ui` / `client` / `area:swiftui-*` | `area:frontend` |
| `backend` / `area:backend-api` / `area:backend-ingest` | `area:backend` |
| `both` | `area:both` |
| `cli` | `area:cli` |
| `ingest` / `kg` / `search` / `workflow` / `architecture` | drop — covered by milestone |
| `0.0.1` | drop — version, not a label |
| `kg-ui-collapse` | drop — temporary marker, cluster closed |
| `engine-quality` | drop — covered by `type:task` + Infrastructure milestone |

### Ownership (optional but useful)
- `owner:daniel` — needs Daniel's hands or decision
- `owner:codex` — assigned to a Codex lane
- `owner:claude` — assigned to a Claude lane (manager / planner / reviewer / bugtriage / opus / sonnet / haiku)
- `needs:daniel-response` — Codex waiting on Daniel input
- `needs:codex-action` — Daniel provided input; Codex should act

## Branches

- `0.0.2` — current development trunk. All work merges here.
- `main` — release branch. Fast-forwarded from `0.0.2` at release time. Do NOT push directly.
- Lane branches: `<lane>-<short-scope>`, e.g. `gpt-inspector-style`, `opus-realitykit-design`, `codex53-mcp-full-vision`. Pushed to origin so the manager can `git fetch origin <branch>` cleanly. Deleted after merge.
- Old `feature/issue-NNN`-style branches are not used anymore — work goes straight to a lane branch.

## Issue numbers ≠ task IDs

Local `TASKS.md` task IDs (e.g. task #264) are session-internal. GitHub issue numbers (e.g. #1229) are the canonical reference. When committing, reference issues: `feat: X (#1229)`.

## Release tracking

Release-flow checklist lives in `dtubb/fichero-releases#1`. Do not refile in this repo.

## Manager / lane discipline

See `.claude/CLAUDE.md` and `docs/CLAUDE.md`. Briefly:
- Each lane operates from its own worktree (`~/code/fichero-<lane>`); manager from `~/code/fichero-0.0.2`.
- All lane branches push to origin so the manager merges from `origin/<branch>`, not a worktree path.
- Never `gh issue close` until `git log origin/main..HEAD | grep "(#N)"` confirms the merge.
- Lane briefs live in `agent-work/dispatch/<date>-<lane>-batch.md`.
- Lane outputs (proposals, audits) live in `agent-work/proposals/<date>-<topic>.md`.
- Handoff briefs (manager → manager across sessions) live in `agent-work/handoff/<date>-manager-resume.md`.
