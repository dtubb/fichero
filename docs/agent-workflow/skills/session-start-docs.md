---
name: session-start-docs
description: Orient an end-user documentation agent at session start. Loads the docs dispatch brief, scopes to Markdown + screenshots only, configures computer-use MCP for capturing app screens. Use instead of /session-start when this agent only writes user-facing docs.
---

# /session-start-docs

End-user documentation lane. **This agent writes ONLY user-facing Markdown + screenshots under `docs/user-guide/`.**
No code edits. No backend edits. Read everything else; touch only `docs/user-guide/**/*` + the dispatch DONE file.

---

## Step 0 — BLOCK gate

```bash
if [ -f BLOCK.md ]; then head -n 40 BLOCK.md; fi
```

Stop if first non-empty line starts with `BLOCKED`.

---

## Step 1 — Load context

```bash
pwd && git status && git log --oneline -5
```

Read in order (skip missing):
1. `agent-work/dispatch/2026-05-30-docs-batch.md` — your dispatch brief (the canonical scope, audience, output layout, hard rules)
2. `docs/agent-workflow/github-conventions.md` — canonical feature naming (use these names in your docs)
3. `CONSTITUTION.md` — product north star + voice
4. `STATE.md` — current trunk state (so you know which features are live vs in-progress)
5. `AGENTS.md` — hard rules

---

## Step 2 — Computer-use MCP prep

You will take screenshots via the `computer-use` MCP. Request access for Fichero first:

```
mcp__computer-use__request_access  # ask for "Fichero" + "Finder"
```

Note: clicking inside Terminal/IDE is restricted (tier "click" only); Fichero is tier "full". You can drive the app fully via `left_click`, `key`, `type`, `screenshot`.

Before any screenshot session:
- Confirm Fichero is running (engine on `:8765` with `FICHERO_FEATURE_TIER=dev`).
- Ask the human operator which library to use — never screenshot private content.
- Make the window a consistent size (1280×800 ideal).

---

## Step 3 — Existing docs check

```bash
ls docs/user-guide/ 2>&1 | head
git log --oneline --all -- docs/user-guide/ 2>&1 | head
```

Report what already exists; do not duplicate.

---

## Step 4 — Report and wait

```
SESSION START — Fichero Docs Lane — [date]

BRANCH: [branch]
LANE: end-user documentation — docs/user-guide/**/*.{md,png} only

BRIEF: agent-work/dispatch/2026-05-30-docs-batch.md
AUDIENCE: end users (humanities researchers, archivists), not developers
OUTPUT: ~10 surface guides + screenshots; ~300–600 words per file

EXISTING:
[list of docs/user-guide/ contents — or "none yet"]

NEXT:
- Confirm with human operator which library is screenshot-safe
- Confirm engine is running with FICHERO_FEATURE_TIER=dev
- Start with 00-getting-started.md → 10-library-and-import.md sequence

DOCS RULES:
- Plain English. Reference in-app menus + keyboard shortcuts.
- Use canonical feature names from docs/agent-workflow/github-conventions.md (KG Single-Path, Mind Palace, etc.)
- One commit per surface file: `docs(user-guide): <surface>`
- No screenshots of private content — synthetic / public library only
- Mark unfinished features with "🚧 in progress (#NNNN)" callouts

INTER-AGENT:
- Spot a bug while writing? File a GH issue, don't fix.
- Spot a missing feature? File a `type:feature` issue, don't implement.

Standing by — confirm library + engine state, then start writing.
```

Then wait.

---

## Constraints

- NEVER edit Swift, Python, or generated code
- NEVER edit anything outside `docs/user-guide/**/*` and `agent-work/dispatch/2026-05-30-docs-DONE.md`
- NEVER take screenshots that show private library content
- NEVER push directly to main
- Always commit incrementally — one surface file at a time
- Use canonical feature names from `docs/agent-workflow/github-conventions.md`
