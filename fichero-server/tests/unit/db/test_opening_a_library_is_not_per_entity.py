"""Opening a library does not visit every entity (#5228).

WHY: the filed-entity backfill ran over EVERY entity at every open, and each unfiled one cost a
document lookup that found nothing: 14,721 on the maintainer's library, ~4.5 s of a 6 s open, on
every launch, and growing with the knowledge graph (50,000 entities would be ~15 s). Filed entities
(the few a person places in the tree) are still re-synced; an unfiled entity's stray mirror row goes
in one statement. If this regresses, opening a large library is slow again and nobody sees why.
"""

from __future__ import annotations

from fichero_server.db import Database
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import EntityType, KnowledgeEntity


def _reopen(path) -> Database:
    return Database(path)


def test_reopening_looks_up_filed_entities_only_and_clears_an_unfiled_mirror(tmp_path, monkeypatch):
    path = tmp_path / "lib.duckdb"
    db = Database(path)
    folder = Document(name="People", doc_type=DocType.folder)
    db.save(folder)
    filed = KnowledgeEntity(canonical_name="Filed", entity_type=EntityType.person, parent_id=folder.id)
    db.save(filed)
    unfiled = [KnowledgeEntity(canonical_name=f"U{i}", entity_type=EntityType.person) for i in range(200)]
    db.save_many(unfiled)
    # A stray mirror row for an unfiled entity (a library from before the mirror kept up).
    db.save(Document(id=unfiled[0].id, name="stray", node_kind="entity"))
    db.close()

    lookups: list[str] = []
    original = Database.get

    def counting_get(self, model, id_):
        if model is Document:
            lookups.append(id_)
        return original(self, model, id_)

    monkeypatch.setattr(Database, "get", counting_get)
    db = _reopen(path)
    try:
        assert len(lookups) < 20, f"opening looked up {len(lookups)} documents -- one per entity again"
        assert db.get(Document, filed.id) is not None, "the filed entity's mirror must remain"
        assert original(db, Document, unfiled[0].id) is None, "the unfiled entity's stray mirror must go"
    finally:
        db.close()


def test_a_slow_open_step_names_itself(tmp_path, monkeypatch, caplog):
    """The guard the maintainer asked for (2026-09-28): if opening ever gets slow, the log says WHICH
    step. With the threshold at zero every step is 'slow', so each must be named."""
    import logging

    monkeypatch.setattr(Database, "SLOW_OPEN_STEP_SECONDS", 0.0)
    with caplog.at_level(logging.WARNING, logger="fichero_server.db"):
        Database(tmp_path / "lib.duckdb").close()
    slow = [r.getMessage() for r in caplog.records if "slow library open step" in r.getMessage()]
    assert any("_backfill_filed_entity_documents" in m for m in slow), slow
    assert any("_materialize_schema" in m for m in slow), slow


def test_one_library_opening_does_not_block_another(tmp_path, monkeypatch):
    """#5228: the manager held ONE lock for a whole open, so at launch every library -- and every
    request for an already-open one -- queued behind whichever library was opening. Now each
    library has its own open lock."""
    import threading
    import time

    from fichero_server.db import manager as manager_module

    mgr = manager_module.DatabaseManager()
    fast, slow = tmp_path / "Fast.fichero", tmp_path / "Slow.fichero"
    fast.mkdir(); slow.mkdir()
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    monkeypatch.setenv("FICHERO_SKIP_DERIVATIVE_RESUME", "1")
    mgr.get_database(fast)  # already open

    real_init = Database.__init__

    def slow_init(self, *args, **kwargs):
        if "Slow.fichero" in str(kwargs.get("path") or (args[0] if args else "")):
            time.sleep(1.5)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(Database, "__init__", slow_init)
    opener = threading.Thread(target=mgr.get_database, args=(slow,))
    opener.start()
    time.sleep(0.2)  # the slow open is under way
    start = time.monotonic()
    mgr.get_database(fast)
    waited = time.monotonic() - start
    opener.join()
    mgr.close_all()
    assert waited < 0.5, f"reaching an open library waited {waited:.2f}s behind another library's open"


def test_reopening_rewrites_only_the_workflow_mirrors_that_changed(tmp_path, monkeypatch):
    """WHY: every open rewrote every workflow's sidebar mirror, ~1 s of each launch on the global
    library though a save already keeps its mirror current (#5228). A missing mirror, an older one,
    and a deleted SYSTEM preset's (it must render) are still written; an up-to-date one is not."""
    from datetime import timedelta

    from fichero_server.models import Workflow

    path = tmp_path / "lib.duckdb"
    db = Database(path)
    current = [Workflow(name=f"W{i}") for i in range(30)]
    for w in current:
        db.save(w)
    missing = Workflow(name="Missing")
    db.save(missing)
    db._execute("DELETE FROM documents WHERE id = $id", {"id": missing.id})
    older = Workflow(name="Older")
    db.save(older)
    db._execute(
        "UPDATE documents SET updated_at = $t WHERE id = $id",
        {"t": older.updated_at - timedelta(days=1), "id": older.id},
    )
    db.close()

    written: list[str] = []
    original = Database._save_workflow_document

    def counting(self, workflow):
        written.append(workflow.id)
        return original(self, workflow)

    monkeypatch.setattr(Database, "_save_workflow_document", counting)
    db = _reopen(path)
    try:
        assert sorted(written) == sorted([missing.id, older.id]), (
            f"opening rewrote {len(written)} workflow mirrors; only the missing and the older one need it"
        )
        assert db.get(Document, missing.id) is not None, "a missing mirror must be written back"
    finally:
        db.close()
