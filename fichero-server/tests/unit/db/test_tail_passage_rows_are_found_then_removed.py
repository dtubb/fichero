"""Tail passage rows written by the old cutter are counted by a scan that changes nothing, and removed only when asked
(#6780)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fichero_server.db import Database
from fichero_server.db.embeddings import EMBEDDINGS_TABLE, EmbeddingMigrationConfirmationError
from fichero_server.models import DocType, Document

_PAGE = (
    "Rose early and walked down to the harbour before the bell, the boats already out and the wind from the north. "
    * 8
).strip() + "\n"


def _vectors(texts: list[str], *, role: str = "passage") -> list[list[float]]:
    return [[1.0, 0.0] for _ in texts]


def _rows(db: Database, doc_id: str) -> list[dict]:
    table = db.lance.open_table(EMBEDDINGS_TABLE)
    return table.search().where(f"document_id = '{doc_id}'").limit(10_000).to_list()


def _add_old_cutter_tails(db: Database, doc_id: str, text: str) -> int:
    """The rows the cutter wrote before #6780 after a page's last passage: one per character of the overlap, each from
    one character further on to the same end."""
    rows = sorted(_rows(db, doc_id), key=lambda r: r["char_start"])
    last, end = rows[-1], rows[-1]["char_end"]
    tails = []
    for index, start in enumerate(range(end - 80, end), start=len(rows)):
        if text[start].isspace():
            continue
        row = dict(last)
        row["id"] = row["passage_id"] = f"{doc_id}:passage:{index}:{start}-{end}"
        row["text"], row["char_start"] = text[start:end], start
        tails.append(row)
    db.save_vectors(EMBEDDINGS_TABLE, tails)
    return len(tails)


@pytest.fixture
def db_with_tails(tmp_path):
    db = Database(tmp_path / "tails.duckdb")
    junk = Document(id="page-junk", name="diary - Page 1", doc_type=DocType.page, page_content=_PAGE)
    clean = Document(id="page-clean", name="diary - Page 2", doc_type=DocType.page, page_content=_PAGE.strip())
    db.save(junk)
    db.save(clean)
    with patch.object(db, "_embed_texts", side_effect=_vectors):
        assert db.embed(junk).embedded is True
        assert db.embed(clean).embedded is True
    real = len(_rows(db, "page-junk"))
    tails = _add_old_cutter_tails(db, "page-junk", _PAGE)
    yield db, junk, clean, real, tails
    db.close()


def test_scan_counts_the_tail_rows_and_changes_nothing(db_with_tails) -> None:
    db, _junk, _clean, real, tails = db_with_tails
    assert tails > 60

    scan = db.tail_passage_scan()

    assert scan["pages"] == ["page-junk"]
    assert scan["tail_rows"] == tails
    assert len(_rows(db, "page-junk")) == real + tails


def test_removal_needs_confirmation(db_with_tails) -> None:
    db, _junk, _clean, real, tails = db_with_tails

    with pytest.raises(EmbeddingMigrationConfirmationError):
        db.remove_tail_passages()

    assert len(_rows(db, "page-junk")) == real + tails


def test_removal_leaves_exactly_the_passages_the_cutter_makes_now(db_with_tails) -> None:
    db, junk, clean, real, tails = db_with_tails
    clean_rows = sorted(r["id"] for r in _rows(db, "page-clean"))

    result = db.remove_tail_passages(confirm=True)

    assert result == {"pages": ["page-junk"], "tail_rows": tails, "rows_removed": tails}
    assert len(_rows(db, "page-junk")) == real
    assert db.embedding_is_current(junk)
    assert sorted(r["id"] for r in _rows(db, "page-clean")) == clean_rows
    assert db.embedding_is_current(clean)
    assert db.tail_passage_scan()["pages"] == []


def test_a_page_with_old_tail_rows_is_current_and_is_not_embedded_again(db_with_tails) -> None:
    db, junk, _clean, real, tails = db_with_tails
    assert tails > 60

    with patch.object(db, "_embed_texts", side_effect=AssertionError("embedded again")) as embed_texts:
        assert db.embedding_is_current(junk)
        assert db.embed_unless_current(junk).reason == "unchanged"
        assert db.embed_many_unless_current([junk]) == (1, 0, 1)

    embed_texts.assert_not_called()
    assert len(_rows(db, "page-junk")) == real + tails
