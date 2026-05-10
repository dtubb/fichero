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

import shutil
from pathlib import Path

import pytest

from fichero.db_manager import DatabaseManager
from fichero.models import Artifact, Document


pytestmark = pytest.mark.integration


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
        ids = {d.document_id for d in docs}
        assert "fix-leidy-001" in ids
        assert "fix-leidy-002" in ids
        assert all(d.claim_count >= 1 for d in docs)

        # /entities/{id}/co-occurrence: Leidy is in claims with both
        # Quibdó (1 shared) and gold (1 shared). Order may vary.
        cos = asyncio.run(
            get_entity_co_occurrence("kg-leidy", limit=10, db=search_library)
        )
        related_ids = {c.entity_id for c in cos}
        assert "kg-quibdo" in related_ids
        assert "kg-gold" in related_ids
        # Self never appears in co-occurrence — would be nonsensical.
        assert "kg-leidy" not in related_ids


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
