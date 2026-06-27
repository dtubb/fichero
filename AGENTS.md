# AGENTS.md: Operational Manual

How to *operate* on Fichero: verify, commit, ship-safety. The product north-star is `CONSTITUTION.md`; code-navigation policy, hard rules, and key paths live in `.claude/CLAUDE.md` (already in every session's context); the detailed guide is `docs/CLAUDE.md`. The session-start / manager skills tell each lane its job. None of that is repeated here.

Every agent starts with `/session-start` (or a lane variant: `-manager`, `-worker`, `-integrator`, `-auto`); it loads context and reports state. Work happens on the milestone branch this worktree is on. Commit directly, no per-task branches.

---

## Who Verifies What

- **Worker**: lints and tests **only its own diff**, then commits. Backend: `ruff check` + `pytest` on the area you touched. Swift: `swiftlint`. A worker does not compile the whole app or run the full suite.
- **Manager / integrator**: owns the Xcode build, the full `FicheroTests` run, and the cross-stack gate before anything merges (one Xcode, the backend on :8765).

```bash
# Backend — PYTHONPATH=fichero-engine/src on every Python command
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived
bash fichero-engine/scripts/start_backend.sh   # server (serves HTTPS; app pins it fail-closed — never bare uvicorn/HTTP, #2538)

# Swift — lint your diff; the manager runs the build + test (prefer the Xcode MCP)
swiftlint lint fichero/fichero/
```

- **Backend API changed?** Regenerate the committed client or the Swift build breaks: `./fichero-engine/scripts/sync_openapi_schema.sh` (change API → sync → commit regen).
- **Ship tests with the change.** Every SwiftUI fix or feature lands with new/updated unit tests in the same commit; write the failing test first for a bug. Test the logic (state, predicates, builders, ID parsing) rather than the rendered pixels, and eyeball pixels by running the built app.
- **Risky diff?** Anything touching auth, file I/O, network, secrets, or keychain → run `/security-review`.

---

## Pydantic + OpenAPI Discipline

Three failure modes that bite *silently*, with no exception and no test failure, just data that vanishes or rows that hide. Load-bearing, not style:

1. **Declare every field on the Pydantic model.** `extra="allow"` lets unknown fields write at runtime, but `model_dump()` only serializes declared fields, so the next read drops them. Add the DB column + the model field + the OpenAPI-typed schema field in the same commit. (`feedback_pydantic_field_must_be_declared.md`)
2. **Swift wrappers set OpenAPI-typed fields, not `additionalProperties`.** Declared fields dumped into `additionalProperties` round-trip on the wire, but the backend Pydantic model ignores them, so the write is lost. (`docs/architecture/swiftui/api_client.md`)
3. **Endpoint defaults matched by strict equality against seed data are foot-guns.** A `folder_path: str = "/"` default silently stops returning rows the moment seed JSON shape changes. Default `Optional[T] = None`, filter only when the caller passes a value, add a regression test. (#722 → #723)

When seed-data shape changes, the shape change and every filter that reads it ship together.

---

## Two-Stack Rule

Before completing a backend route change: does OpenAPI need updating? Do the Swift generated files need regenerating? Do frontend callers need updating? Plan first for architectural, OpenAPI-schema, feature-flag-tier, or database-schema changes; proceed directly on clear-root-cause fixes, tests, and lint/build fixes.

**Engine bug or rendering bug?** The typed `fichero` CLI (`python -m fichero`) mirrors every endpoint reachable from SwiftUI. Reproduce against the CLI first; if it fails the same way, the engine owns it.
