"""Full Text returns a page once, with its best passage and how many passages matched, and a total that is a
ceiling says so (#6784, `search.results.one-row-per-page`, `search.results.total-is-true`)."""

from __future__ import annotations

from unittest.mock import patch

from fichero_server.db import Database
from fichero_server.models import DocType, Document, FileType

_WORD = "acequia"
_FILLER = (
    "The ledger records the sale of two oxen and a cart at the market of San Felipe, the price paid in silver, "
    "and the names of the witnesses who signed below the clerk. The weather was dry and the road was good. "
)
_THREE_PASSAGES = (_FILLER * 6 + f"The {_WORD} was cleared. ") * 3 + _FILLER * 6
_ONE_PASSAGE = f"The {_WORD} was cleared in the spring. " + _FILLER


def _build(tmp_path, texts: dict[str, str]) -> Database:
    db = Database(tmp_path / "one_row.duckdb")
    pages = [
        Document(
            id=page_id, name=page_id, doc_type=DocType.page, file_type=FileType.image,
            sequence=i, page_content=text,
        )
        for i, (page_id, text) in enumerate(texts.items())
    ]
    db.save_many(pages, new=True)
    with patch.object(db, "_embed_texts", side_effect=lambda ts, *, role="passage": [[1.0, 0.0, 0.0, 0.0]] * len(ts)):
        db.embed_many(pages)
    return db


def test_a_page_matching_in_three_passages_is_one_row_with_its_count(tmp_path) -> None:
    db = _build(tmp_path, {"multi": _THREE_PASSAGES, "single": _ONE_PASSAGE})

    results, total, _stats = db.search(_WORD, limit=10, search_type="fulltext")

    assert sorted(r.document_id for r in results) == ["multi", "single"]
    assert total == 2
    by_id = {r.document_id: r for r in results}
    assert by_id["multi"].metadata["passages_matched"] == 3
    assert by_id["single"].metadata["passages_matched"] == 1
    db.close()


def test_a_total_cut_at_the_candidate_cap_is_reported_as_a_lower_bound(tmp_path) -> None:
    db = _build(tmp_path, {f"p{i:03d}": _ONE_PASSAGE for i in range(40)})

    results, total, stats = db.search(_WORD, limit=5, search_type="fulltext")

    assert len(results) == 5
    assert stats["total_is_lower_bound"] is True
    assert stats["has_more"] is True
    db.close()


def test_a_total_below_the_cap_is_exact(tmp_path) -> None:
    db = _build(tmp_path, {f"p{i:03d}": _ONE_PASSAGE for i in range(3)})

    _results, total, stats = db.search(_WORD, limit=5, search_type="fulltext")

    assert total == 3
    assert stats["total_is_lower_bound"] is False
    db.close()
