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
Fichero (THIS PROJECT)
    ├── DuckDB (structured metadata)
    └── LanceDB (vector embeddings, semantic search)
    ↓ query + workflow
SwiftUI macOS App (native, fast, three-column layout)
    ↔ FastAPI backend (localhost:8765)
    ↔ LangGraph (visual workflow editor)
    ↔ LiteLLM (100+ providers: Ollama, Anthropic, OpenAI, Groq...)
    ↓ future integration
Tinderbox Router → Tinderbox (link documents to manuscript notes)
```

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

## Current State (Phase 0 — Feb 2026)

Major restructure complete (codex branch merged). The app exists and has many features in various states. Phase 0 is about understanding what works, what's broken, and designing a clear path to v1.0.

30 feature flags have been designed. Milestones M0–M4 are planned. No coding until the plan is approved.

## Versioning Philosophy

- **M0 (v0.0.1)** — Core stable: document management works reliably, advanced features safely disabled
- **M1 (v0.1.0)** — Stability: data integrity, 100% test coverage of core
- **M2** — Feature completeness: all planned features working and tested
- **M3** — Distribution: packaged, signable, ready for others
- **M4 / v1.0** — Full vision realized: integrated with Tinderbox, polished, documented
