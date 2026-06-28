# Constitution: Fichero

## What This Is

Fichero is a native Apple document-workbench for researchers. The shipped shape
in this repository is a macOS app backed by a local FastAPI engine, with a
typed CLI and an MCP server over the same backend. The app is for reading,
organizing, searching, and processing research materials such as PDFs, scanned
images, notes, audio, and video.

## What Is Built Now

The codebase already implements these core capabilities:

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

## In Progress

These directions are visible in the repository but are not the stable shipped
core yet:

- **iOS / iPadOS / visionOS client work.** The Xcode project contains those
  targets and cross-platform code paths, but macOS remains the primary, most
  complete surface.
- **Spatial / Mind Palace tooling.** Backend and MCP support exists, but this is
  still an evolving surface, not the central product story.
- **Release packaging and public docs polish.** The repo contains release,
  signing, Sparkle, and docs-site machinery that is still being hardened.

## How It Works

One engine, many clients:

```
SwiftUI app    fichero CLI    MCP server
       \           |            /
        \          |           /
         HTTPS on 127.0.0.1:8765
                 (TLS, pinned)
                   |
                   v
            FastAPI engine
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
4. **Privacy is explicit.** Local-model use is supported. Cloud providers are
   opt-in and user-configured.
5. **Honesty over aspiration.** Public docs describe built behavior first and
   mark incomplete work as planned or in progress.
6. **Stability before expansion.** New features do not justify silent breakage
   in ingest, reading, search, or existing workflows.

## Execution Governance

Execution tracking lives in GitHub:

- **Source of truth:** GitHub Issues, Milestones, and the project board
- **Local continuity only:** `STATE.md`, `MEMORY.md`, and `agent-work/`

## Release State

Fichero is alpha software under active development. The repository contains the
app, engine, docs site, release scripts, and worker workflow used to ship dated
builds, but the right way to describe the product is still: built, usable,
in-progress software, not a finished platform.
