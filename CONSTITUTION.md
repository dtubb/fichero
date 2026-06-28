# Constitution: Fichero

## What This Is

*Fichero* (Spanish: file cabinet, card index) is a native macOS document management system with AI processing. It gives a researcher's document corpus (PDFs, fieldwork notes, audio recordings, images, transcripts, references) a single home with semantic understanding. You can ask a question and find the relevant passage by its content.

## The Problem

A researcher accumulates a large, heterogeneous document corpus over years of fieldwork: PDFs, fieldwork notes, audio, transcripts, references. These files are scattered across tools and folders. Finding something means remembering where you put it. Connecting a document to a manuscript note means manual work. There is no single place that understands what the documents contain. Fichero solves this: import everything, extract text and meaning, make it searchable by content, and connect it to the rest of the research stack.

## Where Fichero Fits

Fichero begins as the **document layer**. It imports, provides semantic search, and AI workflows over the full corpus, and allows for a knowledge graph. As the product matures, it also grows a native note, spatial knowledge layer: first-class notes created by the user or AI, plus map/spatial views that help surface relationships across the library. That turns Fichero from a pure archive into a research workspace without making it the manuscript-writing tool.

## What v1.0 Looks Like

A macOS app a researcher actually uses daily:

1. **Imports any document type** in a research corpus (37+ formats: PDF, DOCX, audio, video, images, archives)
2. **Semantic search** across the full corpus: find documents by their content and meaning
3. **Graph and RAG-based Q&A**: ask questions about documents, get answers with source citations
4. **Native notes + AI workspace**: first-class notes created by the user or AI, with explicit links and provenance
5. **Spatial knowledge layer**: list, icon, table, map, and future spatial/3D views over the same research model
6. **AI workflows**: visual node editor for document processing pipelines (LangGraph)
7. **Offline-first**: works with local models (Apple Intelligence, embedded, Ollama, OMLX, LM Studio) without internet; cloud providers optional
8. **Native Mac quality**: SwiftUI for front end, Python for engine.

## How It Works

One engine, many surfaces.

```
SwiftUI app    fichero CLI    MCP server    (iPad / web: future)
       ↘           ↓            ↙
   HTTPS on 127.0.0.1:8765  (TLS, pinned fail-closed)
                 ↓
         FastAPI engine
         (fichero-engine/src/fichero)
            ├── DuckDB (structured metadata)
            ├── LanceDB (vector embeddings)
            ├── LangGraph (workflow execution)
            ├── KG (entities, claims, relationships)
            └── LangChain (100+ LLM providers via provider integrations;
                           LiteLLM is cost/pricing only, not routing)
```

- **`fichero-engine/`**: Python FastAPI engine. All logic lives here: storage, AI processing, search, workflow execution, knowledge graph, LLM orchestration.
- **`fichero/`**: SwiftUI macOS app (Xcode project at `fichero/fichero.xcodeproj`).
- **`fichero` CLI**: typed Python CLI at `fichero-engine/src/fichero/cli/` (ships inside the engine package; invoked as `python -m fichero`).
- **MCP server**: live (`fichero-mcp` entry point at `fichero-engine/src/fichero/mcp_server.py`); another thin client on the engine.

- **OpenAPI schema**: the contract between the engine and every surface. The Swift client is auto-generated from the engine's schema; the CLI is typed against it. When the engine changes, regenerate. Never edit generated code by hand.

## Hard Constraints

These don't change:

1. **Native macOS only.** For Mac App, use SwiftUI, and if necessary AppKit. Not Electron, not a web app.
2. **Offline-first.** Must work without internet via local models (Ollama). Cloud providers are optional.
3. **The researcher writes; Fichero processes.** The app never writes prose in the user's voice.
4. **No data leaves the machine by default.** Cloud LLM providers are opt-in, clearly labeled.
5. **Stability before features.** What works must keep working. New features don't break existing ones.
6. **All logic lives in the engine; clients render only.** Aggregation, dedup, scoping, summarization, KG/entity logic, and validation all live in the backend. A surface (SwiftUI, CLI, MCP, future iPad/web) calls an endpoint and displays the result. If a surface needs to compute something that another surface would also need, it belongs in the engine.

## Execution Governance

Execution tracking and planning are governed in GitHub:

- **Source of truth**: GitHub Issues + Milestones + Project board
- **Not source of truth**: local planning files (`PLAN.md`, `TASKS.md`, `agent-work/agent-workflow/` notes)
- **Local exception**: `STATE.md` is maintained for session continuity/handoff only

## Versioning

The destination is **dated releases** (CalVer, e.g. `2026.05.01`). A dated snapshot is a known-good build with document management, workflows, KG, CLI, and the autonomous loops working together. That's the model for the **final release**; it is not fully in place yet. Current development runs on `main` (the `0.0.2` working line was merged to `main` via PR #2652 on 2026-06-26), and day-to-day work is organized per worker/lane.

- Current working branch + worktree mechanics → `AGENTS.md` ("Rules I Don't Break")
- Release / packaging process (signing, notarize, Sparkle, DMG) → `docs/architecture/release-process.md` (the pipeline itself lives in the separate `fichero-releases` repo)