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


class TestPartiallyEmbeddedLibrary:
    """search.zero-results-for-visible-text (#4236): the no-embeddings
    fallback is gated on `if not fulltext_results:` -- the WHOLE result
    set being empty, not per-document coverage. The moment ANY OTHER
    embedded document's passage genuinely matches the query term, that
    gate never opens, and a different, never-embedded document holding
    the SAME term verbatim in `page_content` silently disappears. Proven
    live: a maintainer's real library is never "nothing embedded" (this
    file's other tests) or "everything embedded" -- it is importing
    continuously, so it is ALWAYS partially embedded, and a common name
    recurring across an embedded and a not-yet-embedded document is the
    ordinary case, not an edge case.

    FIRE-PROOF: `test_never_embedded_sibling_is_dropped_by_an_embedded_
    match_*` failed (0 hits) before this behaviour was fixed -- read the
    engine-lane report on #4236 for the exact failure this test pins.
    """

    def _make_corpus(self, db):
        # P: never embedded, holds the query term verbatim.
        never_embedded = Document(
            name="deed.txt", path="/tmp/deed.txt", doc_type=DocType.file,
            page_content="Juan Asprilla sold the mine to Pedro Mosquera in 1799.",
        )
        db.save(never_embedded, auto_embed=False)
        # A sibling that WILL be embedded for real, and genuinely contains
        # the same term -- the actual trigger, not mere embedding presence.
        embedded_match = Document(
            name="census.txt", path="/tmp/census.txt", doc_type=DocType.file,
            page_content="Asprilla appears again in the parish census of 1801.",
        )
        db.save(embedded_match, auto_embed=False)
        assert db.embed(embedded_match) is True
        return never_embedded, embedded_match

    def test_never_embedded_sibling_is_dropped_by_an_embedded_match_hybrid(self, db):
        never_embedded, embedded_match = self._make_corpus(db)
        results, _total, _stats = db.search(
            query="Asprilla", search_type="hybrid", min_score=0.0, limit=10
        )
        doc_ids = [r.document_id for r in results]
        assert embedded_match.id in doc_ids
        assert never_embedded.id in doc_ids, (
            "the never-embedded document holding the query term verbatim "
            "must be found even though a sibling is embedded (#4236)"
        )

    def test_never_embedded_sibling_is_dropped_by_an_embedded_match_fulltext(self, db):
        never_embedded, embedded_match = self._make_corpus(db)
        results, _total, _stats = db.search(
            query="Asprilla", search_type="fulltext", min_score=0.0, limit=10
        )
        doc_ids = [r.document_id for r in results]
        assert embedded_match.id in doc_ids
        assert never_embedded.id in doc_ids

    def test_folder_scope_does_not_change_the_outcome(self, db):
        """Control: this is NOT a folder-scoping bug. The same drop happens
        with or without a folder filter -- folder_id's own recursive walk
        (`_collect_folder_descendants_helper`) is exonerated separately."""
        folder = Document(name="Folder", doc_type=DocType.folder)
        db.save(folder)
        never_embedded, embedded_match = self._make_corpus(db)
        never_embedded.parent_id = folder.id
        db.save(never_embedded)
        embedded_match.parent_id = folder.id
        db.save(embedded_match)

        results, _total, _stats = db.search(
            query="Asprilla",
            search_type="hybrid",
            min_score=0.0,
            limit=10,
            filters={"folder_id": folder.id},
        )
        doc_ids = [r.document_id for r in results]
        assert never_embedded.id in doc_ids, (
            "folder scope must not change the outcome -- if this fails "
            "while the unscoped test above passes, the bug is in folder "
            "filtering, not the fallback gate"
        )

    def test_subfolder_nesting_is_not_the_cause(self, db):
        """Control: a document nested through TWO folder levels is still
        found once the fallback itself is fixed -- ruling out folder DEPTH
        as a contributing factor, separate from #4885's opt-in-recursion
        switches (which this mechanism does not share: folder_id's walk
        is unconditional, not a flag)."""
        outer = Document(name="F", doc_type=DocType.folder)
        db.save(outer)
        inner = Document(name="S", doc_type=DocType.folder, parent_id=outer.id)
        db.save(inner)
        never_embedded = Document(
            name="deed.txt", path="/tmp/deed.txt", doc_type=DocType.file,
            parent_id=inner.id,
            page_content="Juan Asprilla sold the mine to Pedro Mosquera in 1799.",
        )
        db.save(never_embedded, auto_embed=False)

        results, _total, _stats = db.search(
            query="Asprilla",
            search_type="hybrid",
            min_score=0.0,
            limit=10,
            filters={"folder_id": outer.id},
        )
        assert [r.document_id for r in results] == [never_embedded.id]

    def test_an_embedded_but_non_matching_document_does_not_trigger_the_bug(self, db):
        """Control: the trigger is a MATCHING embedded passage, not mere
        embedding presence in the library. An embedded document whose
        content does not contain the query term must not suppress the
        FULLTEXT fallback for an unrelated never-embedded document.

        search_type="fulltext" deliberately: isolates the exact mechanism
        under test (the FTS/fallback gate). A "hybrid" search also runs the
        semantic leg, which can surface `unrelated_embedded` on its own via
        a weak, non-zero cosine similarity at `min_score=0.0` -- a true but
        unrelated fact about semantic search, not the #4236 mechanism this
        control is isolating.
        """
        never_embedded = Document(
            name="deed.txt", path="/tmp/deed.txt", doc_type=DocType.file,
            page_content="Juan Asprilla sold the mine to Pedro Mosquera in 1799.",
        )
        db.save(never_embedded, auto_embed=False)
        unrelated_embedded = Document(
            name="unrelated.txt", path="/tmp/unrelated.txt", doc_type=DocType.file,
            page_content="Nothing about the query term here at all, just filler prose.",
        )
        db.save(unrelated_embedded, auto_embed=False)
        assert db.embed(unrelated_embedded) is True

        results, _total, _stats = db.search(
            query="Asprilla", search_type="fulltext", min_score=0.0, limit=10
        )
        assert [r.document_id for r in results] == [never_embedded.id]

    def test_no_duplicate_when_a_document_is_both_indexed_and_a_fallback_candidate(
        self, db
    ):
        """A document that IS embedded AND genuinely matches the query must
        appear exactly once, not once per leg."""
        embedded_match = Document(
            name="census.txt", path="/tmp/census.txt", doc_type=DocType.file,
            page_content="Asprilla appears in the parish census of 1801.",
        )
        db.save(embedded_match, auto_embed=False)
        assert db.embed(embedded_match) is True

        results, _total, _stats = db.search(
            query="Asprilla", search_type="hybrid", min_score=0.0, limit=10
        )
        matches = [r for r in results if r.document_id == embedded_match.id]
        assert len(matches) == 1


class TestEmbeddedDocIdsCache:
    """#4236 perf follow-up (2026-09-19): `_get_embedded_doc_ids()` is a
    process-wide cache, keyed by library path, invalidated explicitly at
    every embeddings write site rather than re-scanned every search. Prove
    the cache actually refreshes -- a stale cache here would silently
    reopen #4236 through a different door: a document embedded (or
    un-embedded) after the first search either gets wrongly scanned as a
    duplicate, or wrongly skipped and lost.
    """

    def test_cache_refreshes_after_an_embed(self, db):
        # Q exists and is embedded first, purely to make EMBEDDINGS_TABLE
        # exist so the cache path (as opposed to the "no table" early-out)
        # is actually exercised.
        q = Document(
            name="unrelated.txt", path="/tmp/unrelated.txt", doc_type=DocType.file,
            page_content="Nothing relevant here, just filler prose.",
        )
        db.save(q, auto_embed=False)
        assert db.embed(q) is True

        p = Document(
            name="deed.txt", path="/tmp/deed.txt", doc_type=DocType.file,
            page_content="Bilongoro signed the deed in 1799.",
        )
        db.save(p, auto_embed=False)

        # First search primes the cache: EMBEDDINGS_TABLE exists, only Q is
        # embedded, so P is uncovered and is found via the content-scan
        # fallback.
        results, _total, _stats = db.search(
            query="Bilongoro", search_type="fulltext", min_score=0.0, limit=10
        )
        assert [r.document_id for r in results] == [p.id]
        assert db._get_embedded_doc_ids() == {q.id}

        # Embedding P must invalidate the cache (save_vectors write site) --
        # a stale cache would keep re-scanning P as "uncovered" every search
        # even though it is now indexed, and a version-blind cache could
        # equally have kept the OLD id set forever.
        assert db.embed(p) is True
        assert db._get_embedded_doc_ids() == {q.id, p.id}

        # And P must still be found -- now via the index leg, not the
        # fallback -- proving the refresh didn't just change bookkeeping,
        # it kept the document reachable.
        results, _total, _stats = db.search(
            query="Bilongoro", search_type="fulltext", min_score=0.0, limit=10
        )
        assert p.id in [r.document_id for r in results]

    def test_cache_refreshes_after_an_embedding_delete(self, db):
        p = Document(
            name="deed.txt", path="/tmp/deed.txt", doc_type=DocType.file,
            page_content="Quimbalanda signed the deed in 1799.",
        )
        db.save(p, auto_embed=False)
        assert db.embed(p) is True

        # Prime the cache: P is embedded, so it is covered (not scanned).
        db.search(query="Quimbalanda", search_type="fulltext", min_score=0.0, limit=10)
        assert db._get_embedded_doc_ids() == {p.id}

        # Deleting the embedding must invalidate the cache (the
        # delete_embedding write site) -- a stale cache would keep
        # believing P is covered and silently drop it from fulltext
        # results forever, the exact #4236 failure mode through a new door.
        assert db.delete_embedding(p.id) is True
        assert db._get_embedded_doc_ids() == set()

        results, _total, _stats = db.search(
            query="Quimbalanda", search_type="fulltext", min_score=0.0, limit=10
        )
        assert [r.document_id for r in results] == [p.id]


class TestFtsFindsRowsEmbeddedAfterAnEarlierFtsQuery:
    """#4236 perf follow-up, Concern 2 (2026-09-19): the coverage-scoped
    fix assumes an embedded document is always findable by the Lance FTS
    leg. Checked against LanceDB 0.38.0 (installed version): a query only
    skips unindexed fragments when `.fast_search()` is used
    (`LanceFtsQueryBuilder.fast_search`'s own docstring: "Skip a flat
    search of unindexed data... search results will not include unindexed
    data" -- implying the default DOES include it). `grep -rn
    "fast_search\\|create_fts_index" fichero-server/src/` finds neither:
    this codebase never opts into skipping unindexed rows and never builds
    a persisted FTS index at all, so every `query_type="fts"` search is an
    always-current, effectively unindexed live query here. NOT a bug --
    proven directly below, not just argued from the docstring.
    """

    def test_a_document_embedded_after_an_earlier_fts_query_is_still_found(self, db):
        first = Document(
            name="first.txt", path="/tmp/first.txt", doc_type=DocType.file,
            page_content="Zamboronza appears in the first record.",
        )
        db.save(first, auto_embed=False)
        assert db.embed(first) is True

        # An FTS query runs now, before the second document exists at all --
        # if this codebase built a persisted index and only searched it,
        # this is the point a stale index would be captured.
        results, _total, _stats = db.search(
            query="Zamboronza", search_type="fulltext", min_score=0.0, limit=10
        )
        assert [r.document_id for r in results] == [first.id]

        second = Document(
            name="second.txt", path="/tmp/second.txt", doc_type=DocType.file,
            page_content="Quibdonia appears only in the second record.",
        )
        db.save(second, auto_embed=False)
        assert db.embed(second) is True

        # Embedded strictly AFTER the earlier FTS query above -- must still
        # be found by a fresh fulltext query for its unique term.
        results, _total, _stats = db.search(
            query="Quibdonia", search_type="fulltext", min_score=0.0, limit=10
        )
        assert [r.document_id for r in results] == [second.id]


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
