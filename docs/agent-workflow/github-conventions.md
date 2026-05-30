# GitHub Conventions — Fichero

Source of truth for issues, milestones, branches, and labels in `dtubb/fichero`. Last updated 2026-05-30.

## Milestones — feature-area only, no versions

We do **not** use version-numbered milestones. Versions are tags applied at release time, not buckets for work. Closed historical milestones (`0.0.1`–`0.0.4`) are preserved for release-record searchability; do not reopen.

Active feature milestones — split between **endpoint-led product epics** (backend-driven; UI follows the API) and **client-UI-led surfaces** (have their own design + bug class, may touch many endpoints) + a few **distinct surfaces** (CLI, dev tooling, app chrome).

### Endpoint-led (13)

| Milestone | Scope |
|---|---|
| KG Single-Path | Typed entity layer, CRUD, claim/entity inspector data, ontology browser, epistemology graph, predictions, contradiction triage |
| Search | Hybrid BM25 + dense retrieval, filters, semantic map, saved searches |
| Workflows | Visual canvas editor, tool nodes, LangGraph chains, **batch processing** |
| Importers | Cloud-linked importers, release-data flows, XLSX, drag-in polish, pre-catalogued ingest |
| Translation | Translation workflow (DeepL + local), language identification |
| NER | spaCy on-device NER, AI-text/sentiment/plagiarism detection |
| MCP | MCP server for outside agents, in-app catalog + run, vision-multimodal scene-render hook |
| Exporter | Word/PDF/Excel/JSON/Markdown/static-HTML/Netlify export |
| Mind Palace | RealityKit spatial library (Mac → iOS AR → Vision Pro), notes, drag/connect, viewport persistence |
| Researcher | AI-controlled browser, project tracking, notes/sources, autonomous workflow agents, RAG chat |
| Hermeneutics | Interpretation frameworks, hermeneutic circle, controlled predicate vocab, source-tied annotations |
| Image Editing | Crop/rotate/enhance/remove-background/segment, edit chains (non-destructive pipeline) |
| Settings & Providers | Provider mgmt, **API/model selector**, API keys, local model discovery, AI Advanced |
| Infrastructure | Auth, rate limiting, observability, migrations, IIIF, multilingual normalization, integrations (DEVONthink/Bookends/Tinderbox) |

### Client-UI-led surfaces (5)

| Milestone | Scope |
|---|---|
| Library & Reading Surface | Sidebar/grid/list/table browser, inspector chrome (Info/Metadata/Content/Artifacts/KG tabs), toolbar + View menu pane controls, divider resize, drag/drop polish, image preview + magnifier (loupe), thumbnail prefetch. Use `area:inspector` label for cross-cutting inspector-surface bugs. |
| PDF Viewer | PDFKit integration, zoom/pan, page nav, scroll-sync with WebKit transcript, loupe/magnifier, annotations |
| Chat | RAG conversation surface |
| Activity & Automation | Real-time execution view, log stream, triggers, schedules |
| App Shell | File/Edit/View/Window/Help menus, About panel, keyboard shortcuts cheat sheet, first-run flow, app launch, window state restoration, notifications/toast UI, progress indicators |

### Distinct surfaces (2)

| Milestone | Scope |
|---|---|
| CLI | `fichero` CLI tool: library lifecycle, engine lifecycle (start/stop/restart/status), workflow run, KG queries, ingest commands, output formatting |
| Developer Experience | Agent workflow docs, lane briefs (manager/integrator/reviewer/planner/bugtriage), build scripts (`verify_all.sh`), OpenAPI round-trip (`sync_openapi_schema.sh`), jcodemunch-mcp config, test gates, conventions docs |

Roadmap-tier items carry the `roadmap` label, not a milestone. The previous "Epistemic Platform Expansion" milestone was dissolved into the roadmap label since it had no concrete deliverable boundary.

### Tagging rules (avoid double-assignment)

- An issue gets **one milestone** — the *primary user capability* being built or fixed.
- Endpoint-and-UI work: assign to the milestone whose user story is the main outcome. "Show entity color-coding in inspector" → KG Single-Path (the user story is "see entities"); use `area:inspector` label for the UI surface signal.
- A change to inspector chrome itself (tab bar, layout, scroll) → Library & Reading Surface, regardless of which tab it lives in.
- Don't milestone Inspector separately — its data comes from KG/Search/Workflows/etc.; its chrome belongs to Library & Reading Surface.

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
