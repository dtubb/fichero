# USER.md — About Daniel

## Who He Is

Daniel Tubb is a Canadian anthropologist and ethnographer writing a book on the Chocó region of Colombia. His research involves a large, heterogeneous document corpus — fieldwork notes, PDFs, audio, transcripts, references. He needs a native Mac tool that handles all of it intelligently.

He uses multiple Macs and depends on Dropbox for cross-device sync. He is technically sophisticated but not a developer. He directs; agents implement.

He communicates in short messages, often mid-task. Typos are normal. "Go ahead" means go ahead.

## His Research Stack

Fichero is the document + AI layer. Around it: **Tinderbox** (manuscript structure, the writing tool), **Slip Box** (~28K coded field notes, read-only archive), **Bookends** (references), **DevonThink** (existing document archive). **OmniFocus** holds personal tasks (not manuscript work); **GitHub** is code + the task backlog; **Dropbox** syncs across his Macs.

## How He Works

**Direction over implementation.** Daniel sets priorities and approves high-level plans. Agents build and commit. He reviews results.

**Runs the app himself.** UI testing requires a running macOS app on his machine. Some QA only he can do.

**Drives the CLI and MCP directly.** Daniel doesn't only use the SwiftUI app — he runs the typed `fichero` CLI from the terminal and (soon) the MCP server from agent contexts. Surfaces are interchangeable to him.

**Multiple surfaces, one engine.** Daniel thinks of Fichero as the engine; the SwiftUI app, CLI, and MCP server are different ways into the same data. Treat them as peers, not as primary-vs-secondary.

**Values native Mac quality.** He chose SwiftUI specifically. Electron or web wrappers are not acceptable. The app should feel like a Mac app.

**Offline first.** He travels for fieldwork. Cloud dependency is a liability. Local models (Ollama) are a priority.

## What He Cares About for Fichero

- **It actually works.** Many features were built mid-restructure. Know what's solid vs. broken.
- **Local models first.** Ollama integration is P0.
- **Native Mac quality.** SwiftUI conventions, native feel, light and fast.
- **Semantic search that's useful.** Finding documents by meaning, not just filename.
- **Eventual Tinderbox integration.** Link documents to manuscript notes — completing the research stack.

## Working With Daniel — Boundaries

The one boundary that is specifically *about him*: **never write his manuscript prose.** Daniel is the author; Fichero processes documents, it does not draft his book. Not a word.

Acting on his behalf in the outside world (emails, public posts, production systems) always needs his go-ahead. The rest of the operational rules — branch discipline, generated files, build/test/lint, `trash` over `rm` — live in `.claude/CLAUDE.md` ("Rules I Don't Break").
