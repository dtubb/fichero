"""Full-text search must work WITHOUT embeddings (2026-08-10, Daniel:
"search doesn't seem to work"): the FTS leg ran over the LanceDB embeddings
table, so an un-embedded corpus — every fresh import — was invisible to
keyword search, and hybrid returned zero for text sitting verbatim in
page_content. The no-embeddings fallback scans documents.page_content.
FIRE-PROOF: this test failed (0 hits everywhere) before the fallback."""

from fichero_server.db import EMBEDDINGS_TABLE
from fichero_server.models import Document, DocType


def _make_corpus(db):
    hit = Document(
        name="guapi.txt",
        path="/tmp/guapi.txt",
        doc_type=DocType.file,
        page_content="Guapi, a medium-sized dog with short spotted hair, stood at the creek and whined.",
    )
    db.save(hit, auto_embed=False)
    miss = Document(
        name="mining.txt",
        path="/tmp/mining.txt",
        doc_type=DocType.file,
        page_content="Artisanal gold mining along the river in the Choco.",
    )
    db.save(miss, auto_embed=False)
    return hit, miss


def test_fulltext_hits_without_embeddings(db):
    hit, _ = _make_corpus(db)
    results, total, stats = db.search(
        query="spotted dog", search_type="fulltext", min_score=0.0, limit=10
    )
    assert [r.document_id for r in results] == [hit.id]
    assert total == 1


def test_hybrid_hits_without_embeddings_and_survives_the_floor(db):
    hit, _ = _make_corpus(db)
    # 0.55 is the app's default min_score floor — a keyword match must survive it.
    results, total, stats = db.search(
        query="spotted dog", search_type="hybrid", min_score=0.55, limit=10
    )
    assert [r.document_id for r in results] == [hit.id]


def test_no_match_stays_empty(db):
    _make_corpus(db)
    results, total, stats = db.search(
        query="submarine volcano", search_type="fulltext", min_score=0.0, limit=10
    )
    assert results == []


def test_reported_search_type_downgrades_when_nothing_is_embedded(db):
    """The stats must name the leg that RAN, not the one requested (2026-08-31).

    With no embeddings table there is no vector leg at all — the search above
    is keyword-only. The stats used to echo "hybrid"/"semantic" straight back,
    which is what the client's "Expanded Search Results" notice reads to decide
    whether meaning-based matching happened. Echoing the request made that
    notice claim semantics over a purely lexical result set.

    FIRE-PROOF: both hybrid and semantic assertions failed before the downgrade.
    """
    _make_corpus(db)
    for requested in ("hybrid", "semantic"):
        _results, _total, stats = db.search(
            query="spotted dog", search_type=requested, min_score=0.0, limit=10
        )
        assert stats["search_type"] == "fulltext", requested

    # An explicit full-text search is unchanged — nothing was downgraded, it
    # was keyword-only by request.
    _results, _total, stats = db.search(
        query="spotted dog", search_type="fulltext", min_score=0.0, limit=10
    )
    assert stats["search_type"] == "fulltext"


def test_reported_search_type_downgrades_when_the_vector_leg_raises(db, monkeypatch):
    """Sibling of the case above: embeddings EXIST but the vector leg fails.

    Same defect, different cause — the stats echoed the requested mode even
    though the semantic ranking never happened, so the client's notice would
    still claim meaning-based matching over a keyword-only (or empty) result
    set. A pure "semantic" request has no second leg at all, so it reports
    "none" rather than a full-text search that never ran.

    FIRE-PROOF: both assertions failed before the except-path downgrade.
    """
    _make_corpus(db)
    # Embeddings look present, so the vector leg is attempted…
    monkeypatch.setattr(db, "_lance_tables", lambda: [EMBEDDINGS_TABLE])

    # …and then fails the way a real embedding backend outage does.
    def _boom(_text):
        raise RuntimeError("embedding backend unavailable")

    monkeypatch.setattr(db, "_embed_text", _boom)

    _results, _total, stats = db.search(
        query="spotted dog", search_type="hybrid", min_score=0.0, limit=10
    )
    assert stats["search_type"] == "fulltext"

    _results, _total, stats = db.search(
        query="spotted dog", search_type="semantic", min_score=0.0, limit=10
    )
    assert stats["search_type"] == "none"
