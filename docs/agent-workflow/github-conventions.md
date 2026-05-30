# GitHub Conventions — Fichero

Source of truth for issues, milestones, branches, and labels in `dtubb/fichero`. Last updated 2026-05-30.

## Milestones — feature-area only, no versions

We do **not** use version-numbered milestones. Versions are tags applied at release time, not buckets for work. Closed historical milestones (`0.0.1`–`0.0.4`) are preserved for release-record searchability; do not reopen.

17 active milestones, organized by what kind of work they hold.

### Endpoint-led product epics (11)

Backend-driven feature areas; the UI follows the API.

| Milestone | Scope |
|---|---|
| KG & Hermeneutics | Typed entity layer, CRUD, claim/entity inspector data, ontology browser, epistemology graph, predictions, contradiction triage. **Plus interpretation**: controlled predicate vocab, source-tied annotations, hermeneutic circle. **Plus alternative extractors**: spaCy NER, AI-text/sentiment/plagiarism detection. |
| Search | Hybrid BM25 + dense retrieval, filters, semantic map, saved searches |
| Workflows | Visual canvas editor, tool nodes, LangGraph chains, batch processing. **Plus translation** workflow (DeepL + local) and language-ID nodes — translation is a workflow tool, not a separate epic. |
| Importers | Import TOOLS only — Kreuzberg/Docling/PDF/image loaders, cloud-linked importers (Box, Dropbox), XLSX, drag-in polish, remote SSH backend. The mechanism, not the content. |
| Source Archives | Specific source COLLECTIONS to bring into the library — distinct from Importers (the tools). One milestone entry per curated corpus: Chota Valley maps, Archivo Judicial de Medellin, Mosquera notebooks, Marshall diary, GHC/ACENET, slipbox (Tinderbox-derived), Istmina minería, etc. May depend on Importers tool work landing first. |
| MCP | MCP server for outside agents, in-app catalog + run, vision-multimodal scene-render hook |
| Exporter | Word/PDF/Excel/JSON/Markdown/static-HTML/Netlify export |
| Mind Palace | RealityKit spatial library (Mac → iOS AR → Vision Pro), notes, drag/connect, viewport persistence |
| Researcher | AI-controlled browser, project tracking, notes/sources, autonomous workflow agents, RAG/graph-RAG chat agent |
| Image Editing | Crop/rotate/enhance/remove-background/segment, edit chains (non-destructive pipeline) |
| Settings & Providers | Provider mgmt, API/model selector, API keys, local model discovery, AI Advanced |
| Infrastructure | Auth, rate limiting, observability, migrations, IIIF, multilingual normalization, integrations (DEVONthink/Bookends/Tinderbox) |

### Client-UI surfaces (4)

Each has a distinct user-facing surface, design language, and bug class.

| Milestone | Scope |
|---|---|
| Library & Reading Surface | Sidebar/grid/list/table browser, **PDF viewer** (PDFKit, zoom/pan, scroll-sync, loupe/magnifier, annotations), image preview + magnifier, inspector chrome (Info/Metadata/Content/Artifacts/KG tabs), toolbar + View menu pane controls, divider resize, drag/drop polish, thumbnail prefetch. Use `area:inspector` label for cross-cutting inspector bugs. |
| Chat | Document-scoped chat, multi-model comparison (LLM comparison view), conversation history. **Graph-RAG chat** in the chat window lives here; the agentic version lives in Researcher. |
| Activity & Automation | Real-time execution view, log stream, code output, execution diagrams, event-driven triggers, time-based schedules |
| App Shell | File/Edit/View/Window/Help menus, About panel, keyboard shortcuts cheat sheet, first-run flow, app launch, window state restoration, notifications/toast UI, progress indicators |

### Distinct surfaces (2)

| Milestone | Scope |
|---|---|
| CLI | `fichero` CLI tool: library lifecycle, engine lifecycle (start/stop/restart/status), workflow run, KG queries, ingest commands, output formatting |
| Developer Experience | Agent workflow docs, lane briefs (manager/integrator/reviewer/planner/bugtriage), build scripts (`verify_all.sh`), OpenAPI round-trip (`sync_openapi_schema.sh`), jcodemunch-mcp config, test gates, conventions docs |

Roadmap-tier items carry the `roadmap` label, not a milestone.

### Tagging rules

- An issue gets **one milestone** — the *primary user capability* being built or fixed.
- Endpoint-and-UI work: assign to the milestone whose user story is the main outcome. "Show entity color-coding in inspector" → KG & Hermeneutics (user story is "see entities"); use `area:inspector` label for the surface signal.
- A change to inspector chrome itself (tab bar, layout, scroll) → Library & Reading Surface, regardless of which tab.
- A change to PDF rendering / zoom / scroll-sync → Library & Reading Surface (PDF viewer lives there).
- A translation workflow tool → Workflows (translation is a tool node).
- An NER pipeline change → KG & Hermeneutics (NER is an alternative entity extractor).
- A graph-RAG feature in the chat window → Chat; agentic graph-RAG (autonomous browsing + RAG synthesis) → Researcher.

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
