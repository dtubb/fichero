"""A scoped search searches only its scope: every matching page in the scope is found, however many better matches the
rest of the project holds (#6781, `search.scope.narrows-before-ranking`).

5,000 pages with text and passage vectors: a folder of 50 pages that each hold the word once, 2,000 pages outside it
that hold the word five times and sit nearer the query in meaning, and 2,950 pages without it. Before #6781 the scope
was applied after the best 200 passages of the whole project were kept, and the folder search found none of its 50.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fichero_server.db import Database
from fichero_server.models import DocType, Document, FileType

_WORD = "acequia"
_FILLER = (
    "The ledger records the sale of two oxen and a cart at the market of San Felipe, the price paid in silver, "
    "and the names of the witnesses who signed below the clerk. The weather was dry and the road was good. "
)
_IN_RANGE = (2_400_000, 2_400_100)


def _vector(text: str) -> list[float]:
    if text.count(_WORD) >= 2:
        return [1.0, 0.0, 0.0, 0.0]
    if _WORD in text:
        return [0.6, 0.8, 0.0, 0.0]
    return [0.0, 0.0, 1.0, 0.0]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    db = Database(tmp_path_factory.mktemp("scoped") / "scoped.duckdb")
    folder = Document(id="folder-in", name="Letters 1790", doc_type=DocType.folder)
    other = Document(id="folder-out", name="Everything else", doc_type=DocType.folder)
    docs: list[Document] = [folder, other]
    in_scope: list[str] = []
    for i in range(5_000):
        if i < 50:
            text = _FILLER + f"The {_WORD} was cleared in the spring. " + _FILLER
            parent, jdn = folder.id, _IN_RANGE[0] + i
            in_scope.append(f"page-{i:04d}")
        elif i < 2_050:
            text = _FILLER + (f"The {_WORD} of the upper mill. " * 5) + _FILLER
            parent, jdn = other.id, 2_500_000 + i
        else:
            text = _FILLER * 3
            parent, jdn = other.id, 2_500_000 + i
        docs.append(
            Document(
                id=f"page-{i:04d}", name=f"Page {i}", doc_type=DocType.page, file_type=FileType.image,
                parent_id=parent, sequence=i, page_content=text, date_jdn=jdn,
            )
        )
    db.save_many(docs, new=True)
    pages = docs[2:]

    def _vectors(texts: list[str], *, role: str = "passage") -> list[list[float]]:
        return [_vector(t) for t in texts]

    with patch.object(db, "_embed_texts", side_effect=_vectors):
        for start in range(0, len(pages), 500):
            db.embed_many(pages[start : start + 500])
    yield db, folder.id, sorted(in_scope)
    db.close()


@pytest.mark.parametrize("search_type", ["fulltext", "hybrid", "semantic"])
def test_folder_search_finds_every_matching_page_in_the_folder(project, search_type: str) -> None:
    db, folder_id, in_scope = project

    with patch.object(db, "_embed_text", return_value=[1.0, 0.0, 0.0, 0.0]):
        results, total, _stats = db.search(
            _WORD, limit=100, search_type=search_type, filters={"folder_id": folder_id}
        )

    assert sorted(r.document_id for r in results) == in_scope
    assert total == len(in_scope)


@pytest.mark.parametrize("search_type", ["fulltext", "hybrid"])
def test_written_date_search_finds_every_matching_page_in_the_range(project, search_type: str) -> None:
    db, _folder_id, in_scope = project

    with patch.object(db, "_embed_text", return_value=[1.0, 0.0, 0.0, 0.0]):
        results, total, _stats = db.search(
            _WORD, limit=100, search_type=search_type,
            filters={"date_jdn_from": _IN_RANGE[0], "date_jdn_to": _IN_RANGE[1]},
        )

    assert sorted(r.document_id for r in results) == in_scope
    assert total == len(in_scope)


def test_a_range_holding_no_page_finds_nothing(project) -> None:
    db, _folder_id, _in_scope = project

    results, total, _stats = db.search(
        _WORD, limit=100, search_type="fulltext", filters={"date_jdn_from": 1_000, "date_jdn_to": 1_100}
    )

    assert (results, total) == ([], 0)


def test_type_filter_is_applied_before_the_cut(project) -> None:
    db, folder_id, in_scope = project

    results, total, _stats = db.search(
        _WORD, limit=100, search_type="fulltext", filters={"folder_id": folder_id, "doc_type": DocType.page}
    )

    assert sorted(r.document_id for r in results) == in_scope
    assert total == len(in_scope)
