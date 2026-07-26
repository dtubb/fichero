"""Legacy-embedding warning fires at most once per table per process (#2480).

The warning is emitted when a LanceDB vector table lacks the
``embedding_model_id`` column (legacy/pre-stamp tables). Because
``DatabaseManager`` keys Database connections by (package_path, thread_id),
each worker thread gets a fresh instance — previously the per-instance
deduplication set reset on every new instance, causing the warning to fire
on every search across every thread.

After the fix, ``_LEGACY_TABLE_WARNED`` is module-level, so the warning fires
exactly once per table name for the lifetime of the process.
"""

from __future__ import annotations

import logging
import threading
from unittest.mock import MagicMock

import pytest

from fichero.db import embeddings as db_embeddings
from fichero.db.embeddings import DatabaseEmbeddingMixin


@pytest.fixture(autouse=True)
def _reset_legacy_warned():
    """Isolate module-level set between tests."""
    db_embeddings._LEGACY_TABLE_WARNED.clear()
    yield
    db_embeddings._LEGACY_TABLE_WARNED.clear()


def _make_mixin() -> DatabaseEmbeddingMixin:
    """Return a bare DatabaseEmbeddingMixin with _get_embedding_model_id stubbed."""
    obj = DatabaseEmbeddingMixin.__new__(DatabaseEmbeddingMixin)
    obj._get_embedding_model_id = lambda: (  # type: ignore[method-assign]
        "intfloat/multilingual-e5-large|pooling=mean|normalization=l2|format=e5-role-prefix-v1"
    )
    return obj


def test_warning_fires_once_for_same_table(caplog):
    mixin = _make_mixin()
    with caplog.at_level(logging.WARNING, logger="fichero.db.embeddings"):
        mixin._warn_legacy_vector_table("kg_entity_embeddings")
        mixin._warn_legacy_vector_table("kg_entity_embeddings")
        mixin._warn_legacy_vector_table("kg_entity_embeddings")

    warnings = [r for r in caplog.records if "legacy/unstamped" in r.message]
    assert len(warnings) == 1, "warning must fire exactly once per table"


def test_warning_fires_once_per_distinct_table(caplog):
    mixin = _make_mixin()
    with caplog.at_level(logging.WARNING, logger="fichero.db.embeddings"):
        mixin._warn_legacy_vector_table("kg_entity_embeddings")
        mixin._warn_legacy_vector_table("kg_claim_embeddings")
        mixin._warn_legacy_vector_table("kg_entity_embeddings")
        mixin._warn_legacy_vector_table("kg_claim_embeddings")

    warnings = [r for r in caplog.records if "legacy/unstamped" in r.message]
    assert len(warnings) == 2, "one warning per distinct table name"
    tables_warned = {r.args[0] for r in warnings}
    assert tables_warned == {"kg_entity_embeddings", "kg_claim_embeddings"}


def test_warning_fires_once_across_multiple_instances(caplog):
    """Different Database instances (different threads) share the module-level set."""
    mixin_a = _make_mixin()
    mixin_b = _make_mixin()
    with caplog.at_level(logging.WARNING, logger="fichero.db.embeddings"):
        mixin_a._warn_legacy_vector_table("kg_entity_embeddings")
        mixin_b._warn_legacy_vector_table("kg_entity_embeddings")

    warnings = [r for r in caplog.records if "legacy/unstamped" in r.message]
    assert len(warnings) == 1, "second instance must not re-emit the warning"


def test_warning_fires_once_across_threads(caplog):
    """Concurrent threads racing on the same table each get fresh mixin instances."""
    results: list[int] = []

    def _worker():
        mixin = _make_mixin()
        with caplog.at_level(logging.WARNING, logger="fichero.db.embeddings"):
            mixin._warn_legacy_vector_table("kg_entity_embeddings")
        count = sum(1 for r in caplog.records if "legacy/unstamped" in r.message)
        results.append(count)

    threads = [threading.Thread(target=_worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total_warnings = sum(1 for r in caplog.records if "legacy/unstamped" in r.message)
    assert total_warnings == 1, "concurrent threads must produce exactly one warning"


def test_search_still_allowed_with_unstamped_table():
    """assert_vector_table_model_compatible returns (not raises) for legacy tables."""
    mixin = _make_mixin()

    # Simulate: table exists, schema lacks embedding_model_id column
    mock_table = MagicMock()
    mock_table.schema = []  # no fields → EMBEDDING_MODEL_ID_FIELD absent

    mock_lance = MagicMock()
    mock_lance.open_table.return_value = mock_table

    mixin.lance = mock_lance  # type: ignore[attr-defined]
    mixin._lance_tables = lambda: {"kg_entity_embeddings"}  # type: ignore[attr-defined]

    # Should not raise — legacy tables are allowed with a warning
    result = mixin.assert_vector_table_model_compatible("kg_entity_embeddings")
    assert result is None
    mock_lance.open_table.assert_called_once_with("kg_entity_embeddings")
