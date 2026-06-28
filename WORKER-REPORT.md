## 2026-06-28

- Extended `docs/contributor/backend-development-standards.md` with a
  `Mutations` section documenting the two required mutation invariants:
  audit through `registry.invoke(...)` and observer updates through
  `emit_change(...)`.
- Grounded the write-up in merged code from:
  `fichero-engine/src/fichero/actions/registry.py`,
  `fichero-engine/src/fichero/api/routes/actions_registry.py`, and
  `fichero-engine/src/fichero/api/routes/agent_memory.py`.
- Used the shipped `agent_memory.create` path as the canonical example:
  the route invokes the action registry, the action returns a `ChangeSpec`, and
  `ActionRegistry.invoke(...)` writes `ActionAudit` then calls `_emit(...)` to
  dispatch `emit_change(...)`.
- Ran:
  `~/.venv/bin/mkdocs build --strict`
  -> passed
