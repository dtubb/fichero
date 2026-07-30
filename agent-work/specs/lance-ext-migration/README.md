# lance-under-DuckDB migration — prep branch (NOT landed)

Prep for §0.4a of `../storage-duckdb-lancedb-removal-review.md`: move the vector
store from the standalone `lancedb` Python client to **Lance-as-a-format-under-
DuckDB** via the DuckDB `lance` extension (DuckLabs × LanceDB, DuckDB 1.5.x).

Everything here is a **draft**. Nothing is wired into the `fichero` package, so
the live `lancedb`-client path is untouched and un-breakable. Landing order is
gated on GATE-0.

## Read in this order
1. **`GATE-0.md`** — the go/no-go. Verify a bundled, signed `lance.duckdb_extension`
   LOADs inside the embedded + sandboxed Mac engine. Includes a VERIFIED in-repo
   signing precedent that de-risks the library-validation concern. **If Gate 0
   fails, stop — stay on the `lancedb` client.**
2. `_load_lance_extension.draft.py` — connection helper for `db/__init__.py`.
3. `embeddings_rewrite.draft.py` — the 13 lancedb-client sites → DuckDB SQL
   through the existing connection + RLock.
4. `etl_migrate_lance_tables.draft.py` — idempotent, regenerate-based ETL
   (non-destructive; never runs on live data).
5. `test_lance_ext_parity.draft.py` — same-query → same-top-k parity + ETL
   idempotency + model-id-stamp tests.
6. `RISKS-and-deps.md` — honest risk list + `pyproject.toml` drop assessment
   and bundle-delta caveats.

## Ownership / guardrails obeyed
- Files touched by the eventual landing: `db/embeddings.py`, `db/__init__.py`
  connection helper, `pyproject.toml` — only. `workflows/*.py` and `db/app.py`
  are another lane's; not touched.
- NO build run (single xcodebuild slot held elsewhere). NO push. NO ETL against
  live `.duckdb`/`lance` data. Marshall Diaries never touched.

## Landing checklist (after GATE-0 = GO)
- [ ] Bundle signed osx_arm64 `lance.duckdb_extension` (matched to bundled DuckDB version).
- [ ] Add `_load_lance_extension` to `db/__init__.py`; call from `_connect` + `_reconnect_after_invalidated`.
- [ ] Splice `embeddings_rewrite.draft.py` methods into `db/embeddings.py` / `db/__init__.py`; delete the `self.lance` property + `import lancedb`.
- [ ] Reconcile the `# OPEN` flags (FLOAT[dim], delete, index, compaction) against GATE-0 P4/P5 findings.
- [ ] Run the ETL on a COPY of a real library; confirm count + top-k parity.
- [ ] Full engine suite + guardrails under the venv (parity test included); 0 failed before push.
- [ ] Drop `lancedb`/`pylance` (verify `pyarrow` removability); MEASURE real bundle delta.
