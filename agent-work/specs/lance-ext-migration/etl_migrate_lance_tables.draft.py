"""DRAFT (not wired in) — idempotent ETL: migrate the 3 existing lancedb-client
tables to DuckDB-managed Lance-format datasets.

Contract (from §0.4a step 3 + memory "Marshall Diaries = real data"):
  * IDEMPOTENT: safe to re-run; converges to the same end state.
  * REGENERATE, don't bit-migrate: vectors are re-embeddable from source text
    (DuckDB `documents`/`KnowledgeEntity`/`KnowledgeClaim` rows), so the safe
    path rebuilds them with the existing FastEmbed/ONNX embedder and the SAME
    pinned model-id — no reliance on reading the old Lance binary format.
  * NON-DESTRUCTIVE: leave the old `vectors/` (lancedb-client) dir 100% intact
    until parity is confirmed. Write the new datasets to a SEPARATE dir
    (`vectors_ducklance/`), verify counts + top-k parity, and only then (as a
    SEPARATE, human-gated step) swap dirs. NEVER delete Marshall Diaries data.
  * DO NOT RUN ON LIVE DATA in this prep. This is executed against a COPY of a
    library only, after GATE-0 = GO.

Two migration strategies, both idempotent — pick per GATE-0 findings:
  A. REGENERATE (preferred, no dependency on reading old Lance via extension):
     re-embed every source row into the new datasets. Ground truth = DuckDB.
  B. COPY-THROUGH (faster, needs the extension to READ the old lancedb dir):
     COPY (SELECT * FROM '<old>/<t>.lance') TO '<new>/<t>.lance'
     (FORMAT lance, MODE 'overwrite'). Only valid if the extension can read a
     dataset the lancedb client wrote (GATE-0 P-extra: verify format compat).

This module drafts strategy A (the safe one) + a verify pass.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# The three canonical vector tables (from db_embeddings.py). Legacy
# kg_entities is folded into kg_entity_embeddings by
# ensure_canonical_entity_embedding_table() before/after.
VECTOR_TABLES = ("embeddings", "kg_entity_embeddings", "kg_claim_embeddings")


def migrate_library_vectors(
    library_path: str | Path,
    *,
    dry_run: bool = True,
) -> dict:
    """Regenerate the 3 vector datasets for one library into a side-by-side dir.

    Returns a report dict with per-table before/after counts. `dry_run=True`
    (default) computes source counts and the plan but writes nothing.

    IDEMPOTENCY: strategy A rebuilds from DuckDB source rows every run; the KG
    tables already use `save_vectors(..., replace=True)` (full rebuild) and the
    documents table is rebuilt via reindex_all after clearing, so a second run
    produces the same datasets. Re-running after a partial/interrupted run
    simply regenerates — no duplicate rows, no drift.
    """
    from fichero.db import Database

    library_path = Path(library_path)
    # HARD GUARD: refuse to run against a path that looks like a live library
    # unless explicitly overridden. Wire this to a real allowlist before use.
    _assert_not_live(library_path)

    db = Database(library_path)
    report: dict[str, dict] = {}
    try:
        # Point the NEW datasets at a separate dir so the old lancedb `vectors/`
        # stays untouched until parity is confirmed. (In the landed rewrite,
        # Database uses self._vectors_dir; here we redirect it for the ETL.)
        new_dir = library_path.parent / "vectors_ducklance"
        db._vectors_dir = new_dir  # draft: explicit redirect for side-by-side

        # --- source counts (ground truth = DuckDB) ---
        from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity
        from fichero.models import Document

        docs = [d for d in db.all(Document) if getattr(d, "page_content", None)]
        entities = db.all(KnowledgeEntity)
        claims = db.all(KnowledgeClaim)
        report["source"] = {
            "documents_with_content": len(docs),
            "entities": len(entities),
            "claims": len(claims),
        }

        if dry_run:
            report["dry_run"] = True
            return report

        # --- regenerate (strategy A) ---
        # Same pinned model-id is stamped on every row via _vector_model_metadata,
        # so the new datasets are model-compatible with the old ones by construction.
        docs_indexed = db.reindex_all()          # -> embeddings.lance
        entities_indexed = db.embed_entities(entities)   # -> kg_entity_embeddings.lance (replace=True)
        claims_indexed = db.embed_claims(claims)         # -> kg_claim_embeddings.lance (replace=True)
        report["regenerated"] = {
            "embeddings": docs_indexed,
            "kg_entity_embeddings": entities_indexed,
            "kg_claim_embeddings": claims_indexed,
        }

        # --- verify counts against the OLD lancedb dir (read-only) ---
        report["parity_counts"] = _verify_counts(library_path, new_dir)
        return report
    finally:
        db.close()


def _verify_counts(library_path: Path, new_dir: Path) -> dict:
    """Compare row counts old (lancedb `vectors/`) vs new (`vectors_ducklance/`).

    Reads the OLD dir with the still-installed lancedb client (non-destructive,
    read-only), and the NEW dir via DuckDB `SELECT count(*) FROM '<t>.lance'`.
    Regeneration can legitimately differ by a few rows if source rows changed
    since the old index was built; the report surfaces deltas for human review
    rather than asserting exact equality (that assertion lives in the parity
    TEST against a frozen fixture — see test_lance_ext_parity.draft.py).
    """
    import duckdb
    import lancedb  # still installed until parity confirmed

    out: dict[str, dict] = {}
    old = lancedb.connect(str(library_path.parent / "vectors"))
    old_tables = set(
        old.list_tables() if hasattr(old, "list_tables") else old.table_names()
    )
    conn = duckdb.connect()  # extension already loaded by _load_lance_extension in real path
    for t in VECTOR_TABLES:
        old_n = old.open_table(t).count_rows() if t in old_tables else 0
        new_path = new_dir / f"{t}.lance"
        new_n = (
            conn.execute(f"SELECT count(*) FROM '{new_path}'").fetchone()[0]
            if new_path.exists()
            else 0
        )
        out[t] = {"old": old_n, "new": new_n, "delta": new_n - old_n}
    conn.close()
    return out


def _assert_not_live(library_path: Path) -> None:
    """Refuse to touch a known-live library. Wire to the real guard before use."""
    import os

    if os.getenv("FICHERO_ALLOW_VECTOR_ETL") != "1":
        raise RuntimeError(
            "Vector ETL is gated. It regenerates vector datasets and must run "
            "against a COPY only. Set FICHERO_ALLOW_VECTOR_ETL=1 on a copy. "
            "NEVER run on live Marshall Diaries data."
        )
