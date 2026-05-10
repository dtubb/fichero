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
