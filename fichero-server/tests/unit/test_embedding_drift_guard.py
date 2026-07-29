"""Tests for #2232: embedding drift guard full-table scan.

The old guard sampled only the first 32 rows via table.search().limit(32).
An interrupted re-embed leaves the table in a mixed state: first 32 rows may
be uniformly stamped with the active model while rows 33+ carry the old model.
The old guard would PASS silently; the new guard MUST raise.

Covers:
- Mixed-space table (first 32 rows uniform, rows 33+ differ) → raises
- Uniform table → no raise
- Empty table → no raise
- Legacy table (no embedding_model_id column in schema) → warns, no raise
- All-NULL model-ids (stamped column but all blank) → warns, no raise
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fichero_server.db.embeddings import (
    EMBEDDING_MODEL_ID_FIELD,
    EmbeddingSpaceMismatchError,
    _LEGACY_TABLE_WARNED,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stub_db():
    from fichero_server.db import Database

    class _StubDB(Database):
        def __init__(self):
            pass  # skip real __init__

    db = _StubDB()
    return db


def _make_table(schema_has_field: bool, all_model_ids: list[str | None]) -> MagicMock:
    """Build a mock LanceDB table that returns `all_model_ids` from a full column scan.

    The implementation uses count_rows() + search().select([col]).limit(n).to_list()
    which avoids the pylance Rust extension.
    """
    table = MagicMock()

    if schema_has_field:
        field = MagicMock()
        field.name = EMBEDDING_MODEL_ID_FIELD
        table.schema = [field]
    else:
        table.schema = []  # legacy: column absent

    table.count_rows.return_value = len(all_model_ids)
    # Mock the search().select([...]).limit(n).to_list() chain
    rows = [{EMBEDDING_MODEL_ID_FIELD: v} for v in all_model_ids]
    table.search.return_value.select.return_value.limit.return_value.to_list.return_value = rows

    return table


def _wire_db(db, table, table_name: str = "kg_claim_embeddings", active_model: str = "active-model"):
    # lance is a property backed by _lance_db; set the backing attribute directly
    mock_lance = MagicMock()
    mock_lance.open_table.return_value = table
    db._lance_db = mock_lance
    db._lance_tables = lambda: {table_name}
    db._get_embedding_model_id = lambda: active_model


# ---------------------------------------------------------------------------
# The regression test: fails under old 32-row cap, passes with full scan
# ---------------------------------------------------------------------------


def test_drift_guard_detects_mixed_space_beyond_first_rows() -> None:
    """First 32 rows uniform (active model); rows 33-40 are old-model.

    Old code: .search().limit(32) sees only active IDs → no raise (WRONG).
    New code: full column scan sees both IDs → EmbeddingSpaceMismatchError (CORRECT).
    """
    ACTIVE = "active-model"
    OLD = "old-model"
    # 40 rows: first 32 are fine, last 8 were written by the old embedder
    all_ids = [ACTIVE] * 32 + [OLD] * 8

    db = _make_stub_db()
    table = _make_table(schema_has_field=True, all_model_ids=all_ids)
    _wire_db(db, table, active_model=ACTIVE)

    with pytest.raises(EmbeddingSpaceMismatchError) as exc_info:
        db.assert_vector_table_model_compatible("kg_claim_embeddings")

    err = exc_info.value
    assert OLD in err.stored_model_ids
    assert err.active_model_id == ACTIVE


# ---------------------------------------------------------------------------
# Happy path: uniform table
# ---------------------------------------------------------------------------


def test_drift_guard_passes_uniform_table() -> None:
    ACTIVE = "active-model"
    all_ids = [ACTIVE] * 100

    db = _make_stub_db()
    table = _make_table(schema_has_field=True, all_model_ids=all_ids)
    _wire_db(db, table, active_model=ACTIVE)

    db.assert_vector_table_model_compatible("kg_claim_embeddings")  # must not raise
    assert table.count_rows.call_count == 1


# ---------------------------------------------------------------------------
# Edge: empty table
# ---------------------------------------------------------------------------


def test_drift_guard_empty_table_no_raise() -> None:
    db = _make_stub_db()
    table = _make_table(schema_has_field=True, all_model_ids=[])
    _wire_db(db, table)

    db.assert_vector_table_model_compatible("kg_claim_embeddings")  # must not raise
    assert table.count_rows.call_count == 1


# ---------------------------------------------------------------------------
# Edge: legacy table (column missing from schema)
# ---------------------------------------------------------------------------


def test_drift_guard_legacy_table_warns_not_raises() -> None:
    db = _make_stub_db()
    table = _make_table(schema_has_field=False, all_model_ids=[])
    _wire_db(db, table)

    # The legacy-warning dedup set is a module global (#2480); reset so the warn
    # path is observable regardless of test order.
    _LEGACY_TABLE_WARNED.discard("kg_claim_embeddings")
    db.assert_vector_table_model_compatible("kg_claim_embeddings")
    # should warn but not raise
    assert "kg_claim_embeddings" in _LEGACY_TABLE_WARNED


# ---------------------------------------------------------------------------
# Edge: column present but all NULL values
# ---------------------------------------------------------------------------


def test_drift_guard_all_null_model_ids_warns_not_raises() -> None:
    db = _make_stub_db()
    table = _make_table(schema_has_field=True, all_model_ids=[None, None, None])
    _wire_db(db, table)

    _LEGACY_TABLE_WARNED.discard("kg_claim_embeddings")
    db.assert_vector_table_model_compatible("kg_claim_embeddings")
    assert "kg_claim_embeddings" in _LEGACY_TABLE_WARNED
