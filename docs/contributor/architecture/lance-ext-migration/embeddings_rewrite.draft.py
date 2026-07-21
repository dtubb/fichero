"""DRAFT (not wired in) — rewrite of the vector primitives from the `lancedb`
Python client to DuckDB SQL through the EXISTING `self.conn` + `self._lock`.

Scope: this replaces ONLY the low-level Lance seam. The higher-level methods
(`embed`, `embed_entities`, `embed_claims`, `save_embedding`,
`passage_embedding_records`, `save_passage_embeddings`, `reindex_all`, …) are
UNCHANGED — they only build record dicts and call `save_vectors` /
`_delete_embedding_rows`, which now route through DuckDB. That is the whole
point of the seam being narrow (13 client sites).

Datasets are Lance-format directories addressed BY PATH under the existing
per-library `vectors/` dir: `<lib>.fichero/vectors/<table>.lance`. Every read
and write goes through the one DuckDB connection, so the single-connection +
RLock invariant (#2430/#2462/#2508) now covers vectors too — no second store,
no second lock. `self.lance` / `import lancedb` / `_lance_db` are all removed.

DO NOT land until GATE-0 = GO. Naming (`FLOAT[N]` vs `FLOAT[]`, CREATE INDEX,
row DELETE) marked `# OPEN` must be reconciled with GATE-0 P4/P5 findings.

Old→new call-site map (the "13 sites"):
  lance property / import lancedb        -> DELETED (use self.conn)
  _lance_db / _lance_path.mkdir          -> _vectors_dir (unchanged dir), no db handle
  _lance_tables()                        -> filesystem listing of *.lance dirs
  save_vectors()                         -> COPY ... TO '<t>.lance' (FORMAT lance, MODE ...)
  search_vectors()                       -> SELECT ... FROM lance_vector_search(...)
  _delete_embedding_rows()               -> _rewrite_dataset_excluding(...)
  _delete_artifact_embedding_rows()      -> _rewrite_dataset_excluding(...)
  delete_embedding()                     -> _rewrite_dataset_excluding(...)
  has_embedding()                        -> SELECT count(*) FROM '<t>.lance' WHERE ...
  compact_vectors()                      -> OPEN: lance compaction call, or no-op
  _vector_table_stats()                  -> SELECT count(*) FROM '<t>.lance'
  embedding_table_model_ids()            -> SELECT DISTINCT embedding_model_id ...
  assert_vector_table_model_compatible() -> SELECT DISTINCT embedding_model_id ...
  ensure_canonical_entity_embedding_table() -> COPY legacy .lance -> canonical
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# In __init__ replace:
#   self._lance_path = path.parent / "vectors"
#   self._lance_db = None
# with just the dir (no client handle):
#   self._vectors_dir = path.parent / "vectors"


class _VectorSeamRewrite:
    """Methods spliced onto Database. Shown standalone for review only."""

    # ---- paths / listing -------------------------------------------------

    def _vector_dataset_path(self, table_name: str) -> str:
        # table_name is a fixed internal constant (embeddings / kg_*), not user
        # input, but keep the identifier check to be safe.
        from fichero.db import _validated_identifier  # existing helper

        _validated_identifier(table_name, kind="vector table")
        self._vectors_dir.mkdir(parents=True, exist_ok=True)
        return str(self._vectors_dir / f"{table_name}.lance")

    def _lance_tables(self) -> list[str]:
        """Existing vector datasets, by name (replaces lancedb list_tables)."""
        if not self._vectors_dir.exists():
            return []
        return sorted(
            p.stem for p in self._vectors_dir.glob("*.lance")
        )

    def _dataset_exists(self, table_name: str) -> bool:
        return Path(self._vector_dataset_path(table_name)).exists()

    def _quote(self, value: str) -> str:
        return value.replace("'", "''")

    # ---- write -----------------------------------------------------------

    def save_vectors(
        self,
        table_name: str,
        data: list[dict],
        *,
        replace: bool = False,
        key_field: str = "id",
    ) -> None:
        """Create/append a Lance dataset via DuckDB COPY, through self.conn.

        `replace=True` deletes rows with matching key_field first (idempotent
        reindex/backfill), then appends — same contract as the lancedb path.
        """
        if not data:
            return
        path = self._vector_dataset_path(table_name)
        with self._lock:
            exists = self._dataset_exists(table_name)
            if exists and replace:
                keys = [str(r.get(key_field)) for r in data if r.get(key_field) is not None]
                if keys:
                    self._rewrite_dataset_excluding(table_name, key_field, keys)
                    exists = self._dataset_exists(table_name)

            # Materialise the records as a DuckDB relation, then COPY to Lance.
            # We build a TEMP table with an inferred column set. The vector
            # column is typed FLOAT[]  # OPEN: lance may require fixed FLOAT[dim];
            # if so, thread the model dim through here (e5-large/bge-m3 = 1024).
            self._copy_records_to_lance(
                path=path,
                data=data,
                mode="append" if exists else "overwrite",
                schema_evolve=exists,  # union columns with the existing dataset
            )
            self._note_vector_append(table_name)

    def _copy_records_to_lance(
        self, *, path: str, data: list[dict], mode: str, schema_evolve: bool
    ) -> None:
        """Build a temp relation from record dicts and COPY it to a Lance dir.

        OPEN: without pyarrow we can't `conn.register` an Arrow table directly.
        Two implementable options, pick per GATE-0 findings:
          (a) CREATE TEMP TABLE with inferred typed columns + executemany INSERT,
              then COPY (SELECT * FROM tmp) TO path (FORMAT lance, MODE ...).
          (b) keep a SLIM pyarrow purely to hand DuckDB an Arrow table
              (`conn.register('tmp', pa_table)`), if dropping pyarrow proves
              worse than keeping it (see RISKS.md §5 — measure).
        `schema_evolve`: when appending to an existing dataset whose schema
        differs (legacy tables lacked embedding_model_id — old
        _coerce_vectors_to_existing_schema handled this), read the existing
        rows, UNION the column sets, and rewrite MODE 'overwrite' instead of a
        strict append (COPY append requires identical schema).
        """
        raise NotImplementedError("pick option (a)/(b) after GATE-0 P4/P5")

    def _rewrite_dataset_excluding(
        self, table_name: str, field: str, values: list[str]
    ) -> None:
        """Delete rows by rewriting the dataset without them.

        The extension's documented ops are COPY (overwrite/append) + the search
        functions; a row-level DELETE was NOT in the docs (GATE-0 P5). So model
        delete as read-filter-overwrite, which uses only documented ops:

            COPY (SELECT * FROM '<path>' WHERE <field> NOT IN (...))
              TO '<path>' (FORMAT lance, MODE 'overwrite')

        Rewrites the whole dataset — fine at our per-library scale; flag for the
        billion-vector multimodal future (RISKS.md §3). If GATE-0 P5 finds a
        native Lance delete, use it instead (cheaper).
        """
        if not self._dataset_exists(table_name):
            return
        path = self._vector_dataset_path(table_name)
        in_list = ", ".join(f"'{self._quote(v)}'" for v in values)
        with self._lock:
            self._execute(
                f"COPY (SELECT * FROM '{path}' WHERE {field} NOT IN ({in_list})) "
                f"TO '{path}' (FORMAT lance, MODE 'overwrite')"
            )

    def _delete_embedding_rows(self, field: str, value: str) -> None:
        from fichero.db_embeddings import EMBEDDINGS_TABLE

        self._rewrite_dataset_excluding(EMBEDDINGS_TABLE, field, [value])

    def _delete_artifact_embedding_rows(
        self, artifact_id: str, embedding_scope: str
    ) -> None:
        from fichero.db_embeddings import EMBEDDINGS_TABLE

        if not self._dataset_exists(EMBEDDINGS_TABLE):
            return
        path = self._vector_dataset_path(EMBEDDINGS_TABLE)
        safe_id = self._quote(artifact_id)
        safe_scope = self._quote(embedding_scope)
        with self._lock:
            self._execute(
                f"COPY (SELECT * FROM '{path}' WHERE NOT "
                f"(artifact_id = '{safe_id}' AND embedding_scope = '{safe_scope}')) "
                f"TO '{path}' (FORMAT lance, MODE 'overwrite')"
            )

    # ---- search ----------------------------------------------------------

    def search_vectors(
        self, table_name: str, query_vector: list[float], limit: int = 10
    ) -> list[dict]:
        """kNN via lance_vector_search(), returning row dicts like before.

        The lancedb path returned `_distance`; lance_vector_search also returns
        `_distance`, so downstream `1/(1+d)` scoring and _l2_normalize stay
        valid unchanged.
        """
        if not self._dataset_exists(table_name):
            return []
        self.assert_vector_table_model_compatible(table_name)
        path = self._vector_dataset_path(table_name)
        # OPEN: FLOAT[] vs FLOAT[<dim>] cast form — reconcile with GATE-0 P4.
        vec_literal = "[" + ", ".join(repr(float(x)) for x in query_vector) + "]"
        with self._lock:
            rows, columns = self._execute_fetch_with_columns(
                f"SELECT * FROM lance_vector_search("
                f"'{path}', 'vector', {vec_literal}::FLOAT[], "
                f"k => {int(limit)}, prefilter => true) "
                f"ORDER BY _distance ASC"
            )
        return [dict(zip(columns, row)) for row in rows]

    def has_embedding(self, doc_id: str) -> bool:
        from fichero.db_embeddings import EMBEDDINGS_TABLE

        if not self._dataset_exists(EMBEDDINGS_TABLE):
            return False
        path = self._vector_dataset_path(EMBEDDINGS_TABLE)
        safe = self._quote(doc_id or "")
        row = self._execute_fetchone_compat(
            f"SELECT 1 FROM '{path}' WHERE id = '{safe}' OR document_id = '{safe}' LIMIT 1"
        )
        return row is not None

    def delete_embedding(self, doc_id: str) -> bool:
        from fichero.db_embeddings import EMBEDDINGS_TABLE

        if not self._dataset_exists(EMBEDDINGS_TABLE):
            return False
        path = self._vector_dataset_path(EMBEDDINGS_TABLE)
        safe = self._quote(doc_id)
        with self._lock:
            self._execute(
                f"COPY (SELECT * FROM '{path}' WHERE NOT "
                f"(id = '{safe}' OR document_id = '{safe}')) "
                f"TO '{path}' (FORMAT lance, MODE 'overwrite')"
            )
        return True

    # ---- stats / model-id guard -----------------------------------------

    def _vector_table_stats(self, table_name: str) -> dict:
        if not self._dataset_exists(table_name):
            return {"indexed_count": 0, "table_exists": False}
        path = self._vector_dataset_path(table_name)
        try:
            row = self._execute_fetchone_compat(f"SELECT count(*) FROM '{path}'")
            return {"indexed_count": int(row[0]) if row else 0, "table_exists": True}
        except Exception:  # noqa: BLE001
            return {"indexed_count": 0, "table_exists": False}

    def embedding_table_model_ids(self, *, table_names=None, sample_limit=10_000) -> dict:
        from fichero.db_embeddings import (
            EMBEDDINGS_TABLE,
            KG_CLAIM_EMBEDDINGS_TABLE,
            KG_ENTITY_EMBEDDINGS_TABLE,
            EMBEDDING_MODEL_ID_FIELD,
        )

        table_names = table_names or (
            EMBEDDINGS_TABLE, KG_ENTITY_EMBEDDINGS_TABLE, KG_CLAIM_EMBEDDINGS_TABLE,
        )
        out: dict[str, list[str]] = {}
        for t in table_names:
            if not self._dataset_exists(t):
                out[t] = []
                continue
            path = self._vector_dataset_path(t)
            # Column may be absent in legacy datasets -> COLUMNS() guard, or
            # try/except and report <legacy-unstamped>.
            try:
                rows, _ = self._execute_fetch_with_columns(
                    f"SELECT DISTINCT {EMBEDDING_MODEL_ID_FIELD} FROM '{path}'"
                )
                out[t] = sorted(str(r[0] or "<legacy-unstamped>") for r in rows)
            except Exception:  # noqa: BLE001 — legacy dataset lacks the column
                out[t] = ["<legacy-unstamped>"]
        return out

    def assert_vector_table_model_compatible(self, table_name: str) -> None:
        from fichero.db_embeddings import (
            EMBEDDING_MODEL_ID_FIELD,
            EmbeddingSpaceMismatchError,
        )

        if not self._dataset_exists(table_name):
            return
        path = self._vector_dataset_path(table_name)
        try:
            rows, _ = self._execute_fetch_with_columns(
                f"SELECT DISTINCT {EMBEDDING_MODEL_ID_FIELD} FROM '{path}'"
            )
        except Exception:  # noqa: BLE001 — legacy dataset without the column
            self._warn_legacy_vector_table(table_name)
            return
        known = {r[0] for r in rows if r[0] is not None}
        if not known:
            self._warn_legacy_vector_table(table_name)
            return
        active = self._get_embedding_model_id()
        if any(mid != active for mid in known):
            raise EmbeddingSpaceMismatchError(
                table_name=table_name, active_model_id=active, stored_model_ids=known
            )

    def ensure_canonical_entity_embedding_table(self):
        from fichero.db_embeddings import (
            KG_ENTITY_EMBEDDINGS_TABLE,
            LEGACY_KG_ENTITY_EMBEDDINGS_TABLE,
        )

        if self._dataset_exists(KG_ENTITY_EMBEDDINGS_TABLE):
            return KG_ENTITY_EMBEDDINGS_TABLE
        if not self._dataset_exists(LEGACY_KG_ENTITY_EMBEDDINGS_TABLE):
            return None
        legacy = self._vector_dataset_path(LEGACY_KG_ENTITY_EMBEDDINGS_TABLE)
        canonical = self._vector_dataset_path(KG_ENTITY_EMBEDDINGS_TABLE)
        with self._lock:
            self._execute(
                f"COPY (SELECT * FROM '{legacy}') TO '{canonical}' "
                f"(FORMAT lance, MODE 'overwrite')"
            )
        return KG_ENTITY_EMBEDDINGS_TABLE

    # ---- compaction / index ---------------------------------------------

    def compact_vectors(self, table_name: str | None = None) -> dict:
        """OPEN: with Lance-under-DuckDB the micro-fragment/compaction story
        changes. COPY MODE 'append' still fragments; whether the extension
        exposes an optimize/compact call (or whether periodic overwrite-rewrite
        replaces it) is a GATE-0 P5 finding. Until confirmed, this may become a
        no-op returning {} — the #2542 auto-compaction trigger
        (_note_vector_append) can be disabled by defaulting the interval to 0.
        """
        return {}

    # ---- shims for methods referenced above ------------------------------
    def _execute_fetchone_compat(self, sql: str):
        return self.execute_fetchone(sql)  # existing Database method
