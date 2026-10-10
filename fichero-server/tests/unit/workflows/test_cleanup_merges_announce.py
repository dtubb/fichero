"""Clean Up's merges are knowledge-graph changes and say so (#4420, the change-event seam).

`_apply_groups` points absorbed entities at their canonical one and adds aliases; until it announced
them, every open Inspector kept showing the unmerged names.
"""

from __future__ import annotations

from fichero_server.db import Database
from fichero_server.models.knowledge import EntityType, KnowledgeEntity
from fichero_server.workflows.tools import _workflow_change_emit, cleanup


def test_merging_announces_the_entities_it_changed(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(_workflow_change_emit, "emit_change", lambda library_path, **kw: seen.append(kw))
    db = Database(tmp_path / "t.duckdb")
    keep = KnowledgeEntity(canonical_name="Pedro de Mosquera", entity_type=EntityType.person)
    gone = KnowledgeEntity(canonical_name="P. Mosquera", entity_type=EntityType.person)
    db.save(keep)
    db.save(gone)

    merged = cleanup._apply_groups(db, [keep, gone], [{"canonical": "Pedro de Mosquera", "aliases": ["P. Mosquera"]}])

    assert merged == 1
    (event,) = [kw for kw in seen if kw["type"] == "entity.updated"]
    assert set(event["entity_ids"]) == {keep.id, gone.id}
    db.close()


def test_nothing_merged_announces_nothing(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(_workflow_change_emit, "emit_change", lambda library_path, **kw: seen.append(kw))
    db = Database(tmp_path / "t.duckdb")
    only = KnowledgeEntity(canonical_name="Pedro", entity_type=EntityType.person)
    db.save(only)

    assert cleanup._apply_groups(db, [only], [{"canonical": "Pedro", "aliases": []}]) == 0
    assert seen == []
    db.close()
