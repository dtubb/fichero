"""Full-text search must work WITHOUT embeddings (2026-08-10, Daniel:
"search doesn't seem to work"): the FTS leg ran over the LanceDB embeddings
table, so an un-embedded corpus — every fresh import — was invisible to
keyword search, and hybrid returned zero for text sitting verbatim in
page_content. The no-embeddings fallback scans documents.page_content.
FIRE-PROOF: this test failed (0 hits everywhere) before the fallback."""
from fichero_server.models import Document, DocType


def _make_corpus(db):
    hit = Document(name="guapi.txt", path="/tmp/guapi.txt", doc_type=DocType.file,
                   page_content="Guapi, a medium-sized dog with short spotted hair, stood at the creek and whined.")
    db.save(hit, auto_embed=False)
    miss = Document(name="mining.txt", path="/tmp/mining.txt", doc_type=DocType.file,
                    page_content="Artisanal gold mining along the river in the Choco.")
    db.save(miss, auto_embed=False)
    return hit, miss


def test_fulltext_hits_without_embeddings(db):
    hit, _ = _make_corpus(db)
    results, total, stats = db.search(query="spotted dog", search_type="fulltext", min_score=0.0, limit=10)
    assert [r.document_id for r in results] == [hit.id]
    assert total == 1


def test_hybrid_hits_without_embeddings_and_survives_the_floor(db):
    hit, _ = _make_corpus(db)
    # 0.55 is the app's default min_score floor — a keyword match must survive it.
    results, total, stats = db.search(query="spotted dog", search_type="hybrid", min_score=0.55, limit=10)
    assert [r.document_id for r in results] == [hit.id]


def test_no_match_stays_empty(db):
    _make_corpus(db)
    results, total, stats = db.search(query="submarine volcano", search_type="fulltext", min_score=0.0, limit=10)
    assert results == []
