"""Tests for #2542: batched persistence + LanceDB fragment compaction.

The 100k-image save path did one DuckDB write per row and one tiny LanceDB
append per document. These tests cover the additive bulk helpers and the
bounded auto-compaction that relieve that:

- ``Database.save_many``  — one transaction for N rows, all-or-nothing.
- ``Database.embed_many`` — one forward pass + one Lance append for N docs.
- ``Database.compact_vectors`` + the append-count trigger — micro-fragments
  are merged and the data stays intact.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from fichero.db import Database
from fichero.models import Document, DocType


@pytest.fixture
def temp_db():
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test.duckdb"
    db = Database(db_path)
    yield db
    db.close()
    shutil.rmtree(tmpdir)


def _doc(i: int, *, content: str | None = None) -> Document:
    return Document(
        id=f"doc-{i}",
        name=f"Document {i}",
        doc_type=DocType.file,
        page_content=content,
    )


# ---------------------------------------------------------------------------
# save_many
# ---------------------------------------------------------------------------


def test_save_many_inserts_all_rows_like_individual_saves(temp_db):
    """save_many of N docs == N individual saves (same rows readable back)."""
    docs = [_doc(i) for i in range(25)]
    written = temp_db.save_many(docs)
    assert written == 25

    stored = {d.id: d for d in temp_db.all(Document)}
    assert len(stored) == 25
    for d in docs:
        assert stored[d.id].name == d.name


def test_save_many_matches_single_save_path(temp_db):
    """The same instance round-trips identically via save() and save_many()."""
    one = _doc(1, content="hello world")

    temp_db.save(one)
    via_save = temp_db.get(Document, "doc-1")

    temp_db.save_many([one])
    via_save_many = temp_db.get(Document, "doc-1")

    assert via_save_many.model_dump() == via_save.model_dump()


def test_save_many_empty_is_noop(temp_db):
    assert temp_db.save_many([]) == 0
    assert temp_db.all(Document) == []


def test_save_many_is_upsert_idempotent(temp_db):
    temp_db.save_many([_doc(1, content="v1")])
    temp_db.save_many([_doc(1, content="v2")])
    rows = temp_db.all(Document)
    assert len(rows) == 1
    assert rows[0].page_content == "v2"


def test_save_many_rejects_mixed_types(temp_db):
    from fichero.models import Artifact

    art = Artifact(id="a1", document_id="doc-1", artifact_type="ocr")
    with pytest.raises(TypeError):
        temp_db.save_many([_doc(1), art])


def test_save_many_bad_batch_raises_no_silent_partial(temp_db):
    """A constraint-violating row aborts the WHOLE batch — nothing persists.

    The id column is the PK; a None id violates NOT NULL, so the batch must
    roll back rather than write the good rows that preceded it.
    """
    good_before = _doc(1)
    temp_db.save(good_before)  # pre-existing row, must survive the failed batch

    bad_batch = [_doc(2), _doc(3)]
    bad_batch[1].id = None  # type: ignore[assignment]

    with pytest.raises(Exception):
        temp_db.save_many(bad_batch)

    ids = {d.id for d in temp_db.all(Document)}
    # Only the pre-existing row survives; neither doc-2 nor doc-3 was written.
    assert ids == {"doc-1"}


# ---------------------------------------------------------------------------
# embed_many
# ---------------------------------------------------------------------------


def _stub_embedder(db: Database) -> None:
    """Replace the real ONNX embedder with a deterministic 4-dim stub."""

    def fake_embed_texts(texts, *, role="passage"):
        out = []
        for idx, _text in enumerate(texts):
            base = float((idx % 7) + 1)
            out.append([base, base / 2.0, base / 3.0, base / 4.0])
        return out

    def fake_embed_text(text, *, role="query"):
        return fake_embed_texts([text], role="passage")[0]

    db._embed_texts = fake_embed_texts  # type: ignore[method-assign]
    db._embed_text = fake_embed_text  # type: ignore[method-assign]
    db._ensure_embedder = lambda: None  # type: ignore[method-assign]


def test_embed_many_embeds_batch_and_is_searchable(temp_db):
    _stub_embedder(temp_db)
    docs = [_doc(i, content=f"passage text number {i} " * 5) for i in range(8)]
    for d in docs:
        temp_db.save(d)

    count = temp_db.embed_many(docs)
    assert count == 8

    from fichero.db_embeddings import EMBEDDINGS_TABLE

    table = temp_db.lance.open_table(EMBEDDINGS_TABLE)
    rows = table.count_rows()
    assert rows >= 8  # one passage per short doc, at least

    # Every document is retrievable via vector search.
    indexed_doc_ids = {
        r["document_id"]
        for r in table.search().limit(rows).to_list()
    }
    for d in docs:
        assert d.id in indexed_doc_ids


def test_embed_many_empty_is_noop(temp_db):
    _stub_embedder(temp_db)
    assert temp_db.embed_many([]) == 0


# ---------------------------------------------------------------------------
# compaction
# ---------------------------------------------------------------------------


def _fragment_count(db: Database, table_name: str) -> int:
    table = db.lance.open_table(table_name)
    return len(table.to_lance().get_fragments())


def test_compact_vectors_merges_fragments_and_keeps_data(temp_db, monkeypatch):
    """After many micro-appends + explicit compact, fragments drop, data intact."""
    pytest.importorskip("lance")
    monkeypatch.setenv("FICHERO_VECTOR_COMPACTION_INTERVAL", "0")  # disable auto
    tname = "compaction_probe"

    for i in range(12):
        temp_db.save_vectors(tname, [{"id": f"v-{i}", "vector": [0.1 * i, 0.2, 0.3]}])

    before = _fragment_count(temp_db, tname)
    assert before > 1  # micro-appends really did fragment

    results = temp_db.compact_vectors(tname)
    assert results.get(tname) is True

    after = _fragment_count(temp_db, tname)
    assert after < before  # fragments merged

    # Data intact: same rows, all searchable.
    table = temp_db.lance.open_table(tname)
    assert table.count_rows() == 12
    found = temp_db.search_vectors(tname, [0.5, 0.2, 0.3], limit=12)
    assert len(found) == 12


def test_auto_compaction_triggers_at_interval(temp_db, monkeypatch):
    """Reaching the append interval compacts automatically and resets the count."""
    pytest.importorskip("lance")
    monkeypatch.setenv("FICHERO_VECTOR_COMPACTION_INTERVAL", "5")
    tname = "auto_compaction_probe"

    for i in range(5):
        temp_db.save_vectors(tname, [{"id": f"v-{i}", "vector": [0.1 * i, 0.2, 0.3]}])

    # 5th append hits the interval -> compaction ran -> counter reset to 0.
    assert temp_db._vector_append_counts.get(tname, 0) == 0
    assert _fragment_count(temp_db, tname) == 1
    assert temp_db.lance.open_table(tname).count_rows() == 5


def test_compact_vectors_unknown_table_is_false(temp_db):
    results = temp_db.compact_vectors("does_not_exist")
    assert results == {"does_not_exist": False}
