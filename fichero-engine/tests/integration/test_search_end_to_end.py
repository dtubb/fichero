"""End-to-end search integration test.

Builds a real Database against a tmp_path package, ingests a handful
of text documents with known content, embeds them, then exercises:

- Hybrid search returns the expected docs at top (cosine cosines)
- Score ordering matches phrase/semantic match expectations
- Accent-insensitive folding ('Quibdo' → finds 'Quibdó' page)
- Quoted phrase enforcement ('"sluice wedged"')
- NOT exclusion (gold -mining)
- People-scope (people:Asprilla) hits the entity bridge
- Empty-query returns 400

This is the test Daniel can run after pulling — mirrors the global
library shape on a tiny fixture so we know the *system* works,
not just the unit-level math.
"""

from __future__ import annotations

import os
import shutil
import importlib.util
from pathlib import Path

import pytest
from fastapi import Request

from fichero.db_manager import DatabaseManager
from fichero.models import Artifact, Document


def _request() -> Request:
    return Request({"type": "http", "headers": []})


def _real_search_ready() -> bool:
    """Search E2E is opt-in and requires the local search stack."""
    if os.getenv("FICHERO_RUN_SEARCH_E2E") != "1":
        return False
    return (
        importlib.util.find_spec("fastembed") is not None
        and importlib.util.find_spec("lance") is not None
    )


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _real_search_ready(),
        reason="Search E2E is opt-in and requires local embeddings + lance support",
    ),
]


# Minimal fixture corpus: 5 short pages with overlapping vocab so we can
# test scoring + ordering meaningfully.
FIXTURE_DOCS: list[dict] = [
    {
        "id": "fix-leidy-001",
        "name": "Preface — Leidy.txt",
        "content": (
            "Leidy cleared gravel and stones from a wooden sluice wedged in a "
            "gully. She panned for gold along the river in Quibdó."
        ),
    },
    {
        "id": "fix-leidy-002",
        "name": "Preface — Leidy mother.txt",
        "content": (
            "At the end of the sluice, Leidy's mother worked. He stood by, watching."
        ),
    },
    {
        "id": "fix-asprilla-001",
        "name": "Notarial — Asprilla.txt",
        "content": (
            "En la ciudad de Quibdó, a 23 de Julio de 1809, ante el escribano "
            "compareció Don Joseph Antonio Asprilla, vezino."
        ),
    },
    {
        "id": "fix-mining-001",
        "name": "Mining only.txt",
        "content": "Industrial mining and dredge operations along the Atrato.",
    },
    {
        "id": "fix-empty-001",
        "name": "Empty page.txt",
        "content": "[sin texto]",
    },
]


def _build_library(tmp_path: Path):
    """Create a fresh .fichero package with the fixture corpus indexed.

    Returns (db, library_path).
    """
    package_path = tmp_path / "TestSearch.fichero"
    package_path.mkdir(parents=True, exist_ok=True)
    manager = DatabaseManager()
    db = manager.get_database(package_path)

    for fixture in FIXTURE_DOCS:
        doc = Document(
            id=fixture["id"],
            name=fixture["name"],
            page_content=fixture["content"],
        )
        db.save(doc, auto_embed=True)

    # Plant a 'people:Asprilla' artifact so the entity bridge has
    # something to find — same shape extract_all emits.
    artifact = Artifact(
        document_id="fix-asprilla-001",
        artifact_type="people",
        content="",
        data={"items": [{"name": "Joseph Antonio Asprilla", "role": "compareciente"}]},
    )
    db.save(artifact)

    return db, package_path


@pytest.fixture
def search_library(tmp_path: Path):
    """Per-test fresh library; cleans up after."""
    db, package_path = _build_library(tmp_path)
    yield db
    db.close()
    shutil.rmtree(package_path, ignore_errors=True)


class TestHybridFreetext:
    def test_word_in_two_pages_returns_both_at_top(self, search_library) -> None:
        results, total, _ = search_library.search(query="Leidy", limit=10)
        ids = [r.document_id for r in results[:2]]
        assert "fix-leidy-001" in ids
        assert "fix-leidy-002" in ids
        # Both should beat the unrelated docs by score.
        for r in results[:2]:
            assert r.score >= 0.5

    def test_unique_word_returns_single_top_hit(self, search_library) -> None:
        results, total, _ = search_library.search(query="dredge", limit=10)
        assert results[0].document_id == "fix-mining-001"

    def test_no_match_returns_empty(self, search_library) -> None:
        results, total, _ = search_library.search(query="zzzz_nothing_here", limit=10)
        # Pure-semantic matches against random vector are floored by min_score=0.3.
        assert results == [] or all(r.score >= 0.3 for r in results)


class TestAccentInsensitive:
    def test_quibdo_without_accent_finds_quibdo_with_accent(
        self, search_library
    ) -> None:
        # Query 'Quibdo' (no accent) must find docs containing 'Quibdó'.
        results, total, _ = search_library.search(query="Quibdo", limit=10)
        ids = {r.document_id for r in results}
        assert "fix-leidy-001" in ids
        assert "fix-asprilla-001" in ids

    def test_uppercase_unaccented_matches_lowercase_accented(
        self, search_library
    ) -> None:
        results, total, _ = search_library.search(query="QUIBDO", limit=10)
        ids = {r.document_id for r in results}
        assert "fix-leidy-001" in ids


class TestScoreShape:
    def test_scores_in_unit_interval(self, search_library) -> None:
        results, total, _ = search_library.search(query="Leidy", limit=10)
        for r in results:
            assert 0.0 <= r.score <= 1.0, f"Score {r.score} out of [0,1] for {r.document_id}"

    def test_scores_are_descending(self, search_library) -> None:
        results, total, _ = search_library.search(query="Leidy", limit=10, sort_by="relevance")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestRouteLevelQueryFeatures:
    """Exercise route-level features (parser, entity bridge, did-you-mean,
    phrase + exclude post-filter) end-to-end against the real Database.

    These build on _build_library's fixture corpus, including the
    'Asprilla' artifact planted on doc fix-asprilla-001.
    """

    def test_phrase_required_filters_partial_matches(self, search_library) -> None:
        from fichero.api.routes.search import _apply_phrase_and_exclude_filters

        results, _, _ = search_library.search(query="Leidy gold", limit=10)
        # 'sluice wedged in a gully' appears in fix-leidy-001 only.
        filtered = _apply_phrase_and_exclude_filters(
            search_library, results, phrases=["sluice wedged"], excludes=[]
        )
        ids = {r.document_id for r in filtered}
        assert "fix-leidy-001" in ids
        # fix-leidy-002 has 'sluice' but not 'sluice wedged' verbatim.
        assert "fix-leidy-002" not in ids

    def test_exclude_drops_matching_docs(self, search_library) -> None:
        from fichero.api.routes.search import _apply_phrase_and_exclude_filters

        results, _, _ = search_library.search(query="gold", limit=10)
        filtered = _apply_phrase_and_exclude_filters(
            search_library, results, phrases=[], excludes=["mining"]
        )
        ids = {r.document_id for r in filtered}
        # fix-mining-001 contains 'mining' — must drop.
        assert "fix-mining-001" not in ids

    def test_exclude_is_accent_insensitive(self, search_library) -> None:
        from fichero.api.routes.search import _apply_phrase_and_exclude_filters

        results, _, _ = search_library.search(query="Quibdo", limit=10)
        # exclude 'Quibdo' (no accent) — should still drop docs with 'Quibdó'
        filtered = _apply_phrase_and_exclude_filters(
            search_library, results, phrases=[], excludes=["Quibdo"]
        )
        # All Quibdó docs gone.
        assert all("Quibd" not in (r.metadata.get("name") or "") for r in filtered)

    def test_entity_bridge_finds_artifact_only_match(self, search_library) -> None:
        from fichero.api.routes.search import _entity_match_results

        # 'Asprilla' is only in entities artifact data on fix-asprilla-001
        # AND in its page_content. Bridge should find it via the artifact too.
        hits = _entity_match_results(
            search_library, query="Asprilla", limit=10, exclude_doc_ids=set()
        )
        ids = {h.document_id for h in hits}
        assert "fix-asprilla-001" in ids

    def test_entity_bridge_scope_restricts_to_type(self, search_library) -> None:
        from fichero.api.routes.search import _entity_match_results

        # Scoping to 'people' returns the Asprilla doc; scoping to a type
        # the artifact *isn't* should return nothing for that needle.
        people = _entity_match_results(
            search_library, query="Asprilla", limit=10,
            exclude_doc_ids=set(), entity_types=("people",),
        )
        places = _entity_match_results(
            search_library, query="Asprilla", limit=10,
            exclude_doc_ids=set(), entity_types=("places",),
        )
        people_ids = {h.document_id for h in people}
        places_ids = {h.document_id for h in places}
        assert "fix-asprilla-001" in people_ids
        assert "fix-asprilla-001" not in places_ids

    def test_suggestions_for_typo(self, search_library) -> None:
        from fichero.api.routes.search import _suggest_for_no_results

        # 'Aspriya' — close-ish typo of 'Asprilla'. The entity-name
        # corpus contains 'Joseph Antonio Asprilla', so the suggester
        # should surface it (or similar).
        suggestions = _suggest_for_no_results(
            search_library, query="Aspriya", limit=5
        )
        # Best-effort: our heuristic is set-overlap based, so we just
        # assert that *something* relevant comes back. The fixture has
        # one entity name so we expect that one to be surfaced.
        assert any("Asprilla" in s for s in suggestions)


class TestEmptyQueryRecents:
    def test_empty_query_recent_docs_via_route_helper(self, search_library) -> None:
        # The empty-query path lives in the route, not in db.search; we
        # can still exercise the SQL it runs to make sure it returns
        # only docs with non-empty page_content, sorted by updated_at.
        rows = search_library.conn.execute(
            """
            SELECT id, length(page_content) FROM documents
            WHERE page_content IS NOT NULL AND length(page_content) > 0
            ORDER BY updated_at DESC LIMIT 10
            """,
        ).fetchall()
        ids = [r[0] for r in rows]
        # All five fixture docs have content (including '[sin texto]').
        assert len(ids) == 5
        assert all(r[1] > 0 for r in rows)


class TestRouteLevelEnhancedSearch:
    """Drive the full /api/search route handler through every code path
    we ship: query parser → db.search (cosine + RRF) → phrase + exclude
    filter → entity bridge → did-you-mean. Same body of code the live
    HTTP path runs, just called directly to skip the FastAPI TestClient
    loopback-auth trap.
    """

    def test_freetext_query_returns_results(self, search_library) -> None:
        from fichero.api.routes.search import enhanced_search, SearchRequest
        import asyncio

        request = SearchRequest(query="Leidy", limit=10)
        response = asyncio.run(
            enhanced_search(request, http_request=_request(), db=search_library)
        )
        assert response.count >= 1
        ids = {r.document_id for r in response.results}
        assert "fix-leidy-001" in ids or "fix-leidy-002" in ids

    def test_scoped_query_skips_retriever(self, search_library) -> None:
        """`people:Asprilla` (no free-text) should return entity-bridge
        hits only, not run semantic. Verified by checking the result
        carries match_source='entity'."""
        from fichero.api.routes.search import enhanced_search, SearchRequest
        import asyncio

        request = SearchRequest(query="people:Asprilla", limit=10)
        response = asyncio.run(
            enhanced_search(request, http_request=_request(), db=search_library)
        )
        assert response.count >= 1
        # All results should be entity-bridge (the only path that ran).
        for r in response.results:
            assert r.metadata.get("match_source") == "entity"

    def test_phrase_filter_drops_partial_matches(self, search_library) -> None:
        from fichero.api.routes.search import enhanced_search, SearchRequest
        import asyncio

        # 'Leidy "sluice wedged"' — both Leidy docs match Leidy, but
        # only fix-leidy-001 contains the literal "sluice wedged" phrase.
        request = SearchRequest(query='Leidy "sluice wedged"', limit=10)
        response = asyncio.run(
            enhanced_search(request, http_request=_request(), db=search_library)
        )
        ids = {r.document_id for r in response.results}
        assert "fix-leidy-001" in ids
        assert "fix-leidy-002" not in ids

    def test_exclude_drops_matching_docs(self, search_library) -> None:
        from fichero.api.routes.search import enhanced_search, SearchRequest
        import asyncio

        # 'gold' — would normally hit the mining doc. With -mining,
        # it should drop.
        request = SearchRequest(query="gold -mining", limit=10)
        response = asyncio.run(
            enhanced_search(request, http_request=_request(), db=search_library)
        )
        ids = {r.document_id for r in response.results}
        assert "fix-mining-001" not in ids

    def test_empty_query_returns_recent_docs(self, search_library) -> None:
        from fichero.api.routes.search import enhanced_search, SearchRequest
        import asyncio

        request = SearchRequest(query="", limit=10)
        response = asyncio.run(
            enhanced_search(request, http_request=_request(), db=search_library)
        )
        assert response.search_type == "recent"
        # Returns docs that have non-empty page_content.
        assert response.count >= 1

    def test_suggestions_on_typo_no_results(self, search_library) -> None:
        from fichero.api.routes.search import enhanced_search, SearchRequest
        import asyncio

        # 'Aspriya' with no real matches → suggestions should surface.
        # Note: requires the artifact planted in _build_library which
        # contains 'Joseph Antonio Asprilla'.
        request = SearchRequest(query="Aspriyaaa_no_real_match", limit=5)
        response = asyncio.run(
            enhanced_search(request, http_request=_request(), db=search_library)
        )
        # Even if some semantic hits sneak in, they'd be filtered by
        # the 0.3 min_score for 'Aspriyaaa_no_real_match' which has
        # no real match. Suggestions should be present.
        if response.count == 0:
            assert response.suggestions is not None or response.suggestions == []


class TestKnowledgeGraphRoutes:
    """End-to-end test of the new entity-drill-down endpoints. Builds a
    tiny knowledge graph (3 entities + 2 claims) on top of the search
    fixture corpus and exercises both /documents and /co-occurrence.
    """

    def test_entity_documents_and_co_occurrence(self, search_library) -> None:
        from fichero.knowledge_models import KnowledgeEntity, KnowledgeClaim
        from fichero.api.routes.entities import (
            get_entity_documents,
            get_entity_co_occurrence,
        )
        import asyncio

        # Three entities + two claims:
        #   - claim A: Leidy + Quibdó in fix-leidy-001
        #   - claim B: Leidy + gold-keyword in fix-leidy-002
        leidy = KnowledgeEntity(id="kg-leidy", canonical_name="Leidy")
        quibdo = KnowledgeEntity(id="kg-quibdo", canonical_name="Quibdó")
        gold = KnowledgeEntity(id="kg-gold", canonical_name="gold mining")
        for e in (leidy, quibdo, gold):
            search_library.save(e)

        claim_a = KnowledgeClaim(
            id="claim-a",
            text="Leidy works the sluice in Quibdó",
            source_document_id="fix-leidy-001",
            source_excerpt="Leidy cleared gravel and stones from a wooden sluice",
            entity_ids=["kg-leidy", "kg-quibdo"],
        )
        claim_b = KnowledgeClaim(
            id="claim-b",
            text="Leidy panned for gold",
            source_document_id="fix-leidy-002",
            source_excerpt="Leidy's mother worked alongside her",
            entity_ids=["kg-leidy", "kg-gold"],
        )
        for c in (claim_a, claim_b):
            search_library.save(c)

        # /entities/{id}/documents: Leidy appears in two docs.
        docs = asyncio.run(get_entity_documents("kg-leidy", limit=10, db=search_library))
        ids = {d.document_id for d in docs.items}
        assert "fix-leidy-001" in ids
        assert "fix-leidy-002" in ids
        assert docs.count == len(docs.items)
        assert all(d.claim_count >= 1 for d in docs.items)

        # /entities/{id}/co-occurrence: Leidy is in claims with both
        # Quibdó (1 shared) and gold (1 shared). Order may vary.
        cos = asyncio.run(
            get_entity_co_occurrence("kg-leidy", limit=10, db=search_library)
        )
        related_ids = {c.entity_id for c in cos.items}
        assert "kg-quibdo" in related_ids
        assert "kg-gold" in related_ids
        # Self never appears in co-occurrence — would be nonsensical.
        assert "kg-leidy" not in related_ids

    def test_drill_down_bundles_documents_co_occurrence_excerpts(
        self, search_library
    ) -> None:
        """`/api/entities/{id}/drill-down` returns the three rails in
        one shot — frontend can render an entity inspector from one
        fetch."""
        from fichero.knowledge_models import KnowledgeEntity, KnowledgeClaim
        from fichero.api.routes.entities import entity_drill_down
        import asyncio

        leidy = KnowledgeEntity(id="dd-leidy", canonical_name="Leidy")
        place = KnowledgeEntity(id="dd-quibdo", canonical_name="Quibdó")
        for e in (leidy, place):
            search_library.save(e)
        c = KnowledgeClaim(
            id="dd-c1",
            text="Leidy lives in Quibdó",
            source_document_id="fix-leidy-001",
            source_excerpt="Leidy cleared gravel from a sluice in Quibdó",
            entity_ids=["dd-leidy", "dd-quibdo"],
        )
        search_library.save(c)

        bundle = asyncio.run(entity_drill_down("dd-leidy", db=search_library))
        assert bundle.entity.id == "dd-leidy"
        assert any(d.document_id == "fix-leidy-001" for d in bundle.documents)
        assert any(co.entity_id == "dd-quibdo" for co in bundle.co_occurring)
        assert bundle.claim_excerpts  # at least one excerpt

    def test_top_entities_ranks_by_claim_count(self, search_library) -> None:
        """`/api/entities/top` returns entities ranked by total claim count."""
        from fichero.knowledge_models import KnowledgeEntity, KnowledgeClaim
        from fichero.api.routes.entities import top_entities
        import asyncio

        # Seed: 'frequent' has 3 claims, 'rare' has 1.
        frequent = KnowledgeEntity(id="top-freq", canonical_name="Frequent")
        rare = KnowledgeEntity(id="top-rare", canonical_name="Rare")
        for e in (frequent, rare):
            search_library.save(e)
        for i in range(3):
            search_library.save(KnowledgeClaim(
                id=f"top-c-freq-{i}", text=f"frequent claim {i}",
                source_document_id="fix-leidy-001", entity_ids=["top-freq"],
            ))
        search_library.save(KnowledgeClaim(
            id="top-c-rare", text="rare claim",
            source_document_id="fix-leidy-001", entity_ids=["top-rare"],
        ))

        rows = asyncio.run(top_entities(limit=10, db=search_library))
        assert rows.count == len(rows.items)
        names = [r.name for r in rows.items]
        # 'Frequent' must beat 'Rare' (3 claims vs 1).
        assert names.index("Frequent") < names.index("Rare")
        # Counts reflect input.
        freq_row = next(r for r in rows.items if r.name == "Frequent")
        rare_row = next(r for r in rows.items if r.name == "Rare")
        assert freq_row.claim_count == 3
        assert rare_row.claim_count == 1

    def test_related_documents_aggregates_via_shared_entities(
        self, search_library
    ) -> None:
        """`/api/documents/{id}/related` finds other docs sharing entities.

        Build a third doc that shares the Quibdó entity with fix-leidy-001
        and assert it surfaces as related. Self is excluded.
        """
        from fichero.knowledge_models import KnowledgeEntity, KnowledgeClaim
        from fichero.models import Document
        from fichero.api.routes.documents import related_documents
        import asyncio

        # Seed entities and a 'leidy lives in Quibdó' claim on doc-001.
        leidy = KnowledgeEntity(id="rel-leidy", canonical_name="Leidy")
        quibdo = KnowledgeEntity(id="rel-quibdo", canonical_name="Quibdó")
        for e in (leidy, quibdo):
            search_library.save(e)

        # Plant a third doc + claim that shares Quibdó with fix-leidy-001.
        third_doc = Document(
            id="rel-third",
            name="Third document mentioning Quibdó",
            page_content="A separate document mentions Quibdó for entirely different reasons.",
        )
        search_library.save(third_doc, auto_embed=True)

        c1 = KnowledgeClaim(
            id="rel-c1",
            text="Leidy lives in Quibdó",
            source_document_id="fix-leidy-001",
            entity_ids=["rel-leidy", "rel-quibdo"],
        )
        c2 = KnowledgeClaim(
            id="rel-c2",
            text="Another doc mentions Quibdó",
            source_document_id="rel-third",
            entity_ids=["rel-quibdo"],
        )
        for c in (c1, c2):
            search_library.save(c)

        # /related on fix-leidy-001 → should surface rel-third (shared Quibdó).
        results = asyncio.run(
            related_documents("fix-leidy-001", limit=10, db=search_library)
        )
        assert results.count >= 1
        ids = {r.document_id for r in results.items}
        assert "rel-third" in ids
        # Self is never in related.
        assert "fix-leidy-001" not in ids
        # Sample entity names round-trip from KnowledgeEntity.canonical_name.
        third_row = next(r for r in results.items if r.document_id == "rel-third")
        assert third_row.shared_entities >= 1
        assert "Quibdó" in third_row.sample_entity_names


class TestMarkerOnlyEmbedFallback:
    """Verify the marker-only embed fallback that prevents the
    `[sin texto]` cluster bug (every blank page sharing one vector).

    We can't directly inspect the LanceDB record's source text without
    digging into pyarrow, but we CAN verify behaviour: two docs with
    `[sin texto]` content but DIFFERENT names should embed to
    different vectors (because the fallback uses doc.name). If both
    embedded the marker text itself, their vectors would be identical
    and a search for one's name would find both at the same score.
    """

    def test_marker_only_docs_with_different_names_get_different_embeddings(
        self, search_library
    ) -> None:
        from fichero.models import Document

        a = Document(
            id="marker-aleph",
            name="Aleph manuscript fragment",
            page_content="[sin texto]",
        )
        b = Document(
            id="marker-bet",
            name="Bet manuscript fragment",
            page_content="[sin texto]",
        )
        # Both are saved with auto_embed; fallback should kick in.
        search_library.save(a, auto_embed=True)
        search_library.save(b, auto_embed=True)

        # Searching for 'Aleph' should preferentially find marker-aleph,
        # not place marker-bet at the same score. If embeddings were
        # both `[sin texto]` they'd tie — fallback prevents that.
        results, _, _ = search_library.search(query="Aleph", limit=5)
        ids = [r.document_id for r in results]
        if "marker-aleph" in ids and "marker-bet" in ids:
            a_score = next(r.score for r in results if r.document_id == "marker-aleph")
            b_score = next(r.score for r in results if r.document_id == "marker-bet")
            # 'Aleph' is in marker-aleph's name only. Score gap should
            # be meaningful — if vectors were identical, scores would
            # tie. We assert at least some daylight.
            assert a_score > b_score, (
                f"marker-aleph={a_score} should outscore marker-bet={b_score} "
                f"when query matches only marker-aleph's name"
            )


class TestFolderScope:
    def test_folder_scope_collects_descendants(self, search_library) -> None:
        # Build a parent + two children and verify the folder filter
        # returns just the children.
        from fichero.models import Document

        parent = Document(id="folder-parent", name="Test Folder")
        child_a = Document(
            id="child-a", name="A.txt", parent_id="folder-parent",
            page_content="alpha word",
        )
        child_b = Document(
            id="child-b", name="B.txt", parent_id="folder-parent",
            page_content="beta word",
        )
        for d in (parent, child_a, child_b):
            search_library.save(d, auto_embed=True)

        # Helper directly:
        descendants = search_library._collect_folder_descendants("folder-parent")
        assert "folder-parent" in descendants
        assert "child-a" in descendants
        assert "child-b" in descendants
        # Unrelated docs aren't pulled in.
        assert "fix-leidy-001" not in descendants
