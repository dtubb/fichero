# GitHub Conventions — Fichero

Source of truth for issues, milestones, branches, and labels in `dtubb/fichero`. Last updated 2026-05-30.

## Milestones — feature-area only, no versions

We do **not** use version-numbered milestones. Versions are tags applied at release time, not buckets for work. Closed historical milestones (`0.0.1`–`0.0.4`) are preserved for release-record searchability; do not reopen.

Active feature milestones (each has a description on GitHub):

| Milestone | Scope |
|---|---|
| KG Single-Path | Typed entity layer, CRUD, claim/entity inspector, ontology browser, epistemology graph, predictions, contradiction triage |
| Mind Palace | RealityKit spatial library (Mac → iOS AR → Vision Pro), notes, drag/connect, viewport persistence |
| MCP | MCP server for outside agents, in-app catalog + run, vision-multimodal scene-render hook |
| Researcher | AI-controlled browser, project tracking, autonomous workflow agents, RAG chat |
| Exporter | Word/PDF/Excel/JSON/Markdown/static-HTML/Netlify export |
| Importers | Cloud-linked importers, release-data flows, XLSX, drag-in polish, pre-catalogued ingest |
| Translation | Translation workflow (DeepL + local), language identification |
| NER | spaCy on-device NER + AI-text/sentiment/plagiarism detection |
| Hermeneutics | Interpretation frameworks, hermeneutic circle, controlled predicate vocab, source-tied annotations |
| Search | Hybrid BM25 + dense retrieval, filters, semantic map, saved searches |
| Image Editing | Crop/rotate/enhance/remove-background/segment, edit chains (non-destructive) |
| Chat | Document-scoped chat, multi-model comparison |
| Workflows | Visual canvas editor, tool nodes, LangGraph chains, batch processing |
| Activity & Automation | Real-time execution view, log stream, triggers, schedules |
| Infrastructure | Auth, rate limiting, observability, migrations, integrations (DEVONthink/Bookends/Tinderbox) |
| Settings & Providers | Provider mgmt, API keys, model catalog, local model discovery |
| Onboarding | Reading-surface polish, toolbar controls, first-run flow |
| Epistemic Platform Expansion | Long-term KG research umbrella |

Roadmap-tier items carry the `roadmap` label, not a milestone.

## Labels — canonical set (38 total)

### Type (one) — what kind of work
- `type:bug` — observed broken behavior
- `type:feature` — new capability
- `type:task` — implementation work (refactor/test/chore)
- `type:qa` — human QA verification request
- `type:question` — decision needed from the human operator

### Priority (one) — urgency
- `priority:P0` — critical, ship-blocking
- `priority:P1` — high
- `priority:P2` — medium
- `priority:P3` — low

### Status (one) — workflow state
- `status:ready`
- `status:in-progress`
- `status:blocked`
- `status:blocked-human` (waiting on the human operator)
- `status:ready-for-test`
- `status:done`
- `status:superseded`

### Assignment — who does it (one of `needs:human` or one `tier:*`)

The flow is: **manager dispatches → agent lane works → human operator tests/decides.** Manager reads `tier:*` to pick which lane to dispatch to. The human queue is `needs:human`. No vendor-specific owner labels — they rot when models change.

- `needs:human` — Human operator does it (decision, validation, QA, manual step)
- `tier:frontier` — Opus / Sonnet 4.6 / GPT-5.5 / Codex 5.3. Architectural, ambiguous, large refactors.
- `tier:medium` — Sonnet-mini / GPT-5 mini / Codex 5.4-mini. Typical implementation tasks.
- `tier:mini` — Haiku / GPT-5-nano. Mechanical, narrow scope, well-specified.
- `tier:local` — oMLX / Apple Intelligence. Free, lower capability. KG extraction, triage, small classification.

Tier labels are vendor-agnostic. The model behind each tier swaps over time; the triage question "what capability does this need?" stays the same.

When an agent task is blocked waiting on the human operator, use `status:blocked-human` — no separate "needs response" label.

### Client / surface (one or more)
- `client:swiftui` — Mac app
- `client:cli` — fichero CLI
- `client:html` — exporter static site + `document_view.html` WebKit pages
- `backend` — Python FastAPI engine
- `mcp` — MCP server protocol surface
- `area:both` — coordinated multi-surface change (e.g. OpenAPI regen + Swift BuildProject)

Reserved for when first issue needs them: `client:ios`, `client:visionos`, `client:web`.

### Cross-cutting
- `roadmap` — far-future; hidden from active board with `-label:roadmap`
- `needs-design` — needs brainstorm → spec → plan before dispatch
- `release-gate` — must close before next release tag
- `legacy-reenable` — parked legacy (revisit at 0.1.0+)

### GitHub defaults — keep
`good first issue`, `help wanted`, `documentation`, `duplicate`, `invalid`, `question`, `wontfix`.

## Migration table (legacy → canonical)

| Legacy | Migrate to |
|---|---|
| `bug` | `type:bug` |
| `enhancement`, `feature` | `type:feature` |
| `chore`, `refactor`, `polish`, `architecture` | `type:task` |
| `High`, `Urgent`, `P0` | `priority:P0` |
| `priority:high`, `P1` | `priority:P1` |
| `priority:medium`, `Medium`, `P2` | `priority:P2` |
| `priority:low`, `Low` | `priority:P3` |
| `agent:claude`, `agent:codex` | drop — replaced by `tier:*` (capability-tier labels are vendor-agnostic) |
| `swiftui`, `frontend`, `ui`, `client`, `area:swiftui-*` (8 of them) | `client:swiftui` |
| `cli` (existing) | `client:cli` |
| `backend`, `area:backend-api`, `area:backend-ingest` | `backend` |
| `both` | `area:both` |
| `ingest`, `kg`, `search`, `workflow` | drop (covered by milestone) |
| `0.0.1` | drop (versions are tags) |
| `agent:ollama`, `agent:pi` | drop (lane-internal noise) |
| `kg-ui-collapse` | drop (temporary marker, all closed) |
| `engine-quality` | drop (covered by `type:task` + Infrastructure) |

Net: 73 → 38 labels. ~45 deleted, ~10 created.

## Branches

- `0.0.2` — current development trunk; all work merges here.
- `main` — release branch; fast-forwarded from `0.0.2` at release time. Do NOT push directly.
- Lane branches: `<lane>-<short-scope>`. Pushed to origin; manager merges from `origin/<branch>`; branch deleted after merge.
- No `feature/issue-NNN`-style branches anymore.

## Issue numbers vs task IDs

Local `TASKS.md` task IDs are session-internal. GitHub issue numbers are canonical. Commit references: `feat: X (#1229)`.

## Release tracking

Release-flow checklist lives in `dtubb/fichero-releases#1`. Do not refile in this repo.

## Manager / lane discipline

See `.claude/CLAUDE.md` and `docs/CLAUDE.md`. Briefly:
- Each lane uses its own worktree (`~/code/fichero-<lane>`); manager from `~/code/fichero-0.0.2`.
- Lane branches push to origin so the manager merges from `origin/<branch>`, not a worktree path.
- Never `gh issue close` until `git log origin/main..HEAD | grep "(#N)"` confirms the merge.
- Lane briefs → `agent-work/dispatch/<date>-<lane>-batch.md`
- Lane outputs → `agent-work/proposals/<date>-<topic>.md`
- Manager handoff → `agent-work/handoff/<date>-manager-resume.md`
