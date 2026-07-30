# Risks + dependency assessment — `lance`-under-DuckDB migration

Honest list. Ordered by how likely each is to sink or reshape the plan.

## 1. GATE 0 — extension loads in the embedded + sandboxed engine (PRIMARY)
The whole plan lives or dies here. Full procedure in `GATE-0.md`. **De-risked by a verified in-repo precedent** (see GATE-0 "VERIFIED signing precedent"): the extension is `dlopen`ed by the ENGINE subprocess, which on MAS has no hardened runtime and on DMG has `disable-library-validation` — the same reason `lance`/`pyarrow` `.so`s already load. So macOS library validation is very likely NOT the blocker. Residual gates: DuckDB's own extension-signature check (`allow_unsigned_extensions` — needs a version-matched *signed core-repo* osx_arm64 binary), ABI version match to our bundled DuckDB, and the sandbox being able to read the bundled extension path. Still requires the ONE build (G4/G5) to confirm end-to-end.

## 2. Row-level DELETE is not a documented op (SECOND-BIGGEST)
The extension's documented writes are `COPY … (FORMAT lance, MODE 'overwrite'|'append')` + the search functions. A row DELETE was NOT in the docs. The rewrite models delete as **read-filter-overwrite** (rewrite the dataset without the excluded rows). Correct and idempotent, but:
- rewrites the whole dataset per delete — fine at our per-library scale (thousands–low-millions), **pathological at the billion-vector multimodal future** (§0.3). Flag for that workload.
- delete is on the hot path: `save_vectors(replace=True)`, artifact re-translation, `delete_embedding`, `_delete_embedding_rows`. All go through the rewrite helper.
- **Mitigation to verify in GATE-0 P5:** does the loaded extension expose a native Lance delete/`MERGE`? If yes, use it (cheaper). If not, the overwrite path is the fallback and must be perf-checked on a realistic Marshall-sized table.

## 3. CREATE INDEX (IVF_FLAT/IVF_PQ) syntax unverified
Docs excerpt did not show index DDL. The current code builds **no** index (brute-force `table.search`), so parity does NOT require an index — `lance_vector_search` without an index still works. Indexing is an **optional later optimization** for scale, not a migration blocker. Confirm the real `CREATE INDEX … USING IVF_FLAT` form in GATE-0 P4/P5 before promising it. Do not gate the migration on it.

## 4. Fixed-size vs variable vector column typing
`lance_vector_search` examples cast the query to `FLOAT[4]` (fixed size). Our vectors are 1024-d (e5-large / bge-m3). The rewrite drafts `FLOAT[]` (variable) and flags `# OPEN`: Lance may require a fixed `FLOAT[1024]` column + matching query cast. If so, thread the model dim through `save_vectors`/`search_vectors`. Low risk (dim is known + pinned) but must be pinned down at write time.

## 5. Schema evolution on append
Old code had `_coerce_vectors_to_existing_schema` (add_columns) to heal legacy tables missing `embedding_model_id`. `COPY … MODE 'append'` requires an identical schema, so the rewrite handles a schema delta by read-union-rewrite (overwrite) instead of a strict append. Slower for the legacy-heal case but rare (one-time). The ETL's regenerate strategy sidesteps it entirely for the migration itself.

## 6. Materialising Python record dicts into DuckDB without pyarrow
`save_vectors` receives `list[dict]` with a vector list column. Without `conn.register(arrow_table)` we build a temp table + insert, then `COPY … TO … (FORMAT lance)`. Two options drafted (temp-table vs keep-slim-pyarrow); pick after measuring. This interacts with the dependency question below.

## 7. Compaction / #2542 micro-fragment story changes
`COPY MODE 'append'` still creates fragments. Whether the extension exposes an `optimize`/compact call is unknown (GATE-0 P5). Until confirmed, `compact_vectors` may become a no-op and the auto-compaction trigger (`_note_vector_append`) defaults to interval 0 (disabled). Not a correctness risk; a read-perf-at-scale risk.

## 8. Reading the OLD lancedb-written dir via the extension (format compat)
The ETL's preferred strategy A (regenerate from DuckDB source) avoids this. Strategy B (COPY-through the old dir) assumes the extension can READ a dataset the `lancedb` client wrote — NOT guaranteed across Lance format versions. Keep the `lancedb` client installed through migration so the old dir is always readable by its own writer; only drop it after parity.

## 9. Maturity of a 2026 extension
v0.5.4 (Apr 2026), new. Write/append/delete/index in *embedded* DuckDB (not the CLI) may have rough edges. The parity test + count-verify are the guardrail; keep the `lancedb` client as the documented rollback until the suite is green on real-sized data.

---

## Dependency + bundle assessment (`pyproject.toml`)

Current vector deps (appear in BOTH the base deps ~L65 and the bundled/briefcase list ~L173):
- `duckdb` — **KEEP** (relational engine; now also the vector query surface).
- `lancedb` — candidate to **DROP** after parity (Python client no longer called).
- `pylance` (provides `lance` module, noted "for FTS") — candidate to **DROP**; no `create_fts_index` exists in code (FTS is Python-side BM25), so nothing real depends on it.
- `pyarrow` — **NOT a direct dependency line**; pulled transitively by `lancedb`/`pylance`. Dropping those two *may* drop pyarrow too — **only if** nothing else needs it. `fastembed`→`onnxruntime`/`numpy` do not require pyarrow; DuckDB has its own Arrow. **Verify with `pip show`/dependency graph after removal**; if the `save_vectors` materialisation ends up keeping a slim pyarrow (option 6b), pyarrow stays.

**Expected bundle delta — be honest, MEASURE, don't promise:**
- Review doc attributes ≈380 MB to `lance` (149) + `pyarrow` (123) + `lancedb` (109).
- But the **Lance Rust core still ships inside the `.duckdb_extension`** — so a large chunk of the 149 MB `lance` weight reappears as the extension binary. The realistic win is roughly the `lancedb` client (109) + possibly `pyarrow` (123) IF fully removable = up to ~230 MB, **minus** the extension binary size (unmeasured). Net could be modest.
- **Action:** after GATE-0 GO and the drop, measure `du -sh` of the bundle before/after and the extension binary size. Report the real number. Do not claim −380 MB.

**Sequencing for the pyproject change:** drop `lancedb`/`pylance` LAST — only after the parity test is green on real-sized data AND the old `vectors/` dir is no longer needed for rollback. The ETL's count-verify reads the old dir with the `lancedb` client, so that client must stay installed through migration.
