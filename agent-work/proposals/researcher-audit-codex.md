# Researcher Agent Scaffolding Audit (#1256)

Date: 2026-05-26  
Scope: read-only audit of the current `gpt-mini` worktree

## Verdict

The research scaffold is real, but it is not yet a runnable research system.

Today the codebase provides:
- CRUD for research projects, plans, tasks, steps, sources, notes, and checklists.
- Sandboxed web search, browser navigation, and document fetch primitives.
- Generic ReAct / supervisor / swarm / coordinator workflow wrappers.

It does **not** yet provide:
- A single research-run entry point.
- A planner that turns a topic/term into research scope, archives, locations, and source-evaluation steps.
- Multilingual routing or source evaluation beyond a basic language hint on web search.
- An execution engine that advances a research project through a full research lifecycle.

## What Works Today

### Data model and persistence

`fichero-engine/src/fichero/research_models.py` defines the core objects:
- `ResearchProject`
- `ResearchPlan`
- `ResearchTask`
- `ResearchStep`
- `SearchSource`
- `ResearchNote`
- `ResearchChecklist`

This gives the system a usable persistence shape for research work, and the route handlers already save and retrieve these models.

### CRUD routes

`fichero-engine/src/fichero/api/routes/research_crud.py` supports:
- create/list/get/update/delete projects
- create/list/get/update plans
- create/list/get/update tasks
- create/list/update steps

`fichero-engine/src/fichero/api/routes/research_notes.py` supports:
- create/list sources
- create/list/get/update notes
- create/list/toggle checklist items

### Sandboxed tools

`fichero-engine/src/fichero/api/routes/research_tools.py` and
`fichero-engine/src/fichero/workflows/tools/research.py` implement:
- `web_search`
- `browser_navigate`
- `document_fetch`

Security is not the gap here. The SSRF guard, scheme blocking, redirect validation, and content-size limits are already present.

### Generic agent wrappers

`fichero-engine/src/fichero/workflows/tools/agent.py` provides a generic `react_agent`.
`fichero-engine/src/fichero/workflows/tools/multi_agent.py` provides:
- `supervisor_agent`
- `swarm_agent`
- `agent_coordinator`

These are functional as generic workflow tools.

## What Is Stubbed

### Browser navigation placeholders

The browser path advertises a richer browser flow than it actually has:
- `wait_for_selectors` exists in the config schema, but it is not used.
- `screenshot_base64` is always `None`.

So the tool can fetch and scrape HTML, but it is not a browser automation layer.

### Document fetch is narrow

`document_fetch` can save a fetched document as a `Document` row, but it only does that when the caller already knows the URL and project ID. There is no higher-level research logic around:
- choosing which sources to fetch
- ranking or evaluating fetched sources
- re-trying across languages or archives

### `local_search` is only aspirational

`ResearchStep.tool` includes `local_search`, but there is no implementation path for that tool in the workflow tools or API routes.

## What Is Missing

### No research run entry point

There is no endpoint or service that says:
- start a research run
- accept a topic/term
- build a research plan from that term
- execute the plan
- persist progress/results as a single run

`fichero-engine/src/fichero/api/routes/research_agents.py` only mounts the three sub-routers:
- `research_crud`
- `research_notes`
- `research_tools`

It does not define any orchestration routes of its own.

### No production wiring for the agent tools

The generic agent tools are not connected to the research API surface.
- `react_agent` is only referenced in tests.
- `supervisor_agent` has no runtime callers in the codebase.
- The multi-agent wrappers are not wired into `/api/research`.

So the building blocks exist, but they are not composed into a user-facing research workflow.

### Dev-tier only

`research_agents.router` is mounted in the dev route set in `fichero-engine/src/fichero/api/main.py`.
That means the research API group is **not mounted in the default release tier**.

So even the CRUD/tool surface is not available in the normal release configuration unless the app is running with the dev feature tier enabled.

### No term-to-scope intelligence

The current model has no fields or logic for:
- archives
- locations
- topical term expansion
- multilingual source selection
- source confidence / evaluation scoring

The closest thing to language awareness is:
- `WebSearchRequest.language`

That is only a search-region hint. It does not drive the rest of the pipeline.

### No source evaluation workflow

There is no implemented loop that:
- gathers candidate sources
- compares sources
- scores reliability
- records why a source was accepted or rejected
- revisits the search plan based on evidence quality

`SearchSource.reliability` exists as a field, but it is manual metadata, not an evaluated result.

## Direct Answer: Can a Research Run Be Triggered Today?

**Not as a real research run.**

What exists today is a set of primitives:
- create a project / plan / task / step
- run a sandboxed web search
- navigate a URL
- fetch a document
- attach notes and checklists

What does **not** exist is a single runnable research orchestration path that takes a term and automatically:
- expands the scope into archives / locations / terms
- evaluates sources
- handles multilingual discovery
- drives the plan forward end to end

Also, in the default release tier, the research router is not mounted at all.

## Gap To The Target Experience

The target described in #1256 is closer to:
1. user gives a term
2. system derives related archives, places, and term variants
3. system searches in multiple languages
4. system evaluates sources and records the evidence trail
5. system persists a run with progress, notes, and outputs

The current code only covers step 5 partially, and only when the caller manually assembles the CRUD objects and calls the low-level tools themselves.

## Bottom Line

This is a scaffold, not a finished feature.

The next implementation step should not be “add more tool wrappers.” It should be a real research-run orchestrator with:
- a run model
- a planner
- source-selection logic
- multilingual search/evaluation
- a route or command that triggers the run

