# Agent Briefing — Fichero

Quick orientation for new sessions. Start with `/session-start` (or a lane variant) — it loads context and reports state. This is the one-screen version.

## Project

Fichero — macOS document management with AI processing (SwiftUI app + Python FastAPI engine).

## Current Phase

**Execution.** Implement milestone issues from GitHub on the current milestone branch. Commit directly after each task — no per-task branches, no PRs.

## Essential Files

| File | Purpose |
|---|---|
| `CONSTITUTION.md` | What Fichero is, what it's not, and what matters |
| `AGENTS.md` | Build/test/lint commands, who-verifies-what |
| `.claude/CLAUDE.md` | Code-navigation policy + hard rules |
| `MEMORY.md` | Conventions, lessons, durable decisions |
| `STATE.md` | Current branch, focus, next session entry point |
| `docs/CLAUDE.md` | Architecture & development guide |

## Task Priority (overrides default lowest-issue-number ordering)

When picking the next task in an autonomous session:

1. **`type:bug` issues** — fix all open bugs before any feature work, regardless of milestone or issue number (`gh issue list --state open --label "type:bug"`)
2. **Current milestone feature issues** — lowest issue number first
3. **Future milestone issues** — only if the current milestone is empty

**Why:** Daniel files bugs via `/bug` while testing the app. Fix them before shipping new features or they pile up and block testing.

## Build / Rules

Build, test, and lint commands live in `AGENTS.md`; the hard rules in `.claude/CLAUDE.md`. (Backend runs on `:8765`; `PYTHONPATH=fichero-engine/src` on every Python command.)
