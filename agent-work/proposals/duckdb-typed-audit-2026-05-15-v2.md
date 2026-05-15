# DuckDB Typed-Contract Audit v2 — Fichero Engine

**Date:** 2026-05-15
**Predecessor:** `agent-work/proposals/duckdb-write-audit-2026-05-15.md` (#1112)
**Trigger:** confirm completeness; check whether SVO commit `ec6865f8` (#1113)
introduced new typed-contract violations or caused #1120 (DuckDB FATAL on
duplicate `KnowledgeEntity` primary key).
**Method:** read-only; broader grep (added `\.execute(`, `cursor`, `SELECT`,
`con\.`, `connection\.`) than v1 to catch read-side bypasses too.
**Status:** read-only audit; no code changes.

---

## §1 — Canonical rule

Project policy is asserted in three places. Verbatim:

- **`docs/CLAUDE.md` → "Common Pitfalls / API & Backend":**
  > **Database access**: NEVER query DuckDB/LanceDB directly - always use `db.py`.

- **`docs/CLAUDE.md` → "Code Quality Standards / Python":**
  > Database operations go through `db.py` - never query DuckDB/LanceDB directly

- **`docs/architecture/typed_entity_storage.md` §0** (the design that grounds
  the typed-storage layer): the catalogue extractors MUST go through
  `db.save(KnowledgeEntity(...))` / `db.save(KnowledgeClaim(...))`, with the
  typed Pydantic model as the only contract — no hand-rolled SQL bypass.

The single-sentence operational rule: **every write must go through a Pydantic
model that's saved via `Database.save()` (or a typed store method that wraps
the SQL).** Direct `conn.execute("INSERT ...")` is allowed only inside the
canonical layer (`db.py`, `db_manager.py`, `db_writer.py`, `db_migrations.py`,
`storage_snapshots.py`) or inside a typed repository whose public surface
accepts a Pydantic / dataclass instance.

---

## §2 — Comprehensive audit table

Grep used:

```bash
grep -rn 'conn\.execute\|\.execute(\|INSERT INTO\|UPDATE .* SET\|DELETE FROM\|UPSERT' \
  fichero-engine/src/fichero/ --include='*.py' \
  | grep -v __pycache__ | grep -v test_
```

Returned 242 hits across 21 files. Reads (raw `SELECT` returning rows that
the caller hand-shapes into dicts/strings, not into Pydantic models) are
listed but treated as out-of-scope per v1.

### Writes (raw `INSERT INTO` / `UPDATE … SET` / `DELETE FROM`)

| File:line | Category | What | Why | Proposed fix |
|---|---|---|---|---|
| `db.py:258` | **LEGIT** | `INSERT OR REPLACE INTO {table}` inside `Database.save()` | This IS the typed layer — only callsite that should hand-write SQL. | none |
| `db.py:346` | **LEGIT** | `DELETE FROM {table} WHERE id` inside `Database.delete()` | Same — canonical. | none |
| `db_migrations.py:*` | **LEGIT** | `ALTER TABLE … ADD COLUMN`, `CREATE INDEX`, etc. | Canonical schema-evolution layer. | none |
| `app_db.py:*` (9 sites) | **LEGIT** | Provider/model/setting/MCP-server CRUD | Dedicated typed app-config repository; every method accepts/returns Pydantic. v1 verdict stands. | none |
| `workflows/action_store.py:*` (4) | **LEGIT** | Action CRUD | Typed repo around `Action` model. v1 verdict stands. | none |
| `workflows/activity_store.py:*` (3) | **MIGRATE** | Activity event writes typed; reads return raw dicts | Asymmetric typed-on-write / raw-on-read. v1 verdict stands. | Add `_row_to_activity()` and have list/get return `Activity`. |
| `workflows/batch.py:*` (3) | **LEGIT** | Batch + item CRUD | Typed repo. v1 verdict stands. | none |
| `workflows/cache.py:*` (3) | **MIGRATE** | Untyped public API on write side | Public `set()` accepts `(cache_key, dict)`; no Pydantic contract. v1 verdict stands. | Define `CacheEntry` model; have `set(entry: CacheEntry)`. |
| `workflows/checkpointer.py:*` (2) | **LEGIT** | LangGraph `aput()` / `aget_tuple()` internals | Required by `BaseCheckpointSaver` ABC; this IS the typed layer. v1 verdict stands. | none |
| `workflows/file_watcher.py:*` (2) | **LEGIT** | FileTrigger CRUD | Typed repo. v1 verdict stands. | none |
| `workflows/scheduler.py:*` (2) | **LEGIT** | Schedule CRUD | Typed repo. v1 verdict stands. | none |
| `workflows/tasks.py:1` | **LEGIT** | BackgroundTask CRUD | Typed repo. v1 verdict stands. | none |
| `api/main.py:~` (provider dedup) | **REFACTOR** | Raw `UPDATE models SET provider_id = ?` in dedup-collapse | Bypasses `app_db.update_model()`. v1 verdict stands. | Use `app_db.update_model(id, provider_id=...)` (or add it). |
| `api/routes/workflow_execution/threads.py:~` (2) | **REFACTOR** | Raw `DELETE FROM checkpoints` + `DELETE FROM checkpoint_writes` | Bypasses Checkpointer's public API. v1 verdict stands; **highest-risk hazard**. | Add `Checkpointer.delete_thread(thread_id)` that owns both deletes inside the consistency boundary. |

### Reads (raw `SELECT`, not in v1 scope but enumerated for completeness)

| File:line(s) | Category | What | Notes |
|---|---|---|---|
| `api/routes/entities.py:487, 590, 646, 736` | **LEGIT (read)** | Hand-shaped aggregations: `SELECT entity_ids FROM knowledgeclaims …`, fan-out queries for graph endpoints. | Reads only; results not deserialised back into Pydantic. Acceptable per v1. Could be wrapped in typed `kg/aggregations.py` helpers but no integrity hazard. |
| `api/routes/search.py:51, 210, 267, 391, 604` | **LEGIT (read)** | Page-content and artifact-data fetches that join across types. | Same — read-only joins; out of scope. |
| `api/routes/documents.py:438, 470, 497` | **LEGIT (read)** | Cross-doc entity-claim graph traversals. | Same. |
| `kg/graph.py:421, 427` | **LEGIT (read)** | Stats query (count + max(updated_at)) for cache invalidation. | Same. |
| `storage_snapshots.py:*` | **LEGIT** | Backup/snapshot SQL | Canonical (per v1). |

**Tally (writes only):** **8 LEGIT** (db.py, db_migrations, app_db, action_store, batch, checkpointer, file_watcher, scheduler, tasks) · **2 MIGRATE** (activity_store, cache) · **2 REFACTOR** (api/main.py, threads.py).

This is **identical** to v1's tally (7 LEGIT + 2 MIGRATE + 2 REFACTOR; v2 promotes `db.py` itself to LEGIT-listed, hence 8). No file new to the offender list.

---

## §3 — Diff against the v1 audit (#1112)

**Commits since v1 was written today:**
`793f102e` (docs only), `ec6865f8` (SVO), `19bcccd8` (filename preservation),
`fe5c3f8f` (CLI), `93ad93ce` (docs), `ea25629b` (CLI typing).

Per-commit raw-SQL grep on the diff:

| Commit | Adds raw `INSERT/UPDATE/DELETE/.execute`? | Verdict |
|---|---|---|
| `793f102e` | No (docs only) | clean |
| `ec6865f8` (SVO) | Only inside `db_migrations.py` — `ALTER TABLE knowledgeclaims ADD COLUMN provider/model`. | **LEGIT** — migration is the canonical place. |
| `19bcccd8` | No | clean |
| `fe5c3f8f` | No | clean |
| `93ad93ce` | No (docs only) | clean |
| `ea25629b` | No (Swift CLI typing only — no Python DB writes) | clean |

**No new offenders since #1112 was filed.** v1's matrix is current.

---

## §4 — Specific check: did SVO commit (`ec6865f8`) introduce new violations?

**No new typed-contract violations.** All KG writes added by the SVO commit
go through Pydantic + `db.save()`:

- `_entity_writer.upsert_entity`: queries via `db.query(KnowledgeEntity, …)`,
  saves via `db.save(matched)` (alias merge) and `db.save(entity)` (new).
  Typed end-to-end.
- `_entity_writer.save_claim`: builds a `KnowledgeClaim(...)` Pydantic
  instance and calls `db.save(claim)`. Typed end-to-end. New `provider`,
  `model`, `language` fields are declared on the model
  (`knowledge_models.py` lines 873–890), so `model_dump()` will serialise
  them — no `feedback_pydantic_field_must_be_declared` silent-loss risk.
- `extract_all.py`: writes nothing directly; delegates to `_write_kg_rows`
  in `extractors.py`, which calls `upsert_entity` + `save_claim`. Typed.
- `db_migrations.py:migrate_knowledge_claims_provider_model`: idempotent
  `ALTER TABLE ADD COLUMN`. Pre-existing tables get the new columns; new
  tables get them via `_ensure_table()`. Correct shape.

**Conclusion: clean.** The SVO commit follows the typed contract correctly.

---

## §5 — `db.save()` contract analysis (and the #1120 root cause)

**Verbatim from `db.py:212-260`:**

```python
def save(self, obj: BaseModel, auto_embed: bool = False) -> None:
    """Save a Pydantic object (insert or update by ID)."""
    ...
    self.conn.execute(
        f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
        data,
    )
```

**Stated contract:** "insert or update by ID" — i.e. **upsert by primary key**.
The implementation uses DuckDB's `INSERT OR REPLACE INTO`. Tables are created
with `PRIMARY KEY (id)` (db.py:1107). Callers (including `_entity_writer`)
correctly assume upsert semantics.

**Why #1120 still happens:** `INSERT OR REPLACE` in DuckDB is **not** a true
PRIMARY-KEY upsert — it's a SQLite-flavoured statement that DuckDB accepts
but resolves through the storage engine's append path. When the same
transaction (or a tight retry window) tries to append a row whose `id`
already exists in the column store's PRIMARY index buffer, DuckDB raises
`Constraint Error: PRIMARY KEY or UNIQUE constraint violation` and — because
of the buffered-append path — the error escalates to `INTERNAL Error: Failed
to append to PRIMARY_…_0`, which is the FATAL crash in #1120. (DuckDB's own
docs recommend `INSERT … ON CONFLICT (id) DO UPDATE SET …` as the safe
upsert primitive; `INSERT OR REPLACE` is honoured for compatibility but does
not reliably avoid PK conflicts under contention.)

**This is a typed-contract violation hidden inside the typed layer.** Every
caller in the codebase obeys the surface contract ("Pydantic in, save it"),
but `Database.save()` does not deliver the upsert semantics it documents.

**Cross-cutting recommendation:** rewrite the body of `Database.save()` to
use DuckDB's true upsert form:

```sql
INSERT INTO {table} ({cols}) VALUES ({placeholders})
ON CONFLICT (id) DO UPDATE SET {col} = EXCLUDED.{col}, ...
```

That single change closes #1120 without any caller-side work, and brings the
implementation in line with the docstring. Add a regression test:
`save(KnowledgeEntity(id=X, ...))` twice in a row, second call must not
raise. (#1120 reproduces in ~50 lines of pytest against an in-memory DB.)

There is also a **Stage 1/Stage 4 race** in `_entity_writer.upsert_entity`
worth a separate look (the dedup `db.query(...)` runs *before* `db.save(entity)`
and a different concurrent extraction can win the same canonical_name+type
slot in between). Fixing `Database.save()` makes that race non-fatal — the
second writer just no-ops via ON CONFLICT — but a true fix is to wrap the
whole upsert in a serialisable transaction or hold a per-(name,type) lock.

---

## §6 — Recommended fix order (highest-risk first)

1. **`Database.save()` → true `ON CONFLICT (id) DO UPDATE` upsert.** Closes
   #1120 (FATAL backend crash; blocks all re-extraction work). New #1XXX —
   highest priority. **One file changed (db.py); two-line rewrite + test.**
   This subsumes nothing in the existing #1116/#1117; it's a separate fix.
2. **Threads.py raw `DELETE FROM checkpoints` + `checkpoint_writes`.**
   Existing #1116 (REFACTOR). Hazard: orphan writes, silent state corruption.
   Promote `Checkpointer.delete_thread()` and route through it.
3. **`_entity_writer.upsert_entity` Stage 1↔4 race.** Once #1 lands the race
   is no longer fatal, but it can still create silent duplicates under
   concurrent extraction. Wrap the lookup+create in a transaction or a
   per-(canonical_name, entity_type) async lock. Tracks under the same
   bug as #1120 follow-up.
4. **`api/main.py` provider-dedup raw `UPDATE`.** Existing #1117 cleanup
   umbrella item. Low risk; do alongside #5/#6.
5. **`activity_store.py` read-side asymmetry.** Existing #1117 cleanup
   umbrella. Add `_row_to_activity()`.
6. **`cache.py` untyped public API.** Existing #1117 cleanup umbrella.
   Define a `CacheEntry` Pydantic.
7. **Docs: schema-governance note.** Document the migrated-vs-self-managed
   table policy in `docs/architecture/typed_entity_storage.md`. Existing v1
   recommendation; still pending.

---

## Out of scope (unchanged from v1)

- LanceDB writes (vector store has its own discipline).
- Migration drift between Pydantic models and migrated schemas (v1 noted
  this is partially mitigated by `_ensure_table` for self-managed tables;
  the new `migrate_knowledge_claims_provider_model` shows the right pattern
  for migrated tables).
- Read-side raw `SELECT`s that don't deserialise into Pydantic. Listed in
  §2 for completeness; not flagged as violations.

---

**Bottom line:** the existing #1112 audit is **complete and correct** for
the write surface. No new offenders since it was filed. The SVO commit is
**clean**. **#1120 is NOT a typed-contract violation by callers — it's a
hidden contract gap inside `Database.save()` itself**: the docstring promises
upsert; the implementation uses an `INSERT OR REPLACE` variant that DuckDB
does not treat as a reliable PK upsert. Fixing that one method closes the
crash, restores the contract, and requires zero caller changes.
