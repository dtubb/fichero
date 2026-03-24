# Fichero — Agent Constitution

## What This Is

Fichero is a macOS document management system with LangChain-powered AI toolchains. Two-part architecture: SwiftUI frontend (`fichero-swiftui/`) + Python FastAPI backend (`fichero-api/`). **Current phase: Planning** — no coding until plan is approved.

**Core constraint:** Never push to main without Daniel's explicit approval. Always work on feature branches.

## How I Think

**Priority order:**
1. Plan before coding. Enter plan mode for non-trivial work.
2. One concern per commit. Small, complete increments.
3. Verify everything: build, test, lint — then mark complete.

## How I Ship

1. Build: `PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765`
2. Test: `PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived`
3. Lint Swift: `swiftlint lint fichero-swiftui/fichero-swiftui/`
4. Lint Python: `ruff check fichero-api/src/`
5. Commit with conventional format: `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`, `style:`
6. Never push to main without Daniel's approval. Feature branches only.

## GitHub Workflow

GitHub Issues is the source of truth for the backlog. All work traces to an issue.

```bash
# Check open issues
gh issue list

# Create issue
gh issue create --title "..." --body "..."

# Start work
git checkout -b feature/NNN-description

# Create PR
gh pr create --title "..." --body "Closes #NNN"
```

**TASKS.md is NOT a duplicate of GitHub.** It is a session-level view — what's active right now, with issue numbers for reference.

## Architecture

```
SwiftUI App → HTTP localhost:8765 → FastAPI → DuckDB/LanceDB
                                             → LangGraph (workflows)
                                             → LiteLLM (100+ providers)
```

Full architecture: `docs/CLAUDE.md` (canonical, detailed), `docs/architecture/`

## Key Paths

| Path | What |
|---|---|
| `VISION.md` | What we're building and why — the bigger picture |
| `AGENTS.md` | Agent operational manual — session startup, all skills, decisions |
| `SOUL.md` | Agent identity and values |
| `USER.md` | About Daniel — who he is, how he works, constraints |
| `STATE.md` | Current branch, focus, next session |
| `TASKS.md` | Session-level tasks (points to GH issues) |
| `MEMORY.md` | Persistent state and decisions |
| `docs/CLAUDE.md` | Full agent guidance (canonical, detailed) |
| `.claude/CLAUDE.md` | This constitution (session rules) |
| `docs/agent-workflow/TODO.md` | Master task list in repo |
| `fichero-swiftui/` | Swift/SwiftUI frontend |
| `fichero-api/src/fichero/` | Python FastAPI backend |

## Visual Verification

Use Peekaboo MCP for screenshot-based visual verification of UI changes:

```bash
# Run as MCP server (stdio transport)
peekaboo mcp serve --transport stdio
```

```json
// Claude Desktop config snippet (Developer → Edit Config):
{
  "mcpServers": {
    "peekaboo": {
      "command": "npx",
      "args": ["-y", "@steipete/peekaboo"],
      "env": {
        "PEEKABOO_AI_PROVIDERS": "openai/gpt-5.1,anthropic/claude-opus-4"
      }
    }
  }
}
```

For quick UI iteration: `briefcase dev` in `fichero-api/` runs the backend without full build.

## Rules I Don't Break

1. Never push to main without explicit approval.
2. Never skip build, test, lint before marking work complete.
3. Never modify generated files manually (`*Generated.swift`, `openapi.json`, the api-client package).
4. Never start coding before a plan exists for non-trivial work.
5. PYTHONPATH must be set to `fichero-api/src` for all Python commands.
