# Docs lane dispatch — 2026-05-30

**You are the docs writer.** Worktree: `~/code/fichero-0.0.2`. Branch: `0.0.2`. Tier: Sonnet (frontier-medium). Audience: **end users** of the Fichero Mac app — humanities researchers, archivists, document-organizing professionals — not developers.

## Output

End-user documentation with screenshots, in `docs/user-guide/` (create if missing). Each major surface gets one Markdown file with embedded screenshots:

```
docs/user-guide/
├── 00-getting-started.md            (install → first library → first import)
├── 10-library-and-import.md         (link vs copy mode, drag-in, folder ingest)
├── 20-reading-and-inspector.md      (the multi-pane layout, inspector tabs, PDF tools)
├── 30-workflows.md                  (workflow library, run a workflow, view results)
├── 40-knowledge-graph.md            (entities, claims, single-path KG, focus state)
├── 50-search-and-chat.md            (semantic search, document-scoped chat)
├── 60-settings.md                   (providers, API keys, models, tiers)
├── 70-mind-palace.md                (RealityKit spatial library, navigation, future iOS/visionOS)
├── 80-research-mode.md              (AI-controlled browser, project tracking)
├── 90-export-and-mcp.md             (static-site export, MCP server for outside agents)
└── images/                          (one folder for all screenshots, named by surface)
```

Each file: ~300–600 words, one screenshot per concept, plain English, no developer jargon. Reference [[github-conventions.md]] feature milestones for naming consistency with the project structure.

## How to take screenshots

1. Use the `computer-use` MCP — `mcp__computer-use__request_access` for "Fichero" first, then `screenshot` and `screenshot_region` for specific UI regions.
2. Save PNGs to `docs/user-guide/images/<surface>-<short-name>.png`. Optimize for clarity, not file size; ~1200px wide is plenty for the static site.
3. **Set up before screenshotting:**
   - Open Fichero with a library that has interesting content (ask the human operator which library — they'll point you at one).
   - Make the app window a consistent size — 1280×800 keeps screenshots readable.
   - Engine must be running with `FICHERO_FEATURE_TIER=dev` so all features show.

## Constraints

- No code edits to the app. Read-only.
- No backend edits while the engine is running ([[feedback_no_backend_edits_during_live_run]]).
- Do NOT take screenshots of the human operator's private library content. Ask them to point you at a public-safe library or seed one with synthetic data first.
- Use the canonical feature names from `docs/agent-workflow/github-conventions.md` (KG Single-Path, Mind Palace, etc.) so the docs match the codebase organization.
- If a surface is gated behind a feature flag (`FICHERO_FEATURE_TIER=dev`), note that in the doc.
- One file per surface; if a file balloons past 800 words, split.

## Process

1. Read `CONSTITUTION.md` to ground the voice + audience.
2. Read `docs/agent-workflow/github-conventions.md` for the canonical feature naming.
3. Walk through the app surface-by-surface; for each, write the doc + capture screenshots.
4. Commit incrementally — one commit per surface file. Commit message format: `docs(user-guide): <surface-name>` (e.g. `docs(user-guide): library and import`).
5. Push to `0.0.2`.

## When done

Write `agent-work/dispatch/2026-05-30-docs-DONE.md` with a list of files produced + screenshot count. Manager reviews; pushes the user-guide to `tubb.ca/fichero` separately.

## Hard rules

- Plain English. Assume reader has used Mac apps before but knows nothing about Fichero.
- Reference the in-app menu / keyboard shortcut for each action ("File → Import…", `⌘O`).
- Screenshots must show real content (no `lorem ipsum`).
- If a feature is broken or unfinished, write what it WILL do but mark a small "🚧 in progress (#NNNN)" callout.
- Acknowledge in this lane: confirm "starting" + which library you'll use for screenshots before producing any docs.
