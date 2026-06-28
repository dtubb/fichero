---
name: session-start-swiftui
description: Orient a SwiftUI/frontend agent at session start. Loads KG inspector focus, frontend-only issues, Swift-specific rules. Use instead of /session-start when this agent only touches Swift files.
---

# /session-start-swiftui

Frontend-only session start. **This agent touches ONLY `fichero/fichero/**/*.swift` files.**
Do not edit Python, openapi.json, or generated client sources.

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
1. `STATE.md` — current focus + "Next Session — Start Here (frontend Claude)" section
2. `MEMORY.md` — Swift-relevant entries (SwiftUI patterns, layout gotchas, SwiftLint rules)
3. `AGENTS.md` — hard rules

---

## Step 2 — Open frontend issues

```bash
gh issue list --label frontend --state open --limit 20
```

Report top 3 by priority (pick highest-numbered recent ones unless STATE.md specifies).

---

## Step 3 — Swift health check

```bash
swiftlint lint fichero/fichero/ 2>&1 | tail -5
```

Note any violations. Zero warnings is the bar.

---

## Step 4 — Report and wait

```
SESSION START — Fichero SwiftUI — [date]

BRANCH: [branch]
LANE: frontend — Swift only (fichero/fichero/**/*.swift)

FOCUS: [from STATE.md frontend section]
TOP ISSUES:
  #NNNN [title]
  #NNNN [title]
  #NNNN [title]

SWIFT RULES:
- New .swift files → ruby scripts/add-swift-file.rb <path> (mandatory)
- Three-leg check: swiftlint + xcodebuild + RunAllTests before marking done
- @field_validator mode=before → Pydantic generates *-Input schema variants (don't remove them)
- Never touch fichero-engine/ or openapi.json

INTER-AGENT:
- Need backend work? Write .ai/inbox/for-backend-YYYY-MM-DD.md
- Need CLI test? Write .ai/inbox/for-cli-YYYY-MM-DD.md

What would you like to work on?
```

Then wait.

---

## Constraints

- NEVER edit Python files, openapi.json, or anything under fichero-engine/
- NEVER push directly to main
- NEVER skip swiftlint before committing
- Register every new .swift file with add-swift-file.rb
