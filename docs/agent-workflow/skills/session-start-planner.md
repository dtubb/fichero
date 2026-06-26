---
name: session-start-planner
description: Feature-planning lane for any project — turn a feature request or complex bug into a concrete implementation plan with file targets, sequencing, risks, and required tests before coding begins. Does not write code by default.
---

# /session-start-planner

Planner-only session start. This lane shapes work before implementation.

## Startup Checklist

1. Read project context:
   ```bash
   [ -f VISION.md ] && sed -n '1,40p' VISION.md
   [ -f CONSTITUTION.md ] && sed -n '1,30p' CONSTITUTION.md
   [ -f CLAUDE.md ] && sed -n '1,60p' CLAUDE.md
   ```
2. Read the assigned issue in full.
3. Read relevant architecture docs (check CLAUDE.md for paths like `docs/architecture/`).
4. Map likely files with jCodemunch:
   - `plan_turn { repo: ".", query: "<feature/bug>", model: "<model-id>" }` — confidence + recommended files
   - `search_symbols`, `get_blast_radius` for shared types, `get_class_hierarchy` for inheritance
5. Map the work into safe phases.

## Owns

- Read a feature issue or complex bug in full
- Map likely files and affected surfaces
- Split work into safe phases
- Identify required tests and integration risks
- Hand back a plan the manager can assign to workers

## Does Not Own

- No coding by default
- No final integration
- No general backlog grooming unrelated to the assigned item

## Planning Output

Produce:

- scope summary
- files likely touched
- sequencing / phases
- risk points (especially cross-stack: API changes, schema changes, UI+backend coupling)
- test plan
- suggested worker model tier if useful (frontier for complex/risky, medium for straightforward, small for mechanical)

## Good Use Cases

- cross-stack feature work
- risky UI/layout changes
- API changes that may require client regeneration
- bugs with unclear ownership between frontend/backend
- work that needs to be safely split across multiple workers

## Constraints

- Stay concise
- Prefer actionable implementation steps over essay-style design prose
- If scope is unclear, ask one clarifying question rather than guessing
