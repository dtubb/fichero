"""Search-ranking degradation must be loud, not silent (#2507).

`_expand_query_with_entity_aliases` and `_entity_bonus_doc_ids` swallow any
exception and degrade gracefully (raw terms / no boost). That graceful path is
correct, but it used to be SILENT — masking a real KG/DB fault. These tests force
the failure path (monkeypatch `db.all` to raise) and assert the method still
degrades AND emits a warning.
"""

from __future__ import annotations

import logging


def _boom(*_args, **_kwargs):
    raise RuntimeError("kg table exploded")


def test_query_expansion_warns_on_failure(db, monkeypatch, caplog):
    monkeypatch.setattr(db, "all", _boom)
    with caplog.at_level(logging.WARNING):
        terms, entity_ids = db._expand_query_with_entity_aliases("popayán")
    # Degrades to the raw terms with no entity ids...
    assert entity_ids == set()
    assert terms  # non-empty term list preserved
    # ...and the failure is now visible.
    assert any(
        rec.levelno == logging.WARNING and "expansion failed" in rec.getMessage()
        for rec in caplog.records
    ), caplog.records


def test_entity_bonus_warns_on_failure(db, monkeypatch, caplog):
    monkeypatch.setattr(db, "all", _boom)
    with caplog.at_level(logging.WARNING):
        boosted = db._entity_bonus_doc_ids({"entity-1"})
    assert boosted == set()
    assert any(
        rec.levelno == logging.WARNING and "without entity boost" in rec.getMessage()
        for rec in caplog.records
    ), caplog.records


def test_entity_bonus_empty_input_short_circuits(db):
    # No matched entities → empty set without touching the DB at all.
    assert db._entity_bonus_doc_ids(set()) == set()
