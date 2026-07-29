"""Tests for _vector_row_count's no-silent-fallback behavior (#2512).

A broad ``except: return 0`` previously turned ANY error into a row count
of 0, which the finalize stage reads as "vector store is empty" and uses to
trigger a full, expensive re-embed of every entity and claim. The only
legitimate empty case is a table that does not exist yet (first run); any
other failure must NOT collapse to 0 — it must be logged loudly and raised.
"""

from unittest.mock import MagicMock

import pytest

from fichero_server.workflows.tools.kg_persist_finalize import _vector_row_count


def test_returns_zero_when_table_not_created_yet():
    """First run / never-embedded: the table is absent → legitimate 0."""
    db = MagicMock()
    db._lance_tables.return_value = ["some_other_table"]

    assert _vector_row_count(db, "kg_entity_embeddings") == 0
    # open_table must NOT be consulted for a non-existent table.
    db.lance.open_table.assert_not_called()


def test_returns_real_count_when_table_exists():
    db = MagicMock()
    db._lance_tables.return_value = ["kg_claim_embeddings"]
    db.lance.open_table.return_value.count_rows.return_value = 42

    assert _vector_row_count(db, "kg_claim_embeddings") == 42


def test_unexpected_error_raises_instead_of_silent_zero(caplog):
    """A transient/unexpected failure while reading an EXISTING table must
    propagate (loudly logged), never silently return 0 — a silent 0 would
    trigger a full KG re-embed (#2512)."""
    db = MagicMock()
    db._lance_tables.return_value = ["kg_entity_embeddings"]
    db.lance.open_table.side_effect = RuntimeError("transient lance failure")

    with pytest.raises(RuntimeError, match="transient lance failure"):
        _vector_row_count(db, "kg_entity_embeddings")

    assert any(
        "kg_entity_embeddings" in r.getMessage()
        and r.levelname in ("WARNING", "ERROR")
        for r in caplog.records
    ), "expected a loud log of the failure"


def test_error_listing_tables_also_raises(caplog):
    """If even listing tables fails unexpectedly, do not paper over it with
    a 0 — propagate so the re-embed does not silently fire."""
    db = MagicMock()
    db._lance_tables.side_effect = RuntimeError("lance connect failed")

    with pytest.raises(RuntimeError, match="lance connect failed"):
        _vector_row_count(db, "kg_entity_embeddings")
