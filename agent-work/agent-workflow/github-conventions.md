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

### Distinct surfaces (4)

| Milestone | Scope |
|---|---|
| CLI | `fichero` CLI tool: library lifecycle, engine lifecycle (start/stop/restart/status), workflow run, KG queries, ingest commands, output formatting |
| Documentation | **End-user manual.** macOS Help menu, in-app help text, user-guide markdown (publishes to Website), FAQ. Audience: end users (and AI agents helping them). |
| Developer Experience | **For contributors + lane agents.** Reference docs AND tooling (same audience). Docs: `docs/architecture/`, `docs/CLAUDE.md`, `CONSTITUTION.md`, `docs/agent-workflow/`, lane briefs, conventions. Tooling: `verify_all.sh`, `sync_openapi_schema.sh`, OpenAPI round-trip, jcodemunch-mcp config, test gates, CI hooks. |
| Website | tubb.ca/fichero — public website, release notes, download page, dev blog. Republishes Documentation's user-guide as a static site. |

Roadmap-tier items carry the `roadmap` label, not a milestone.

### Tagging rules

- An issue gets **one milestone** — the *primary user capability* being built or fixed.
- Endpoint-and-UI work: assign to the milestone whose user story is the main outcome. "Show entity color-coding in inspector" → KG & Hermeneutics (user story is "see entities"); use `area:inspector` label for the surface signal.
- A change to inspector chrome itself (tab bar, layout, scroll) → Library & Reading Surface, regardless of which tab.
- A change to PDF rendering / zoom / scroll-sync → Library & Reading Surface (PDF viewer lives there).
- A translation workflow tool → Workflows (translation is a tool node).
- An NER pipeline change → KG & Hermeneutics (NER is an alternative entity extractor).
- A graph-RAG feature in the chat window → Chat; agentic graph-RAG (autonomous browsing + RAG synthesis) → Researcher.

## Labels — canonical set (23 total)

### Type (one) — what kind of work
- `type:bug` — observed broken behavior
- `type:feature` — new capability
- `type:task` — implementation work (refactor / test / chore / docs)

### Priority (one) — urgency
- `priority:P0` — critical, ship-blocking
- `priority:P1` — high
- `priority:P2` — medium
- `priority:P3` — low

### Status (one) — workflow state
- `status:blocked` — blocked on external dependency
- `status:ready-for-test` — merged, awaiting human QA

(Open + unassigned = ready. Assignee = in-progress. Closed = done. `needs:human` covers "waiting on the human operator".)

### Assignment — who does it (one of `needs:human` or one `tier:*`)

Manager reads `tier:*` to pick which lane to dispatch to. The human queue is `needs:human`. Vendor-agnostic — the model behind each tier changes; the triage question "what capability does this need?" stays the same.

- `needs:human` — Human operator does it (decision, validation, QA, manual step)
- `tier:frontier` — Opus / Sonnet 4.6 / GPT-5.5 / Codex 5.3. Architectural, ambiguous, large refactors.
- `tier:medium` — Sonnet-mini / GPT-5 mini / Codex 5.4-mini. Typical implementation.
- `tier:mini` — Haiku / GPT-5-nano. Mechanical, narrow scope, well-specified.
- `tier:local` — oMLX / Apple Intelligence. Free, lower capability. KG extraction, triage.

### Surface (one or more)
- `client:swiftui` — Mac app
- `client:cli` — fichero CLI
- `client:html` — exporter static site + `document_view.html` WebKit pages
- `backend` — Python FastAPI engine
- `mcp` — MCP server protocol surface
- `area:both` — coordinated multi-surface change (e.g. OpenAPI regen + Swift BuildProject)

Reserved (create only when first issue needs them): `client:ios`, `client:visionos`, `client:web`.

### Cross-cutting
- `roadmap` — far-future; hidden from active board with `-label:roadmap`
- `needs-design` — needs brainstorm → spec → plan before dispatch
- `documentation` — docs-related issue

GitHub's close-as-duplicate, close-as-not-planned, and assignee fields cover what the dropped legacy labels used to track.

## Branches

- `main` — the trunk. All work merges here. No separate "release branch" — releases are dated git tags published as DMGs in `dtubb/fichero-releases`.
- Lane branches: `<lane>-<short-scope>`. Pushed to origin; manager merges from `origin/<branch>`; branch deleted after merge.
- `archive-main-2026-05-30` — the previous `main` before the 2026-05-30 trunk consolidation. Kept for history; do not push to it.
- Local worktree paths (`~/code/fichero-worktrees/<name>/`) are independent of branch names — directory naming stays stable across branch renames. (The retired `~/code/fichero-<version>/` bare-sibling pattern is gone — worktrees live ONLY under `~/code/fichero-worktrees/`.)
- No `feature/issue-NNN`-style branches anymore.

## Pull requests — optional, not required

Routine lane work merges directly to `main` (manager does `git merge --no-ff origin/<branch>`). The `feat: X (#1229)` commit message convention auto-cross-links work to the issue on GitHub. PR review happens in-session via the manager + subagents, not on the PR UI.

**Open a PR only when one of these applies:**
- You want a **CI gate to run before merge** (and CI isn't already running on every push to that branch).
- You want **GitHub Copilot Reviewer** to take a pass (paid; separate from session review).
- You want a **conversation surface** for an external contributor (open-source case).

Going-open-source future: when external contributors arrive, switch to PR-required for all non-Daniel work. The current convention is solo-optimised; future-Daniel can promote PRs to standard without breaking the existing commit-cross-ref pattern.

## CI strategy — Linux-only on GH Actions, Mac stays local

GH Actions free tier = 2000 Linux-min/month. Mac runners cost 10× (= 200 effective Mac-min/month free, then **billed in real dollars**). **Don't run Mac builds on GH Actions.** Mac work stays local — Daniel's machine, lane worktrees, `mcp__xcode__BuildProject` via the Xcode MCP. That's already the working pattern.

**GH Actions runs (Linux, free, every push to any branch):**
- `ruff check fichero-engine/src/`
- `pytest fichero-engine/tests/unit/ -k "not slow"` (skip ML-heavy suites — see [[feedback_no_full_pytest_on_daniels_machine]])
- OpenAPI drift: regen `openapi.json` from the FastAPI app, diff vs the committed one → catches the [[feedback_backend_merge_needs_swift_build]] failure mode without needing a Swift build

Each push: ~1-2 min of Linux minutes. Well within free tier even with many pushes/day.

**Stays local on Daniel's Mac (or lane worktrees):**
- `swiftlint` — runs in the lane via `swiftlint lint fichero/fichero/`
- `xcodebuild build` / `xcodebuild test` — via `mcp__xcode__BuildProject` (shares Xcode's cache, fast)
- Full-suite backend pytest — NEVER on Daniel's machine ([[feedback_no_full_pytest_on_daniels_machine]]); tiny `-k` subsets only

**Doesn't run anywhere automated:**
- `RenderPreview` ([[feedback_renderpreview_app_launch_blocked]] — app-launch timeout, broken)
- XCUITest ([[feedback_xcuitest_tcc_automation_grant]] — needs TCC grant, headless can't)

The honest contract: GH Actions catches Python/contract bugs cheap; the human-driven Mac build + the manager's review pass catch the Swift side.

## Where ideas + features live: GitHub Issues, NOT the filesystem

Filesystem files get lost. Search is poor. They're invisible to outside readers when the project goes open source. **Use GitHub Issues as the durable home for:**

- **Feature ideas** — file as `type:feature`. The issue body IS the spec.
- **Architectural proposals** — file as `type:task` + `needs-design`. Comment thread = the discussion.
- **Bug reports** — `type:bug`. Repro, expected/actual, screenshots.
- **Decision logs** — close the relevant issue with a comment that captures the decision + the commit SHA that implemented it.

**Filesystem is only for ephemeral operational artifacts:**
- `agent-work/dispatch/<lane>-batch.md` — lane briefs (operational; the corresponding GH issue holds the durable scope).
- `agent-work/proposals/<topic>.md` — drafts while a proposal is being shaped, then promoted to a GH issue and the file becomes vestigial.
- `agent-work/handoff/<date>-manager-resume.md` — session-to-session continuity (manager-internal, not feature-durable).
- `STATE.md` / `HISTORY.md` / `MEMORY.md` — agent + project session state (NOT product knowledge).

**Rule of thumb:** if a future open-source contributor would benefit from knowing this, it goes in a GH issue. If only the next manager session needs it, filesystem is fine.

## Self-documenting on GH for future open source

Future-Daniel may open this repo to outside contributors. Bake self-documentation into the workflow now so the open-sourcing pivot is cheap:

- Milestone descriptions explain what each feature area IS (already done).
- Label descriptions tell newcomers what each label means (already done).
- Issue titles use plain English, not internal jargon.
- Closed issues link to the commit + any companion PR that shipped them.
- The `docs/` tree is structured by audience (Documentation = end users, Developer Experience = contributors, Website = tubb.ca content).
- Branch + tag history tells the version story (release tags `v0.0.2`, archive tags `archive/main-2026-05-30`).

If the repo would confuse a stranger reading `https://github.com/dtubb/fichero/issues?q=label:type:feature`, that's a signal something needs better labels, milestones, or descriptions.

## Issue numbers vs task IDs

Local `TASKS.md` task IDs are session-internal. GitHub issue numbers are canonical. Commit references: `feat: X (#1229)`.

## Release tracking

Release-flow checklist lives in `dtubb/fichero-releases#1`. Do not refile in this repo. Release tags follow `vX.Y.Z` (annotated).

## Manager / lane discipline

See `AGENTS.md` and `docs/CLAUDE.md`. Briefly:
- Each lane uses its own worktree (`~/code/fichero-<lane>`); manager from `~/code/fichero`.
- Lane branches push to origin so the manager merges from `origin/<branch>`, not a worktree path.
- Never `gh issue close` until `git log origin/main..HEAD | grep "(#N)"` confirms the merge.
- Lane briefs → `agent-work/dispatch/<date>-<lane>-batch.md` (ephemeral; the GH issue carries the durable scope).
- Lane outputs → `agent-work/proposals/<date>-<topic>.md` (drafts; promote to GH issues when ready for discussion).
- Manager handoff → `agent-work/handoff/<date>-manager-resume.md` (session-to-session only).
