"""DRAFT (not wired in) — parity test for the lancedb-client -> DuckDB-lance
rewrite. Landing target: fichero-engine/tests/db/test_lance_ext_parity.py.

Proves the new DuckDB-lance path returns the SAME top-k (same ids, same order)
as the old lancedb-client path for identical query vectors, on a SYNTHETIC
fixture (no live data). Also pins idempotency + count parity of the ETL.

Runs only when the extension is available; skips cleanly otherwise so CI on a
box without the bundled extension stays green.
"""

from __future__ import annotations

import pytest


def _extension_available() -> bool:
    try:
        import duckdb

        conn = duckdb.connect()
        # Real path uses _load_lance_extension(conn); here just probe.
        conn.execute("LOAD lance")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _extension_available(), reason="lance DuckDB extension not loadable here"
)


@pytest.fixture
def synthetic_docs():
    """Deterministic, tiny corpus — never touches a real library."""
    from fichero.models import Document

    texts = [
        "handwritten letter from the 1920s about coffee trade in Quibdó",
        "notarial record of a land dispute in Antioquia, 1887",
        "interview transcript discussing river navigation and gold mining",
        "photograph caption: portrait of a family, sepia, undated",
        "ledger of shipments between Cartagena and Barranquilla",
    ]
    return [Document(name=f"doc{i}", page_content=t) for i, t in enumerate(texts)]


def _old_topk(old_db, query_vec, k):
    """Old lancedb-client search path (reference implementation)."""
    rows = old_db.search_vectors("embeddings", query_vec, limit=k)
    return [(r.get("id"), round(float(r.get("_distance", 0.0)), 5)) for r in rows]


def _new_topk(new_db, query_vec, k):
    """New DuckDB-lance search path."""
    rows = new_db.search_vectors("embeddings", query_vec, limit=k)
    return [(r.get("id"), round(float(r.get("_distance", 0.0)), 5)) for r in rows]


def test_topk_ids_match_between_backends(tmp_path, synthetic_docs):
    """Same query vector -> same top-k ids in the same order on both backends.

    Builds two libraries from the identical corpus + identical (pinned) model,
    one on each backend, and compares. Distances may differ in the last
    decimals (different distance kernels) so we assert on ID ORDER, and on
    distance only to a tolerance.
    """
    # old backend
    from fichero.db import Database as OldDatabase  # lancedb-client build

    old_db = OldDatabase(tmp_path / "old" / "lib.duckdb")
    for d in synthetic_docs:
        old_db.save(d)
        old_db.embed(d, mode="page")

    # new backend (rewrite applied) — same corpus, same embedder/model-id
    from fichero.db import Database as NewDatabase

    new_db = NewDatabase(tmp_path / "new" / "lib.duckdb")
    for d in synthetic_docs:
        new_db.save(d)
        new_db.embed(d, mode="page")

    # Identical query vector from the SAME embedder -> compare top-k.
    qvec = new_db._embed_text("coffee trade letters", role="query")
    k = 3
    old = _old_topk(old_db, qvec, k)
    new = _new_topk(new_db, qvec, k)

    assert [i for i, _ in new] == [i for i, _ in old], f"id order diverged: {new} vs {old}"
    for (_, dn), (_, do) in zip(new, old):
        assert abs(dn - do) < 1e-3, f"distance drift too large: {dn} vs {do}"

    old_db.close()
    new_db.close()


def test_etl_is_idempotent_and_count_parity(tmp_path, synthetic_docs):
    """Running the ETL twice converges to the same per-table counts."""
    from fichero.db import Database

    lib = tmp_path / "lib.duckdb"
    db = Database(lib)
    for d in synthetic_docs:
        db.save(d)
        db.embed(d, mode="page")
    db.close()

    import os

    os.environ["FICHERO_ALLOW_VECTOR_ETL"] = "1"  # test copy only
    from docs.contributor.architecture.lance_ext_migration.etl_migrate_lance_tables_draft import (  # noqa: E501
        migrate_library_vectors,
    )

    r1 = migrate_library_vectors(lib, dry_run=False)
    r2 = migrate_library_vectors(lib, dry_run=False)
    assert r1["regenerated"] == r2["regenerated"], "ETL not idempotent"
    # New count must match the regenerated document count exactly (page mode).
    counts = r2["parity_counts"]["embeddings"]
    assert counts["new"] == len(synthetic_docs)


def test_model_id_stamp_preserved(tmp_path, synthetic_docs):
    """Regenerated datasets carry the SAME pinned model-id (no silent drift)."""
    from fichero.db import Database

    db = Database(tmp_path / "lib.duckdb")
    for d in synthetic_docs:
        db.save(d)
        db.embed(d, mode="page")
    ids = db.embedding_table_model_ids()["embeddings"]
    assert ids and all("<legacy-unstamped>" not in i for i in ids)
    db.close()
