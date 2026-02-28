# Constitution Changelog

## 2026-02-26 -- Initial Creation

- Created SOUL.md -- Fichero Lead identity, development system orchestrator
- Created USER.md -- Daniel Tubb context, constitutional rules, project context
- Created AGENTS.md -- Team structure, dispatch rules, workflow principles, skills
- Created TOOLS.md -- Development commands, MCP tools, key paths, constraints
- Created MEMORY.md -- Project state, architecture summary, conventions
- Created IDENTITY.md -- Name and role
- Created HEARTBEAT.md -- Empty initial state
- Created tasks/BACKLOG.md -- Initial task backlog
- Created 6 skills: session-start, session-end, build-and-test, pr-workflow, assign-task, task-status
- Created _shared/architecture-summary.md for team agent context

## 2026-02-26 -- Ralph Loop Pass 1: cross-file-consistency

- AGENTS.md: Removed duplicate Constitution Team (was identical to Planning Team), added note that Planning Team doubles as Constitution Team
- AGENTS.md: Added 3 missing skills to skills table (feature-audit, milestone-check, toggle-feature)
- AGENTS.md: Replaced verbose Constitution Improvement Protocol with pointer to session-start skill
- TOOLS.md: Added pylint command (pylintrc exists at fichero-api/.pylintrc, was referenced in SOUL.md but missing from TOOLS.md)
- TOOLS.md: Clarified MCP tools scope -- only available when Claude Code runs from ~/code/fichero with its .claude config, not from this workspace

## 2026-02-26 -- Ralph Loop Pass 2: codebase-ground-truth

- MEMORY.md: Updated commit count 43+ -> 173 (verified via git rev-list)
- MEMORY.md: Updated Swift file count 189 -> 343 (verified via find)
- MEMORY.md: Added Python file count: 116
- MEMORY.md: Added Dev Environment Status section: no .venv, no swiftlint
- USER.md: Updated commit count 43+ -> 173
- BACKLOG.md: Added P0 dev environment setup tasks (venv + swiftlint) as blockers
- BACKLOG.md: Marked constitution consistency review as complete
