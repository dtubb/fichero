"""The scan a zero-hit word or a fuzzy search falls back to never reads the vector column (#6783,
`search.scale.no-whole-table-read`). The read is observed where Lance returns the columns."""

from __future__ import annotations

from unittest.mock import patch

import lance
import pytest
from lancedb.table import LanceTable

from fichero_server.db import Database
from fichero_server.models import DocType, Document, FileType


@pytest.fixture()
def project(tmp_path):
    db = Database(tmp_path / "p.duckdb")
    pages = [
        Document(id=f"p{i}", name=f"Page {i}", doc_type=DocType.page, file_type=FileType.image,
                 page_content=f"The acequia of San Felipe was cleared in year {i}.")
        for i in range(20)
    ]
    db.save_many(pages, new=True)
    with patch.object(db, "_embed_texts", side_effect=lambda t, role="passage": [[1.0, 0.0, 0.0, 0.0]] * len(t)):
        db.embed_many(pages)
    yield db
    db.close()


def _search_recording_columns(db: Database, query: str, **kw):
    """Every whole-table read the search makes: the columns it asked for, None when it asked for all of them."""
    seen: list[list[str] | None] = []
    real_to_table = lance.LanceDataset.to_table
    real_to_pandas = LanceTable.to_pandas

    def spy_to_table(self, *args, **kwargs):
        seen.append(kwargs.get("columns"))
        return real_to_table(self, *args, **kwargs)

    def spy_to_pandas(self, *args, **kwargs):
        seen.append(None)
        return real_to_pandas(self, *args, **kwargs)

    with patch.object(lance.LanceDataset, "to_table", spy_to_table), patch.object(LanceTable, "to_pandas", spy_to_pandas):
        out = db.search(query, limit=10, search_type="fulltext", **kw)
    return out, seen


def test_a_word_the_index_misses_is_found_without_reading_vectors(project) -> None:
    # "cequia" is inside "acequia": the text index finds no token, the scan finds the pages.
    (results, total, _stats), seen = _search_recording_columns(project, "cequia")

    assert total == 20
    assert seen, "the scan was expected to run"
    assert all(cols is not None and "vector" not in cols and "vector_int8" not in cols for cols in seen), seen


def test_a_fuzzy_search_is_found_without_reading_vectors(project) -> None:
    (results, total, _stats), seen = _search_recording_columns(project, "acequa", use_fuzzy_match=True)

    assert total == 20
    assert seen
    assert all(cols is not None and "vector" not in cols and "vector_int8" not in cols for cols in seen), seen
