"""`kg_mentions` holds one row per name on a statement and moves with the statement (#6755)."""

from __future__ import annotations

from fichero_server.db import Database
from fichero_server.models.knowledge import KnowledgeClaim


def _rows(db: Database, claim_id: str) -> set[tuple]:
    return set(
        db.conn.execute(
            "SELECT entity_id, claim_id, page, role FROM kg_mentions WHERE claim_id = ?", [claim_id]
        ).fetchall()
    )


def test_save_writes_one_row_per_name_with_page_and_role(tmp_path):
    db = Database(tmp_path / "t.duckdb")
    claim = KnowledgeClaim(
        text="a met b", entity_ids=["a", "b"], subject_entity_id="a", source_page_label="7"
    )
    db.save(claim)
    assert _rows(db, claim.id) == {("a", claim.id, "7", "subject"), ("b", claim.id, "7", "named")}
    db.close()


def test_resave_replaces_the_rows(tmp_path):
    db = Database(tmp_path / "t.duckdb")
    claim = KnowledgeClaim(text="x", entity_ids=["a", "b"])
    db.save(claim)
    claim.entity_ids = ["c"]
    db.save(claim)
    assert {r[0] for r in _rows(db, claim.id)} == {"c"}
    db.close()


def test_save_many_and_delete(tmp_path):
    db = Database(tmp_path / "t.duckdb")
    claims = [KnowledgeClaim(text=f"c{i}", entity_ids=["a", f"n{i}"]) for i in range(3)]
    db.save_many(claims, new=True)
    assert all(len(_rows(db, c.id)) == 2 for c in claims)
    db.delete(claims[0])
    assert _rows(db, claims[0].id) == set()
    assert len(_rows(db, claims[1].id)) == 2
    db.close()


def test_failed_statement_write_leaves_no_rows(tmp_path):
    db = Database(tmp_path / "t.duckdb")
    claim = KnowledgeClaim(text="x", entity_ids=["a"])
    db.save(claim)
    try:
        with db.transaction():
            db.save(KnowledgeClaim(id="boom", text="y", entity_ids=["z"]))
            raise RuntimeError("abort")
    except RuntimeError:
        pass
    assert _rows(db, "boom") == set()
    db.close()


def test_table_has_no_index(tmp_path):
    db = Database(tmp_path / "t.duckdb")
    db.save(KnowledgeClaim(text="x", entity_ids=["a"]))
    assert db.conn.execute("SELECT count(*) FROM duckdb_indexes() WHERE table_name = 'kg_mentions'").fetchone()[0] == 0
    assert db.conn.execute("SELECT count(*) FROM duckdb_constraints() WHERE table_name = 'kg_mentions'").fetchone()[0] == 0
    db.close()
