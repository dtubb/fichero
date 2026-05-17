# Audit Report: Pydantic-only DuckDB Writes (#1112)

## Summary

Audit completed on 2026-05-17. Found **5 raw SQL DELETE statements** in `fichero-engine/src/fichero/app_db.py` that bypass the Pydantic-typed write path.

**Status:** All bypasses are in the AppDatabase class, which is app-level (not library-level) — distinct architectural scope from the #1117 fixes which addressed library-level database writes.

## Bypasses Found

### 1. `AppDatabase.delete_provider()` — Lines 219-224

**File:** `fichero-engine/src/fichero/app_db.py`

**Code:**
```python
def delete_provider(self, provider_id: str):
    """Delete a provider and its associated models."""
    with self._lock:
        self.conn.execute("DELETE FROM models WHERE provider_id = ?", [provider_id])
        self.conn.execute("DELETE FROM providers WHERE id = ?\", [provider_id])
        self.conn.commit()
```

**Scope:** Deletes from both `providers` and `models` tables — cascading delete.

**Mitigation:** Create `Provider` and `Model` Pydantic models, implement `db.delete(provider)` typed method in AppDatabase. Alternatively, add a typed `delete_provider_cascade()` wrapper.

---

### 2. `AppDatabase.delete_setting()` — Lines 436-439

**File:** `fichero-engine/src/fichero/app_db.py`

**Code:**
```python
def delete_setting(self, key: str):
    """Delete a setting."""
    self.conn.execute("DELETE FROM settings WHERE key = ?", [key])
    self.conn.commit()
```

**Scope:** Settings table only. Called by `reset_ai_defaults()` (line 496+) during factory reset.

**Mitigation:** Create `Setting` Pydantic model, implement `db.delete(setting)` typed method.

---

### 3. `AppDatabase.delete_model()` — Lines 544-547

**File:** `fichero-engine/src/fichero/app_db.py`

**Code:**
```python
def delete_model(self, model_id: str):
    """Delete a model."""
    self.conn.execute("DELETE FROM models WHERE id = ?", [model_id])
    self.conn.commit()
```

**Scope:** Models table only.

**Mitigation:** Create `Model` Pydantic model, implement `db.delete(model)` typed method.

---

### 4. `AppDatabase.delete_mcp_server()` — Lines 660-663

**File:** `fichero-engine/src/fichero/app_db.py`

**Code:**
```python
def delete_mcp_server(self, server_id: str):
    """Delete an MCP server."""
    self.conn.execute("DELETE FROM mcp_servers WHERE id = ?", [server_id])
    self.conn.commit()
```

**Scope:** MCP servers table only.

**Mitigation:** Create `MCPServer` Pydantic model, implement `db.delete(server)` typed method.

---

### 5. `AppDatabase.reset_ai_defaults()` — Lines 496-542 (via delete_setting)

**File:** `fichero-engine/src/fichero/app_db.py`

**Code:**
```python
def reset_ai_defaults(self):
    # ... docstring ...
    keys_to_delete = [
        "default_vision_provider", "default_vision_model",
        # ... (17 keys total) ...
    ]
    for key in keys_to_delete:
        self.delete_setting(key)  # ← Raw SQL via delete_setting()
    # ... then re-seed with factory defaults via set_setting() ...
```

**Scope:** Settings table (batch delete via loop). Called from settings route.

**Note:** This is _not_ a separate bypass — it's #2 called in a loop. Fix #2 to fix this.

---

## Not Found (Verified Clean)

Searched for raw INSERT/UPDATE/UPSERT patterns using:
- `execute("INSERT ...`
- `execute("UPDATE ...`
- `execute("UPSERT ...`

Result: **No other raw INSERT/UPDATE statements found outside db.py.**

---

## Architectural Context

**Invariant (from digest.md):**
> DuckDB writes go through Pydantic models. All persistence happens in `fichero-engine/src/fichero/db.py`. Raw SQL outside `db.py` is a bug.

**Why these exist:**
- AppDatabase manages app-level settings (providers, models, MCP server configs) — distinct from library-level database.py
- These methods predate the typed-write refactor pattern.
- Each case uses `with self._lock:` and `.conn.commit()`, so they're not unsafely concurrent — but they're still untyped.

**Precedent:** Issue #1117 fixed similar bypasses in `activity_store.py` and `cache.py` by introducing dataclasses (`WorkflowRun`, `CacheEntry`).

---

## Recommended Fix Pattern

For each bypass:

1. **Create a Pydantic model** (if not already present):
   ```python
   class Provider(BaseModel):
       id: str
       name: str
       # ... other fields ...
   ```

2. **Add a typed delete method** to AppDatabase (or use existing generic `db.delete()` from library-level Database class):
   ```python
   def delete_provider(self, provider_id: str):
       provider = self.get_provider(provider_id)
       if provider:
           db.delete(provider)
   ```

3. **Update call sites** to use the typed wrapper.

4. **Add unit tests** covering the delete path.

---

## Companion Issues

- **#1117:** Fixed 3 write-path bypasses in activity_store.py and cache.py (completed 2026-05-17).
- **#1112 (this audit):** Document all remaining raw-SQL bypasses for future cleanup.

---

*Report generated 2026-05-17 via `/session-worker` autonomous loop.*
