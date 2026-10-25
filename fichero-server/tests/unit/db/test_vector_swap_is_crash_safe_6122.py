"""#6122 (`search.embedding.change-is-a-re-embed-run`, review ## 1284): the swap of the whole vector folder is crash-safe. A
failure at any step puts the old vectors and the old model back; a death at any step is finished or undone when the library is
next opened; the old folder is never deleted until the swap is verified; entities and claims are embedded once per change."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fichero_server.db import embeddings, vector_swap
from fichero_server.db.embeddings import EMBEDDINGS_TABLE, DatabaseEmbeddingMixin
from fichero_server.models import Document
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

E5 = "intfloat/multilingual-e5-large"
BGE_ID = embeddings.BGE_M3_EMBEDDING_SPACE.model_id
E5_ID = embeddings.PINNED_EMBEDDING_SPACE.model_id


class _Death(BaseException):
    """The process dying: not an Exception, so no `except Exception` in the swap runs."""


@pytest.fixture
def library(db, monkeypatch):
    monkeypatch.delenv(embeddings.EMBED_MODEL_ENV, raising=False)
    seen: list[tuple[str, str]] = []

    def embed_texts(self, texts, *, role="passage"):
        seen.extend((self._get_embedding_model_id(), t) for t in texts)
        return [[float(len(t) % 7), 1.0, 0.0, 0.5] for t in texts]

    monkeypatch.setattr(DatabaseEmbeddingMixin, "_embed_texts", embed_texts)
    monkeypatch.setattr(DatabaseEmbeddingMixin, "_ensure_embedder", lambda self: None)
    for i in range(3):
        db.save(Document(name=f"p{i}", page_content=" ".join(f"Line {j} of page {i} is about the harbour." for j in range(40))))
    db.reindex_all()
    seen.clear()
    return db, seen


def _state(db):
    """What search would see now: the vector rows, the model ids stamped on them, and the project's model."""
    db._lance_db = None  # a fresh open: this is where a crash is recovered
    rows = db.lance.open_table(EMBEDDINGS_TABLE).count_rows()
    ids = {i for ids in db.embedding_table_model_ids().values() for i in ids}
    return rows, ids, db._get_embedding_space().source_model_name


def _package(db) -> Path:
    return Path(str(db.path)).parent


def _raising(step, exc):
    def hook(name):
        if name == step:
            raise exc
    return hook


@pytest.mark.parametrize("step", ["marked", "live-moved", "next-moved", "choice-written"])
def test_a_failure_at_any_step_puts_the_old_vectors_and_the_old_model_back(library, monkeypatch, step):
    db, _seen = library
    old = _state(db)
    assert old[1] == {BGE_ID} and old[2] == "BAAI/bge-m3"
    monkeypatch.setattr(vector_swap, "_hook", _raising(step, OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        db.migrate_embedding_space(confirm=True, to_model=E5)
    assert _state(db) == old, "old vectors, old model, search working"
    assert not (_package(db) / vector_swap.MARKER).exists()
    assert not (_package(db) / "vectors-old").exists()


@pytest.mark.parametrize("step,new", [("marked", False), ("live-moved", False), ("next-moved", False),
                                        ("choice-written", True), ("verified", True)])
def test_a_death_at_any_step_is_finished_or_undone_when_the_library_is_next_opened(library, monkeypatch, step, new):
    db, _seen = library
    old = _state(db)
    monkeypatch.setattr(vector_swap, "_hook", _raising(step, _Death()))
    with pytest.raises(_Death):
        db.migrate_embedding_space(confirm=True, to_model=E5)
    monkeypatch.setattr(vector_swap, "_hook", lambda name: None)
    rows, ids, model = _state(db)  # the next open recovers
    if new:
        assert ids == {E5_ID} and model == E5 and rows == old[0]
    else:
        assert (rows, ids, model) == old, "the old vectors and the old model, search working"
    package = _package(db)
    assert not (package / vector_swap.MARKER).exists() and not (package / "vectors-old").exists()


def test_the_next_run_after_a_death_does_not_delete_the_only_copy(library, monkeypatch):
    db, _seen = library
    old = _state(db)
    monkeypatch.setattr(vector_swap, "_hook", _raising("live-moved", _Death()))
    with pytest.raises(_Death):
        db.migrate_embedding_space(confirm=True, to_model=E5)
    monkeypatch.setattr(vector_swap, "_hook", lambda name: None)
    assert (_package(db) / "vectors-old").exists() and not (_package(db) / "vectors").exists()
    db.migrate_embedding_space(confirm=True, to_model=E5)  # recovers first, then runs
    rows, ids, model = _state(db)
    assert ids == {E5_ID} and model == E5 and rows == old[0]


def test_the_choice_and_the_vectors_change_together_the_choice_file_is_never_half_written(library):
    db, _seen = library
    db.migrate_embedding_space(confirm=True, to_model=E5)
    data = json.loads((_package(db) / "embedding.json").read_text())
    assert data == {"model": E5}
    assert [p.name for p in _package(db).iterdir() if p.name.startswith("embedding.json")] == ["embedding.json"]


def test_a_shadow_of_another_model_is_not_carried_on(library, monkeypatch):
    db, _seen = library
    monkeypatch.setattr(vector_swap, "_hook", _raising("marked", OSError("boom")))
    with pytest.raises(OSError):
        db.migrate_embedding_space(confirm=True, to_model=E5)  # leaves a full e5 shadow behind
    shadow = _package(db) / "vectors-next"
    assert shadow.exists()
    monkeypatch.setattr(vector_swap, "_hook", lambda name: None)
    db.migrate_embedding_space(confirm=True, to_model="BAAI/bge-m3")  # same model: the in-place rebuild, shadow untouched
    assert _state(db)[1] == {BGE_ID}
    # now the other way: stamp the shadow with a wrong model, then change to e5
    import shutil

    shutil.rmtree(shadow)
    db.migrate_embedding_space(confirm=True, to_model=E5)
    assert _state(db)[1] == {E5_ID}


def test_entities_and_claims_are_embedded_once_per_change(library):
    db, seen = library
    db.save(KnowledgeEntity(canonical_name="Santa Marta"))
    db.save(KnowledgeEntity(canonical_name="Cartagena"))
    db.save(KnowledgeClaim(text="The ship reached Cartagena in March."))
    db.embed_entities(db.all(KnowledgeEntity))
    db.embed_claims(db.all(KnowledgeClaim))
    seen.clear()
    db.migrate_embedding_space(confirm=True, to_model=E5)
    texts = [t for _m, t in seen]
    assert {m for m, _t in seen} == {E5_ID}
    assert len(texts) == len(set(texts)), "no entity, claim or page text was embedded twice"
    assert any("Cartagena" in t for t in texts) and any("Santa Marta" in t for t in texts)
