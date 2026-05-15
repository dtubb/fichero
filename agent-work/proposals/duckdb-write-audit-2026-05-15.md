# DuckDB Write-Path Audit — Fichero Engine

**Date:** 2026-05-15
**Issue:** #1112
**Milestone:** 0.0.3 - Post-LLM-stack
**Status:** Read-only audit; no code changes.

---

## One-line answer to Daniel's question

**Yes, we write through typed models almost everywhere — 7 of 11 files are LEGIT typed repositories, 2 need read-side symmetry (MIGRATE), and 2 callsites bypass typed APIs and should be fixed (REFACTOR).** No silent-data-loss pattern (write raw + read typed) detected anywhere. One genuine hazard found: raw `DELETE` against checkpointer tables that can orphan write rows.

---

## Method

Canonical rule (`docs/CLAUDE.md`, "Common Pitfalls"): "**Database access**: NEVER query DuckDB/LanceDB directly - always use `db.py`." The typed-storage doc (`docs/architecture/typed_entity_storage.md`) reinforces it: writes go through Pydantic models + `DBWriter` / repository abstractions, not hand-rolled SQL.

Survey grep:

```bash
grep -rn 'INSERT INTO\|UPDATE .* SET\|DELETE FROM\|UPSERT' \
  fichero-engine/src/fichero/ --include='*.py' \
  | grep -v '/db_writer\|/db_manager\|/db\.py\|/db_migrations\|/migrations/\|/tests/\|test_'
```

Returned ~64 raw write statements distributed across 11 files. Each file was inspected (public surface + write helpers + read helpers + schema bootstrap) and classified.

**Canonical db layer** (treated as legit, not audited): `db.py`, `db_manager.py`, `db_writer.py`, `db_migrations.py`, `storage_snapshots.py`, `models.py`.

---

## Findings

| File | Stores | Typed repo? | Round-trip? | Schema in migrations? | Class | Justification |
|---|---|---|---|---|---|---|
| `api/main.py` | Provider re-parenting during dedup | No | No | n/a | **REFACTOR** | Single raw `UPDATE` in dedup-collapse routine bypasses `app_db.update_provider()`. |
| `api/routes/workflow_execution/threads.py` | Thread deletion across checkpoint tables | No | Mixed | Partial (checkpoints yes; checkpoint_writes implicit) | **REFACTOR** | Raw `DELETE` bypasses Checkpointer's public API; risks orphaning write rows. |
| `app_db.py` | Providers, models, settings, mcp_servers | Yes | Yes | Self-managed | **LEGIT** | Dedicated typed app-config layer; wraps all SQL in Pydantic-model methods. Reasonable structural split from library-scoped `db.py`. |
| `workflows/action_store.py` | Reusable workflow actions | Yes | Yes | Inline (not migrated) | **LEGIT** | Full typed repository; accepts `Action` Pydantic, JSON-serializes, deserializes via `_row_to_action()`. |
| `workflows/activity_store.py` | Activity events + workflow run logs | Asymmetric | Partial | Inline | **MIGRATE** | Writes accept typed `Activity`; reads return raw dicts. Asymmetry is a maintainability smell. |
| `workflows/batch.py` | Batch execution + item status | Yes | Yes | Inline | **LEGIT** | Accepts `BatchExecution`/`BatchItem` dataclasses; round-trips via JSON. |
| `workflows/cache.py` | Node-execution cache | No (raw API) | Yes (on read) | Inline | **MIGRATE** | Public `set()` accepts raw `(cache_key, result_dict)`; deserializes on read. No typed contract. |
| `workflows/checkpointer.py` | LangGraph checkpoints + pending writes | Yes | Yes | Partial (checkpoints migrated; checkpoint_writes implicit) | **LEGIT** | LangGraph-compatible; `aput()` / `aget_tuple()` / `alist()` are the public surface. |
| `workflows/file_watcher.py` | File triggers + executions | Yes | Yes | Inline | **LEGIT** | Accepts `FileTrigger` dataclass; round-trips via `_row_to_trigger()`. |
| `workflows/scheduler.py` | Recurring schedules + run history | Yes | Yes | Inline | **LEGIT** | Accepts `Schedule` dataclass; round-trips via `_row_to_schedule()`. |
| `workflows/tasks.py` | Background task queue | Yes | Yes | Inline | **LEGIT** | Accepts `BackgroundTask` dataclass; round-trips via `_row_to_task()`. |

**Tally:** 7 LEGIT · 2 MIGRATE · 2 REFACTOR.

---

## Overall assessment

The engine is in good shape. The discipline asserted in `docs/CLAUDE.md` is largely followed: most files that touch DuckDB are themselves the typed repository for their concern. The pattern is consistent — accept a dataclass or Pydantic model from callers, inline-serialize nested fields as JSON, write through DuckDB, deserialize back on read via a `_row_to_X()` helper. `app_db.py` is a parallel but legit second layer for app-level configuration (providers, models, settings, MCP servers) — that's a reasonable structural split from the library-scoped `db.py`, not a bypass.

**No silent-data-loss risk detected.** The worst failure mode the audit was looking for — write via raw SQL + read via Pydantic, where un-declared fields silently drop on read (the `feedback_pydantic_field_must_be_declared` pattern) — is **not present** anywhere. Every store either round-trips through the same typed contract on both sides, or round-trips through raw dicts on both sides. No asymmetric type drift.

**Two genuine hazards** worth dedicated follow-up issues:

1. **`api/routes/workflow_execution/threads.py`** does raw `DELETE` against checkpointer tables. The checkpointer owns its consistency contract — pending writes are linked to checkpoints — and bypassing it risks orphaning rows. **High-risk follow-up.**
2. **`api/main.py`** has a raw `UPDATE` in the provider dedup-collapse routine. Bypasses `app_db.update_provider()`. Low-risk (provider dedup is infrequent and recoverable), but a cleanup target.

**Two stores with read-asymmetry** worth one combined cleanup issue:

3. **`activity_store.py`** accepts typed `Activity` on write but returns raw dicts on read. If reads ever switch to return Pydantic and the Pydantic model gains `extra="allow"`, this becomes a silent-data-loss site.
4. **`cache.py`** has an entirely raw public API on the write side. Deserializes JSON on read. The contract is documented by convention, not by type.

**Migration-coverage gap.** Six stores (`action_store`, `activity_store`, `batch`, `cache`, `file_watcher`, `scheduler`, `tasks`) create their own tables inline at startup rather than declaring schema in `db_migrations.py`. These are workflow-runtime stores (caches, queues, ephemeral state) — inline initialization is acceptable if intentional, but the policy isn't documented anywhere. Recommend a short "schema-governance" section in `docs/CLAUDE.md` or the typed-storage doc that names the two regimes (migrated vs. self-managed) and which stores belong where.

---

## Recommended follow-ups (filed as separate issues)

- **High priority — REFACTOR:** Route thread deletion through Checkpointer's public API instead of raw `DELETE`. Hazard: orphan writes.
- **Medium priority — Cleanup umbrella:** Three smaller items (`api/main.py` provider `UPDATE` bypass, `activity_store` read-side asymmetry, `cache.py` untyped public API) folded into one cleanup issue.
- **Low priority — Docs:** Add a schema-governance note distinguishing migrated tables (core library data) from self-managed tables (workflow runtime state).

---

## Out of scope

- LanceDB writes (vector store has its own discipline — separate audit if Daniel wants it).
- Migration content (drift between models and migrated schema).
- Reads (raw `SELECT` is fine as long as deserialization is typed; audit targeted writes because that's where integrity is created).
- Any fixes — this audit is read-only.
