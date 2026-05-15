# Constitution — Fichero

## What This Is

Fichero is a native macOS document management system with AI processing. It gives a researcher's document corpus — PDFs, fieldwork notes, audio recordings, images, transcripts, references — a single home with semantic understanding. You can ask a question and find the relevant passage, not just the filename.

Designed for a single researcher first; distribution is a later milestone.

## The Problem

A researcher accumulates a large, heterogeneous document corpus over years of fieldwork — PDFs, fieldwork notes, audio, transcripts, references. These files are scattered across tools and folders. Finding something means remembering where you put it. Connecting a document to a manuscript note means manual work. There is no single place that understands what the documents contain.

Fichero solves this: import everything, extract text and meaning, make it searchable by content, and connect it to the rest of the research stack.

## Where Fichero Fits

The target research infrastructure has several specialized tools. Each does one thing well:

| Tool | Role |
|---|---|
| **Tinderbox** | Manuscript structure, note linking, writing |
| **Slip Box** | ~28K coded field notes (read-only archive) |
| **Bookends** | Reference management, citations |
| **DevonThink** | Existing document archive |
| **Fichero** | Document management + AI processing (this project) |

Fichero begins as the **document layer**. It imports from Bookends and DevonThink, provides semantic search and AI workflows over the full corpus, and will eventually link documents to Tinderbox notes.

As the product matures, it also grows a native note and spatial knowledge layer: first-class notes created by the user or AI, plus map/spatial views that help surface relationships across the library. That turns Fichero from a pure archive into a research workspace without making it the manuscript-writing tool.

The Tinderbox Router is an MCP multiplexer that will connect Fichero to the manuscript system and a research-assistant agent (Escribano). The long-term integration: a document in Fichero gets linked to a Tinderbox note, giving the manuscript system access to source material alongside structure. Right now: get the documents organized and searchable.

## What Fichero Is Not

- **Not a writing tool.** The researcher's prose lives in Tinderbox. Fichero never writes manuscript content.
- **Not a reference manager.** That's Bookends.
- **Not the primary long-form writing app.** Tinderbox remains the main synthesis and manuscript environment. Fichero may still host working notes, AI-authored notes, and research-facing spatial organization.
- **Not a DevonThink replacement.** It complements DevonThink — importing from it is a workflow.
- **Not a cloud service.** It runs locally on macOS. No server, no subscription, no data leaves the machine unless the user opts into a cloud LLM provider.

## What v1.0 Looks Like

A macOS app a researcher actually uses daily:

1. **Imports any document type** in a research corpus (37+ formats: PDF, DOCX, audio, video, images, archives)
2. **Semantic search** across the full corpus — find documents by meaning, not just filename
3. **RAG-based Q&A** — ask questions about documents, get answers with source citations
4. **Native notes + AI workspace** — first-class notes created by the user or AI, with explicit links and provenance
5. **Spatial knowledge layer** — list, icon, table, map, and future spatial/3D views over the same research model
6. **AI workflows** — visual node editor for document processing pipelines (LangGraph)
7. **Offline-first** — works with local models (Ollama) without internet; cloud providers optional
8. **Integrations** — Bookends (import references), DevonThink (archive bridge), Tinderbox Router (link to manuscript)
9. **Native Mac quality** — SwiftUI, fast launch, light resources, feels like it belongs on macOS

## How It Works

One engine, many surfaces.

```
SwiftUI app    fichero CLI    MCP server    (iPad / web — future)
       ↘           ↓            ↙
        HTTP on localhost:8765
                 ↓
         FastAPI engine
         (fichero-engine/src/fichero)
            ├── DuckDB (structured metadata)
            ├── LanceDB (vector embeddings)
            ├── LangGraph (workflow execution)
            ├── KG (entities, claims, relationships)
            └── LiteLLM (100+ LLM providers)
```

- **`fichero-engine/`** — Python FastAPI engine. All logic lives here: storage, AI processing, search, workflow execution, knowledge graph, LLM orchestration.
- **`fichero/`** — SwiftUI macOS app (Xcode project at `fichero/fichero.xcodeproj`).
- **`fichero` CLI** — typed Python CLI at `fichero-engine/src/fichero/cli/` (ships inside the engine package; invoked as `python -m fichero`).
- **MCP server** — planned / in flight; another thin client on the engine.
- **OpenAPI schema** — the contract between the engine and every surface. The Swift client is auto-generated from the engine's schema; the CLI is typed against it. When the engine changes, regenerate — never edit generated code by hand.

There are 3+ surfaces today and more coming. Surfaces render and accept input; the engine owns logic.

## Hard Constraints

These don't change:

1. **Native macOS only.** SwiftUI. Not Electron, not a web app.
2. **Offline-first.** Must work without internet via local models (Ollama). Cloud providers are optional.
3. **The researcher writes; Fichero processes.** The app never generates manuscript prose.
4. **No data leaves the machine by default.** Cloud LLM providers are opt-in, clearly labeled.
5. **Stability before features.** What works must keep working. New features don't break existing ones.
6. **Data must be portable across Macs via Dropbox — no hardcoded paths.**
7. **All logic lives in the engine; clients render only.** Aggregation, dedup, scoping, summarization, KG/entity logic, validation — all backend. A surface (SwiftUI, CLI, MCP, future iPad/web) calls an endpoint and displays the result. If a surface needs to compute something that another surface would also need, it belongs in the engine.

## Execution Governance

Execution tracking and planning are governed in GitHub:

- **Source of truth**: GitHub Issues + Milestones + Project board
- **Not source of truth**: local `PLAN.md`, `TASKS.md`, or `docs/agent-workflow/TODO.md`
- **Local exception**: `STATE.md` is maintained for session continuity/handoff only

## Versioning

GitHub Milestones are the source of truth. Each milestone gets its own branch and worktree at `~/code/fichero-<version>/`. The two-ahead rule: never work more than one milestone ahead of what Daniel is currently testing.

Milestone arc (high level):
- **0.0.x** — Core stable: document management, workflows, KG, CLI, autonomous loops
- **0.1.x** — Data integrity and broader test coverage
- **0.x → 1.0** — Feature completeness, distribution, Tinderbox integration

## What Success Looks Like

- A researcher can find documents half-remembered from fieldwork years ago
- Semantic search returns relevant passages, not just filenames
- Local Ollama models work without internet — useful during fieldwork travel
- The user can inspect user notes and AI-authored notes in the same workspace, with clear provenance and visible relationships
- The app doesn't crash, doesn't lose data, doesn't surprise
- A document in Fichero links to a Tinderbox note — the research stack is complete
