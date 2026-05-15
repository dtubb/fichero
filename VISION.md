# VISION.md — Fichero

## What We're Building

A native macOS document management system with AI processing — designed for researchers, built for Daniel.

*Fichero* (Spanish: file cabinet, card index) is where documents live, get processed, and become searchable. It is the document layer of Daniel's research infrastructure, sitting alongside Tinderbox (manuscript structure) and the Slip Box (coded field notes).

## The Problem It Solves

Daniel works with a large and heterogeneous document corpus: PDFs, fieldwork notes, audio recordings, images, transcripts, references from Bookends, archives from DevonThink. These files are scattered. Finding something means remembering where you put it. Connecting a document to a Tinderbox note means manual work.

Fichero gives documents a home with semantic understanding — you can ask a question and find the relevant passage, not just the filename.

## The Stack

```
Documents (PDF, DOCX, audio, video, images, 37+ types)
    ↓ import + extract + embed
Fichero engine (fichero-engine/)
    ├── DuckDB (structured metadata)
    ├── LanceDB (vector embeddings, semantic search)
    ├── LangGraph (workflow execution, visual editor)
    ├── KG (entities, claims, relationships)
    └── LiteLLM (100+ providers: Ollama, Anthropic, OpenAI, Groq...)
    ↑ HTTP localhost:8765
Display surfaces (thin clients on the engine)
    ├── SwiftUI app (fichero/ — three-column native macOS)
    ├── fichero CLI (fichero/cli/ — typed, mirrors the HTTP surface)
    ├── MCP server (planned / in flight — for agent tooling)
    └── future: iPad app, web client
    ↓ future integration
Tinderbox Router → Tinderbox (link documents to manuscript notes)
```

### Display Surfaces

The engine is the only place logic lives. Surfaces render and accept input; they do not compute.

- **SwiftUI app** — Daniel's daily driver on the Mac.
- **`fichero` CLI** — typed command-line surface; Daniel uses it directly, agents use it for verification.
- **MCP server** — exposes engine endpoints to MCP-aware agents (Escribano and others).
- **iPad / web** — future surfaces; same engine, different renderers.

## How It Fits Daniel's Research System

```
Slipbox (raw field notes, Dropbox — read-only)
Bookends (references)          → → Fichero (documents, semantic search, AI Q&A)
DevonThink (document archive)  → ↗
    ↓ future
Tinderbox (manuscript structure via Router MCP)
    ↓
Daniel (author — all decisions his)
```

Eventually: Fichero surfaces a relevant document → Daniel links it to a Tinderbox note → Escribano can reference it in manuscript work. The full research stack becomes connected.

## What Fichero Is Not

- It is not a writing tool — Daniel's prose lives in Tinderbox
- It is not a reference manager — that's Bookends
- It is not a note-taking app — that's Tinderbox / Slip Box
- It does not replace DevonThink — it complements it (import from DT is a workflow)
- It does not write manuscript content — constitutional rule

## End State (v1.0)

A macOS app that:
1. Imports and indexes any document type Daniel uses (37+)
2. Provides fast semantic search across the full corpus
3. Answers questions about documents via RAG (with source citations)
4. Runs AI workflows on documents (LangGraph, visual editor)
5. Works offline with local models (Ollama) — no forced cloud dependency
6. Integrates with Bookends (import references), DevonThink (archive bridge), Tinderbox Router (link to manuscript)
7. Runs reliably on macOS with native performance — not Electron, not web

## Versioning Philosophy

GitHub Milestones are the source of truth. Branch and worktree per milestone (`~/code/fichero-<version>/`); two-ahead rule (never work more than one milestone ahead of what Daniel is testing).

Milestone arc:
- **0.0.x** — Core stable: workflows, KG endpoints, CLI, autonomous loops live
- **0.1.x** — Stability: data integrity, broader test coverage of core paths
- **0.x → 1.0** — Feature completeness, distribution, Tinderbox integration
