"""Tests for #2225: LanceDB legacy schema stamp migration.

_coerce_vectors_to_existing_schema() must try table.add_columns() for
unknown fields before falling back to stripping them.  The critical case
is embedding_model_id: legacy tables lack the column, so without this fix
every append silently discards the model stamp.

Covers:
- No extra fields → data passes through unchanged (fast path)
- Extra field, add_columns succeeds → data unchanged (column now exists)
- Extra field, add_columns raises → field stripped from rows (safe fallback)
- Multiple extra fields, partial success → only failed ones stripped
- Empty data → returns [] without touching the table
"""

from __future__ import annotations

from unittest.mock import MagicMock, call


def _make_db():
    """Minimal concrete Database stub for unit-testing the mixin method."""
    from fichero.db import Database

    class _StubDB(Database):
        def __init__(self):
            pass  # skip real __init__

    db = _StubDB()
    db._lance_table_field_names = lambda table: frozenset(table._field_names)
    return db


def _make_table(*field_names: str) -> MagicMock:
    table = MagicMock()
    table._field_names = set(field_names)
    return table


def test_no_extra_fields_passthrough() -> None:
    """When all fields already exist in the table, data is returned unchanged."""
    db = _make_db()
    table = _make_table("id", "vector", "text")
    data = [{"id": "e1", "vector": [0.1, 0.2], "text": "hello"}]
    result = db._coerce_vectors_to_existing_schema("kg_entity_embeddings", table, data)
    assert result is data
    table.add_columns.assert_not_called()


def test_extra_field_add_columns_succeeds() -> None:
    """If add_columns succeeds, the data is returned intact (column now exists)."""
    db = _make_db()
    table = _make_table("id", "vector")
    table.add_columns.return_value = MagicMock()  # success
    data = [{"id": "e1", "vector": [0.1], "embedding_model_id": "intfloat/e5-small-v2"}]
    result = db._coerce_vectors_to_existing_schema("kg_entity_embeddings", table, data)
    assert result == data, "Data should be unchanged when column add succeeds"
    # DataFusion (LanceDB's SQL engine) rejects 'varchar'; 'string' is the correct dialect.
    table.add_columns.assert_called_once_with({"embedding_model_id": "cast(null as string)"})


def test_extra_field_add_columns_fails_strips_field() -> None:
    """If add_columns raises, the extra field is stripped so the append succeeds."""
    db = _make_db()
    table = _make_table("id", "vector")
    table.add_columns.side_effect = RuntimeError("schema locked")
    data = [{"id": "e1", "vector": [0.1], "embedding_model_id": "intfloat/e5-small-v2"}]
    result = db._coerce_vectors_to_existing_schema("kg_entity_embeddings", table, data)
    assert result == [{"id": "e1", "vector": [0.1]}]


def test_multiple_extra_fields_partial_failure() -> None:
    """Partial success: successfully added columns are kept; failed ones stripped."""
    db = _make_db()
    table = _make_table("id", "vector")

    def _add_side_effect(transforms: dict) -> MagicMock:
        if "bad_field" in transforms:
            raise RuntimeError("unsupported type")
        return MagicMock()

    table.add_columns.side_effect = _add_side_effect
    data = [{"id": "e1", "vector": [0.1], "embedding_model_id": "model-x", "bad_field": None}]
    result = db._coerce_vectors_to_existing_schema("kg_entity_embeddings", table, data)
    # embedding_model_id add succeeded → kept; bad_field failed → stripped
    assert "embedding_model_id" in result[0]
    assert "bad_field" not in result[0]


def test_empty_data_returns_empty() -> None:
    """Empty data list returns [] without touching the table."""
    db = _make_db()
    table = _make_table("id", "vector")
    result = db._coerce_vectors_to_existing_schema("t", table, [])
    assert result == []
    table.add_columns.assert_not_called()


def test_null_field_value_uses_string_expression() -> None:
    """A field with all-None values gets cast(null as string) — DataFusion rejects varchar."""
    db = _make_db()
    table = _make_table("id")
    data = [{"id": "e1", "mystery_col": None}]
    result = db._coerce_vectors_to_existing_schema("t", table, data)
    assert result == data
    table.add_columns.assert_called_once_with({"mystery_col": "cast(null as string)"})
