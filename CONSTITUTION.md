# Constitution: Fichero

## What This Is

Fichero is a native Apple document-workbench for researchers. The app is aa SwifUI app with a local FastAPI engine, a typed CLI, and an MCP server over the same backend. The app is for reading, organizing, searching, and processing research materials such as PDFs, scanned
images, notes, audio, and video.

## What Is Built

The codebase has these core capabilities:

1. **Document ingest.** The engine imports 37 file extensions across images,
   documents, word-processing files, ebooks, audio, and video.
2. **Reader and library UI.** The app browses a document library and renders
   PDFs, page images, extracted text, artifacts, and inspector panes.
3. **Semantic search.** The engine stores embeddings in LanceDB and exposes
   search routes the app and CLI use.
4. **Knowledge graph.** The engine extracts and stores entities, claims, and
   graph relationships with provenance back to source documents.
5. **AI workflows.** Workflow definitions, execution routes, and a SwiftUI
   workflow editor all exist in the current tree.
6. **Chat and model tools.** The backend exposes chat and provider routes, and
   the app includes chat and model-management surfaces.
7. **Multiple clients.** The same engine is consumed by the macOS app, the
   `python -m fichero` CLI, and `fichero-mcp`.

## How It Works

One engine, many clients:

```
SwiftUI app       CLI     MCP server
       \           |            /
        \          |           /
      The Fast API Fichero Engine
        (fichero-engine/src/fichero)
           | DuckDB + LanceDB
           | workflows
           | knowledge graph
           | provider integrations
```

- **`fichero-engine/`** owns ingest, storage, workflows, search, knowledge
  graph, and model/provider orchestration.
- **`fichero/`** is the native Apple client. On macOS it prefers the embedded
  local engine; non-macOS targets currently connect to an external backend.
- **`python -m fichero`** is a typed CLI over the same HTTP surface.
- **`fichero-mcp`** exposes that same surface to MCP-aware tools and agents.
- **OpenAPI** is the contract between engine and clients. Generated client code
  is derived from the backend schema, not edited by hand.

## Hard Constraints

These do not change:

1. **Native clients, not a web wrapper.** The app is built with SwiftUI first,
   with AppKit or UIKit bridges only where needed.
2. **The engine owns the logic.** Storage, ingest, search, workflows, KG, and
   validation live in the backend; clients render and collect input.
3. **The researcher stays in charge.** Fichero helps process and surface source
   material; it does not replace the user's interpretation.

## Execution Governance

Execution tracking lives in GitHub:

- **Source of truth:** GitHub Issues, Milestones, and the project board
- **Local continuity only:** `STATE.md`, `MEMORY.md`, and `agent-work/`

## Release State

Fichero is in Public Beta, under active development. The repository contains the
app, engine, docs site, release scripts, and worker workflow used to ship dated
builds. But, Fichero is usable, in-progress software. It is not finished.
