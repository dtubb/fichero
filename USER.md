# USER.md — About Daniel

## Who He Is

Daniel Tubb is a Canadian anthropologist and ethnographer writing a book on the Chocó region of Colombia. His research involves a large, heterogeneous document corpus — fieldwork notes, PDFs, audio, transcripts, references. He needs a native Mac tool that handles all of it intelligently.

He uses multiple Macs and depends on Dropbox for cross-device sync. He is technically sophisticated but not a developer. He directs; agents implement.

He communicates in short messages, often mid-task. Typos are normal. "Go ahead" means go ahead.

## His Research Stack

| Tool | Purpose |
|---|---|
| Tinderbox 11 | Manuscript structure, note linking, word count |
| Slip Box | ~28K coded field notes (read-only archive, Dropbox) |
| Bookends | Reference management (citations, PDFs) |
| DevonThink | Document archive (existing corpus) |
| Fichero | Document management + AI (THIS PROJECT) |
| OmniFocus | Personal task management (NOT manuscript tasks) |
| Claude Code | AI coding assistant |
| OpenClaw / Myco | AI orchestration |
| GitHub | Code version control |
| Dropbox | Cross-device sync |

## How He Works

**Direction over implementation.** Daniel sets priorities and approves plans. Agents build. He reviews before anything ships.

**Phase-gated.** He explicitly approved Phase 0 (planning). Coding starts when he approves the plan. This is not bureaucracy — it's how he maintains oversight of a complex codebase.

**Runs the app himself.** UI testing requires a running macOS app on his machine. Some QA only he can do.

**Values native Mac quality.** He chose SwiftUI specifically. Electron or web wrappers are not acceptable. The app should feel like a Mac app.

**Offline first.** He travels for fieldwork. Cloud dependency is a liability. Local models (Ollama) are a priority.

## Constitutional Rules (Hard Constraints)

1. **Never push to main without explicit approval.** Branch → PR → Daniel reviews → merge.
2. **Never deploy or publish without permission.** No surprises in production.
3. **Never modify generated files.** `*Generated.swift`, `openapi.json`, api-client — regenerate via scripts, never edit manually.
4. **Never skip build/test/lint.** SwiftLint + ruff + pytest + xcodebuild before any PR.
5. **Never start coding before a plan is approved.** Especially for non-trivial work — use plan mode.
6. **Never write manuscript prose.** Fichero processes documents; Daniel writes.
7. **`trash` over `rm`.** Recoverable deletion only.
8. **No external actions without permission.** Don't send emails, post issues publicly, or touch production systems.

## What He Cares About for Fichero

- **It actually works.** Many features were built mid-restructure. Phase 0 exists to know what's solid vs. broken.
- **Local models first.** Ollama integration is P0.
- **Native Mac quality.** SwiftUI conventions, native feel, light and fast.
- **Semantic search that's useful.** Finding documents by meaning, not just filename.
- **Eventual Tinderbox integration.** Link documents to manuscript notes — completing the research stack.

## Current Blockers Daniel Owns

As of 2026-02-28:
- Plan approval (Phase 0 → Phase 1 transition)
- Feature flag scope decisions (30 flags — which tier for each)
- Milestone scope sign-off

Don't start coding until he approves the plan. Surface the plan clearly; let him decide.
