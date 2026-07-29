"""Tests for #2213: legacy LanceDB table rejects stamped embedding_model_id writes.

After #2225 stamped embedding_model_id onto every vector write, tables created
BEFORE that change lack the column. _coerce_vectors_to_existing_schema must
migrate the schema via table.add_columns before the append — so the stamp lands
and the write doesn't fail. The bug was that add_columns was called with
"cast(null as varchar)" which DataFusion rejects; the fix uses "cast(null as string)".

Covers:
- Legacy table (no embedding_model_id column) → column auto-added, stamp persisted
- Fresh table (column present from creation) → no migration needed, stamp persisted
- Fallback (add_columns raises) → field stripped rather than crashing
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from fichero_server.db import Database


@pytest.fixture
def _temp_db():
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "migration_test.duckdb"
    db = Database(db_path)
    yield db
    db.close()
    shutil.rmtree(tmpdir)


class TestLegacyLanceMigration:
    """save_vectors migrates legacy tables lacking embedding_model_id (#2213)."""

    def test_legacy_table_gets_column_and_stamp_persists(self, _temp_db):
        """Write stamped rows to a legacy table → column is added, value stored.

        This is the regression path: old code used 'cast(null as varchar)' which
        DataFusion rejects, so the fallback stripped the column and the model-id
        was silently lost. Fixed to 'cast(null as string)'.
        """
        db = _temp_db

        # Seed the table WITHOUT embedding_model_id (legacy schema).
        db.save_vectors("entity_vecs", [
            {"id": "e1", "vector": [0.1, 0.2], "text": "legacy row"},
        ])
        # Verify column is absent in legacy table.
        table = db.lance.open_table("entity_vecs")
        schema_fields = {f.name for f in table.schema}
        assert "embedding_model_id" not in schema_fields, (
            "Pre-condition: table should not yet have embedding_model_id"
        )

        # Now write with the stamped field — must succeed (migration runs).
        db.save_vectors("entity_vecs", [
            {"id": "e2", "vector": [0.3, 0.4], "text": "new row", "embedding_model_id": "model-v1"},
        ])

        # Re-open and verify column was added and stamp persisted.
        table = db.lance.open_table("entity_vecs")
        schema_fields_after = {f.name for f in table.schema}
        assert "embedding_model_id" in schema_fields_after, (
            "Column should be present after migration"
        )
        rows = table.search().select(["id", "embedding_model_id"]).limit(10).to_list()
        by_id = {r["id"]: r["embedding_model_id"] for r in rows}
        assert by_id["e1"] is None, "Legacy row should have null stamp"
        assert by_id["e2"] == "model-v1", "New row should carry the model stamp"

    def test_fresh_table_stamp_persists_without_migration(self, _temp_db):
        """Table created with embedding_model_id present → stamp stored directly."""
        db = _temp_db

        db.save_vectors("claim_vecs", [
            {"id": "c1", "vector": [0.1, 0.2], "text": "hello", "embedding_model_id": "model-v2"},
        ])
        table = db.lance.open_table("claim_vecs")
        rows = table.search().select(["id", "embedding_model_id"]).limit(5).to_list()
        assert rows[0]["embedding_model_id"] == "model-v2"

    def test_fallback_strips_field_when_add_columns_raises(self, _temp_db):
        """If add_columns itself raises, the write still completes (field stripped)."""
        db = _temp_db

        # Seed legacy table.
        db.save_vectors("fail_vecs", [
            {"id": "f1", "vector": [0.1, 0.2], "text": "base"},
        ])

        # Patch add_columns to simulate a persistent failure (e.g. concurrent writer).
        original_open = db.lance.open_table

        def _open_with_broken_add(name):
            t = original_open(name)
            def _broken_add_columns(*args, **kwargs):
                raise RuntimeError("simulated add_columns failure")
            t.add_columns = _broken_add_columns
            return t

        with patch.object(db._lance_db, "open_table", side_effect=_open_with_broken_add):
            # Must not raise — falls back to stripping the unknown field.
            db.save_vectors("fail_vecs", [
                {"id": "f2", "vector": [0.3, 0.4], "text": "new", "embedding_model_id": "model-v1"},
            ])

        # The row was written (id f2 exists), but embedding_model_id was stripped.
        table = db.lance.open_table("fail_vecs")
        rows = table.search().select(["id"]).limit(10).to_list()
        ids = {r["id"] for r in rows}
        assert "f2" in ids, "Row should be written even when add_columns fails"
        # Column should still be absent (migration was skipped).
        assert "embedding_model_id" not in {f.name for f in table.schema}
