"""`use_fuzzy_match` end-to-end through `Database.search` (#3321, plan #3319).

The Fabel review recorded this parameter as *"accepted by the API, threaded into
`Database.search`, documented — and never used in the body. Typo tolerance is
advertised and silently absent."* That is no longer true: the flag reaches a
real `difflib` pass. This file is the evidence, and the coverage that was
missing while it WAS true.

What existed before: `TestFuzzyMatch` in `tests/unit/db/test_db.py`, which
exercises `_fuzzy_contains_any_term` as a pure function over a pandas Series.
Correct, and it cannot tell whether anything calls it. The parameter could have
gone back to being ignored — reverted, refactored, or lost behind the
`has_embeddings` guard the fulltext branch sits inside — with that suite still
green.

So every test here asserts a DIFFERENCE the flag makes to a real search, and the
suite deliberately includes the direction that a naive fuzzy test never checks:
that fuzzy does not simply match everything. A matcher that returned True for
all rows would satisfy "the typo now finds the document" perfectly, and would
be catastrophic on a historical corpus where the point is to distinguish
"Asprilla" from a different name two edits away.
"""

from __future__ import annotations

import pytest

from fichero_server.db import Database
from fichero_server.models import Document

pytest.importorskip("lancedb")


@pytest.fixture
def library(tmp_path) -> Database:
    """A database with one document and one real embeddings row.

    The row goes through `save_vectors` into the actual LanceDB table rather
    than a fake, because the branch under test is selected by
    `has_embeddings` — a fake table would skip the very gate that decides
    whether fulltext (and therefore fuzzy) runs at all.
    """
    db = Database(tmp_path / "library.duckdb")
    doc = Document(name="Diary", page_content="Faustino Asprilla arrived in Quibdo")
    db.save(doc)
    db.save_vectors(
        "embeddings",
        [
            {
                "id": "e1",
                "document_id": doc.id,
                "text": doc.page_content,
                "name": doc.name,
                "doc_type": "file",
                "file_type": "text",
                "vector": [0.0] * 8,
            }
        ],
    )
    yield db
    db.close()


def _hits(db: Database, query: str, *, fuzzy: bool) -> int:
    results, _total, _meta = db.search(
        query, search_type="fulltext", use_fuzzy_match=fuzzy, limit=5
    )
    return len(results)


# ---------------------------------------------------------------------------
# The flag must CHANGE something
# ---------------------------------------------------------------------------


def test_a_typo_misses_without_the_flag_and_hits_with_it(library):
    """The whole contract, in one assertion pair.

    If this ever passes in both directions the parameter has gone back to
    being decoration, which is exactly what the plan found.
    """
    assert _hits(library, "Asprila", fuzzy=False) == 0
    assert _hits(library, "Asprila", fuzzy=True) == 1


def test_a_two_character_slip_is_still_caught(library):
    """OCR of handwriting does not politely limit itself to one bad character."""
    assert _hits(library, "Aspriya", fuzzy=False) == 0
    assert _hits(library, "Aspriya", fuzzy=True) == 1


def test_an_exact_query_works_either_way(library):
    """Turning fuzzy ON must not LOSE an exact match.

    A matcher that replaced exact containment rather than widening it would
    still pass the typo tests above.
    """
    assert _hits(library, "Asprilla", fuzzy=False) == 1
    assert _hits(library, "Asprilla", fuzzy=True) == 1


# ---------------------------------------------------------------------------
# The direction a naive fuzzy test never checks
# ---------------------------------------------------------------------------


def test_fuzzy_does_not_simply_match_everything(library):
    """The failure that would look like success.

    `_fuzzy_contains_any_term` returning True unconditionally satisfies every
    test above. On Ann's corpus that turns search into "show me the library",
    silently, with no error anywhere.
    """
    assert _hits(library, "zzzznotaword", fuzzy=True) == 0


def test_a_genuinely_different_name_is_not_pulled_in(library):
    """Precision at the edge that matters for a historical corpus.

    Distinguishing two real names is the point; a threshold loose enough to
    merge them is worse than no fuzzy matching at all.
    """
    assert _hits(library, "Bolivar", fuzzy=True) == 0


def test_accent_folding_still_works_independently_of_the_flag(library):
    """Accent tolerance is the folded-scan layer's job, not fuzzy's (#3319).

    Pinned here because the two are easy to conflate: if accent-insensitivity
    ever silently started depending on `use_fuzzy_match`, every default search
    over the Marshall corpus would quietly narrow.
    """
    assert _hits(library, "Quibdó", fuzzy=False) == 1
    assert _hits(library, "Quibdo", fuzzy=False) == 1


# ---------------------------------------------------------------------------
# The measurement itself
# ---------------------------------------------------------------------------


def test_search_returns_a_three_tuple_not_a_container(library):
    """Guards the shape this suite counts through.

    Written after `len()` on the raw return value reported 3 hits for every
    query, including nonsense — `search` returns `(results, total, meta)`, so
    the count was the tuple's arity and the flag appeared to do nothing in
    either direction. A measurement that cannot fail is not evidence.
    """
    value = library.search("Asprilla", search_type="fulltext", limit=5)

    assert isinstance(value, tuple) and len(value) == 3
    results, total, meta = value
    assert isinstance(results, list)
    assert total == len(results)
    assert meta["search_type"] == "fulltext"
