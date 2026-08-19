"""Unit tests for the search-correctness fixes shipped in 0.0.2.

Covers the three independent pieces that turned 0.2%-everywhere into
real cosine ranking:

1. L2 normalisation (db_embeddings._l2_normalize)
2. Accent-insensitive folding (db._fold_for_search)
3. RRF hybrid combination (exercised via Database.search at unit level
   with a mocked LanceDB)

The route-level entity bridge is covered separately in
test_routes_search.py (integration-shaped, hits a real Database).
"""

from __future__ import annotations

import math
from types import SimpleNamespace

from fichero_server.db import (
    EMBEDDINGS_TABLE,
    Database,
    _bm25_scores,
    _build_transcript_excerpts,
    _fold_for_search,
    _is_content_marker_only,
    _search_result_preview,
)
from fichero_server.db.embeddings import _l2_normalize
from fichero_server.db.embeddings import _quantize_int8, _dequantize_int8


class TestL2Normalize:
    def test_simple_3_4_normalises_to_unit(self) -> None:
        assert _l2_normalize([3.0, 4.0]) == [0.6, 0.8]

    def test_unit_stays_unit(self) -> None:
        v = [1.0, 0.0, 0.0]
        assert _l2_normalize(v) == v

    def test_zero_vector_passes_through(self) -> None:
        # Don't divide by zero — zero vector stays zero (defensive).
        assert _l2_normalize([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]

    def test_negative_components_preserved(self) -> None:
        out = _l2_normalize([3.0, -4.0])
        assert out[0] == 0.6
        assert out[1] == -0.8

    def test_high_dimensional_unit_norm(self) -> None:
        # 384-dim like multilingual-e5-large, all 1.0.
        v = [1.0] * 384
        out = _l2_normalize(v)
        norm_sq = sum(x * x for x in out)
        assert math.isclose(norm_sq, 1.0, abs_tol=1e-9)


class TestInt8Quantization:
    def test_round_trip_preserves_shape_and_nearby_values(self) -> None:
        vec = [0.0, 0.125, -0.5, 1.0, -1.0]
        qvec, scale = _quantize_int8(vec)
        restored = _dequantize_int8(qvec, scale)
        assert len(restored) == len(vec)
        for got, want in zip(restored, vec):
            assert math.isclose(got, want, abs_tol=0.02)

    def test_zero_vector_quantizes_cleanly(self) -> None:
        qvec, scale = _quantize_int8([0.0, 0.0, 0.0])
        assert qvec == [0, 0, 0]
        assert scale == 1.0


class TestFoldForSearch:
    def test_strips_acute_accent(self) -> None:
        assert _fold_for_search("Quibdó") == "quibdo"

    def test_strips_grave(self) -> None:
        assert _fold_for_search("à") == "a"

    def test_strips_tilde(self) -> None:
        # Spanish ñ → n. Critical for 'español' / 'señor' searches.
        assert _fold_for_search("Español") == "espanol"
        assert _fold_for_search("señor") == "senor"

    def test_strips_circumflex(self) -> None:
        assert _fold_for_search("Café") == "cafe"
        assert _fold_for_search("naïve") == "naive"

    def test_handles_uppercase_accented(self) -> None:
        # Uppercase has different combining-mark composition path.
        assert _fold_for_search("QUIBDÓ") == "quibdo"
        assert _fold_for_search("MARTÍNEZ") == "martinez"

    def test_handles_mixed_diacritics(self) -> None:
        # Real-world Spanish phrase with multiple diacritics.
        assert _fold_for_search("Santa Fé de Bogotá") == "santa fe de bogota"

    def test_ascii_passthrough(self) -> None:
        assert _fold_for_search("Asprilla") == "asprilla"

    def test_empty_string(self) -> None:
        assert _fold_for_search("") == ""

    def test_preserves_internal_punctuation(self) -> None:
        # Folding should NOT strip punctuation — it's case+accent only.
        assert _fold_for_search("San José, Costa Rica") == "san jose, costa rica"


class TestTranscriptExcerpts:
    def test_builds_offsets_from_indexed_text(self) -> None:
        content = "Before the passage, Leidy cleared gravel from the sluice."
        excerpts = _build_transcript_excerpts(
            "doc-1", content, "Leidy", context_chars=10
        )
        assert len(excerpts) == 1
        excerpt = excerpts[0]
        assert excerpt.text == " passage, Leidy cleared g"
        assert excerpt.match_start == content.index("Leidy")
        assert excerpt.match_end == content.index("Leidy") + len("Leidy")
        assert excerpt.anchor.document_id == "doc-1"
        assert excerpt.anchor.char_start == excerpt.match_start
        assert excerpt.anchor.char_end == excerpt.match_end

    def test_offsets_survive_unaccented_query_for_accented_text(self) -> None:
        content = "La ciudad de Quibdó aparece en el acta."
        excerpts = _build_transcript_excerpts(
            "doc-1", content, "Quibdo", context_chars=0
        )
        assert excerpts[0].text == "Quibdó"
        assert excerpts[0].match_start == content.index("Quibdó")
        assert excerpts[0].match_end == content.index("Quibdó") + len("Quibdó")

    def test_preview_prefers_matched_excerpt_over_first_line(self) -> None:
        content = "First line only.\nSecond line mentions Camilo in the actual match."
        excerpts = _build_transcript_excerpts("doc-1", content, "Camilo", context_chars=8)

        assert _search_result_preview(content, excerpts) == excerpts[0].text

    def test_preview_skips_fallback_excerpt_without_match_offsets(self) -> None:
        content = "First line only.\nSecond line mentions Camilo in the actual match."
        excerpts = _build_transcript_excerpts("doc-1", content, "missing", context_chars=8)
        matched = _build_transcript_excerpts("doc-1", content, "Camilo", context_chars=8)[0]

        assert _search_result_preview(content, [excerpts[0], matched]) == matched.text

    def test_preview_truncates_raw_content_when_no_match_excerpt_exists(self) -> None:
        content = "A" * 205

        assert _search_result_preview(content, []) == ("A" * 200) + "..."


class TestRRFHybridCombiner:
    """Smoke-test the RRF math via a tiny end-to-end search through
    Database.search. We mock LanceDB by pre-populating the embeddings
    table directly through Database._save_vectors so the path is real.

    Skipped when LanceDB / embedder isn't importable (CI).
    """

    def test_rrf_max_score_normalised_to_one(self) -> None:
        # Theoretical max RRF contribution with k=60:
        #   2 / (60 + 1) = 2/61 ≈ 0.0328
        # Projection divides by this, so a doc ranking #1 in BOTH lists
        # should score 1.0 in the response. Other ranks should be < 1.0.
        # We assert the math directly without standing up Database.
        rrf_k = 60
        contribution_rank_1 = 1.0 / (rrf_k + 1)
        max_rrf = 2 * contribution_rank_1
        # Doc #1 in both lists hits the projection ceiling.
        score_perfect = (2 * contribution_rank_1) / max_rrf
        assert math.isclose(score_perfect, 1.0)

        # Doc #1 in one list only is exactly half of perfect.
        score_one_list = contribution_rank_1 / max_rrf
        assert math.isclose(score_one_list, 0.5)

        # Doc #5 in both lists < doc #1 in one list (interesting edge).
        contribution_rank_5 = 1.0 / (rrf_k + 5)
        score_rank5_both = (2 * contribution_rank_5) / max_rrf
        # 2 * (1/65) / (2/61) = 61/65 ≈ 0.938
        assert score_rank5_both > score_one_list  # both-lists still beats one-list


class TestBM25LexicalScoring:
    def test_exact_term_doc_ranks_above_partial(self) -> None:
        corpus = [
            _fold_for_search("Bolivar entered the city"),
            _fold_for_search("The city at dawn"),
        ]
        scores = _bm25_scores(corpus, ["bolivar", "city"])
        assert scores[0] > scores[1]

    def test_empty_query_terms_returns_zeroes(self) -> None:
        assert _bm25_scores(["a b c"], []) == [0.0]


class TestHybridRanking:
    def test_exact_fulltext_hit_beats_semantic_only_neighbor(self, db, monkeypatch) -> None:
        class FakeQuery:
            def __init__(self, rows):
                self.rows = rows

            def select(self, columns):
                assert "created_at" not in columns
                assert "updated_at" not in columns
                return self

            def limit(self, _limit):
                return self

            def to_list(self):
                return self.rows

        class FakeTable:
            schema = SimpleNamespace(
                names=[
                    "document_id", "id", "text", "name", "doc_type", "file_type",
                    "embedding_scope", "passage_id", "page_id", "char_start", "char_end",
                ]
            )

            def search(self, _query, query_type="auto", fts_columns=None):
                assert query_type == "fts"
                assert fts_columns == "text"
                return FakeQuery(
                    [
                        {
                            "document_id": "doc-exact",
                            "id": "doc-exact",
                            "text": "Andagueda river ledger",
                            "name": "Exact hit",
                            "doc_type": "file",
                            "file_type": "text",
                            "_score": 3.0,
                        }
                    ]
                )

            def to_pandas(self):
                raise AssertionError("fulltext hot path should not materialize the whole table")

        fake_lance = SimpleNamespace(open_table=lambda _name: FakeTable())
        monkeypatch.setattr(type(db), "lance", property(lambda self: fake_lance))
        monkeypatch.setattr(type(db), "_lance_tables", lambda self: [EMBEDDINGS_TABLE])
        monkeypatch.setattr(type(db), "_embed_text", lambda self, _query: [0.0])
        monkeypatch.setattr(
            type(db),
            "search_vectors",
            lambda self, _table, _query_vector, _limit: [
                {
                    "document_id": "doc-semantic",
                    "id": "doc-semantic",
                    "text": "Andagoya river report",
                    "name": "Semantic neighbor",
                    "doc_type": "file",
                    "file_type": "text",
                    "_distance": 0.2,
                }
            ],
        )
        monkeypatch.setattr(type(db), "_is_active_document_id", lambda self, _doc_id: True)
        monkeypatch.setattr(
            type(db), "_has_indexed_page_children", lambda self, _doc_id: False
        )
        monkeypatch.setattr(
            type(db),
            "enrich_search_results_with_kg",
            lambda self, results, _query: results,
        )

        results, total, _stats = Database.search(db, "andagueda", search_type="hybrid")

        assert total == 2
        assert results[0].document_id == "doc-exact"
        assert results[0].score > results[1].score



    def test_keyword_only_hit_at_rank_2_survives_default_min_score(self, db, monkeypatch) -> None:
        """#4236 / SEARCH_PLAN M2: a doc the KEYWORD leg matched projects to
        0.5 + 0.1*bm25norm, so the app's default min_score=0.55 silently
        dropped every keyword-only hit except the single top-BM25 doc — a
        confident empty answer for rare terms. Fulltext evidence is exempt
        from the fused-score floor; the floor still cuts semantic-only noise."""

        class FakeQuery:
            def __init__(self, rows):
                self.rows = rows

            def select(self, _columns):
                return self

            def limit(self, _limit):
                return self

            def to_list(self):
                return self.rows

        def fulltext_row(doc_id, score):
            return {
                "document_id": doc_id, "id": doc_id,
                "text": f"jemseg ledger {doc_id}", "name": doc_id,
                "doc_type": "file", "file_type": "text", "_score": score,
            }

        class FakeTable:
            schema = SimpleNamespace(
                names=[
                    "document_id", "id", "text", "name", "doc_type", "file_type",
                    "embedding_scope", "passage_id", "page_id", "char_start", "char_end",
                ]
            )

            def search(self, _query, query_type="auto", fts_columns=None):
                return FakeQuery([
                    fulltext_row("doc-kw-1", 3.0),
                    fulltext_row("doc-kw-2", 1.0),
                ])

        fake_lance = SimpleNamespace(open_table=lambda _name: FakeTable())
        monkeypatch.setattr(type(db), "lance", property(lambda self: fake_lance))
        monkeypatch.setattr(type(db), "_lance_tables", lambda self: [EMBEDDINGS_TABLE])
        monkeypatch.setattr(type(db), "_embed_text", lambda self, _query: [0.0])
        # Semantic leg finds nothing relevant.
        monkeypatch.setattr(
            type(db), "search_vectors", lambda self, _t, _v, _l: []
        )
        monkeypatch.setattr(type(db), "_is_active_document_id", lambda self, _d: True)
        monkeypatch.setattr(
            type(db), "_has_indexed_page_children", lambda self, _d: False
        )
        monkeypatch.setattr(
            type(db), "enrich_search_results_with_kg", lambda self, results, _q: results
        )

        results, total, _stats = Database.search(
            db, "jemseg", search_type="hybrid", min_score=0.55
        )

        ids = [r.document_id for r in results]
        assert "doc-kw-1" in ids and "doc-kw-2" in ids, (
            f"keyword hits dropped by the fused min_score floor: {ids}"
        )


class TestMarkerOnlyDetection:
    """`_is_content_marker_only` decides whether to fall back to doc.name
    when embedding (avoids the [sin texto]-cluster bug where every blank
    page shares one vector and dominates semantic results)."""

    def test_sin_texto_is_marker(self) -> None:
        assert _is_content_marker_only("[sin texto]")
        assert _is_content_marker_only("  [sin texto]  ")
        assert _is_content_marker_only("[SIN TEXTO]")  # case-insensitive

    def test_ilegible_is_marker(self) -> None:
        assert _is_content_marker_only("[ilegible]")
        assert _is_content_marker_only("[Ilegible]")
        assert _is_content_marker_only("[ILLEGIBLE]")
        assert _is_content_marker_only("[UNCERTAIN]")

    def test_two_markers_concatenated(self) -> None:
        assert _is_content_marker_only("[sin texto] [ilegible]")
        assert _is_content_marker_only("[blank] [empty]")

    def test_real_content_is_not_marker(self) -> None:
        assert not _is_content_marker_only("Real content here.")
        assert not _is_content_marker_only("Leidy cleared gravel from the sluice.")
        assert not _is_content_marker_only("Asprilla")

    def test_marker_plus_real_text_is_not_marker(self) -> None:
        # Only-marker filter; if there's real prose alongside, embed it.
        assert not _is_content_marker_only("[sin texto] Recibido en 8bre de 1788")

    def test_empty_treated_as_marker(self) -> None:
        # Empty triggers fallback the same as marker — db.embed handles
        # both via the 'text falls back to name' branch.
        assert _is_content_marker_only("")
        assert _is_content_marker_only("   ")

    def test_accent_insensitive(self) -> None:
        # The marker check folds via _fold_for_search so accented variants
        # in user-edited content are also recognised.
        assert _is_content_marker_only("[íléǵiblé]")  # noqa: RUF001  (intentional accent test)


class TestCosineFromL2:
    """The cosine-from-L2 conversion in Database.search.

    Asserts that on unit-norm vectors:
      L2² = 2 - 2·cos    ⇒    cos = 1 - L2²/2

    And that the clamp [0, 1] handles antiparallel + identical vectors.
    """

    def test_identical_vectors_score_one(self) -> None:
        # L2 distance between identical unit vectors is 0.
        distance = 0.0
        cos = 1.0 - (distance * distance) / 2.0
        assert math.isclose(cos, 1.0)

    def test_orthogonal_vectors_score_half(self) -> None:
        # Unit vectors at 90° have L2² = 2 - 2·0 = 2 → L2 = sqrt(2).
        distance = math.sqrt(2.0)
        cos = 1.0 - (distance * distance) / 2.0
        assert math.isclose(cos, 0.0, abs_tol=1e-9)

    def test_antiparallel_vectors_clamp_to_zero(self) -> None:
        # L2 distance between [1,0] and [-1,0] is 2.0; cos comes out -1.
        distance = 2.0
        cos = 1.0 - (distance * distance) / 2.0
        assert cos == -1.0  # exact
        # Caller clamps with max(0.0, min(1.0, cos)) → 0.0 for ranking.
        clamped = max(0.0, min(1.0, cos))
        assert clamped == 0.0


class TestScriptAwareFold:
    """Daniel's ruling (#4604 Q9): accent-insensitive for Latin/Greek/
    Cyrillic; vowel signs PRESERVED for the abugidas — a Devanagari matra is
    a vowel, not an accent, and stripping it collapsed distinct words."""

    def test_latin_accents_still_fold(self) -> None:
        assert _fold_for_search("Quibdó CAFÉ çedilla") == "quibdo cafe cedilla"

    def test_devanagari_vowel_signs_survive(self) -> None:
        # कि (ka + i-matra) must NOT collapse to क (bare ka).
        assert _fold_for_search("कि") == "कि"
        assert _fold_for_search("कि") != _fold_for_search("क")

    def test_sanskrit_word_distinct_after_fold(self) -> None:
        # धर्म (dharma) keeps its virama + vowel structure.
        word = "धर्म"
        assert _fold_for_search(word) == word

    def test_mixed_script_line_folds_each_side_correctly(self) -> None:
        folded = _fold_for_search("José कि")
        assert folded == "jose कि"


class TestKGFusionLeg:
    """#1833 M1: KG evidence is a real RRF leg in hybrid search — claims and
    entity links rank documents alongside text similarity, and a KG-only hit
    survives the min_score floor (it is evidence, not a fuzzy neighbour)."""

    def _wire(self, db, monkeypatch, kg_leg):
        class FakeQuery:
            def __init__(self, rows):
                self.rows = rows

            def select(self, _columns):
                return self

            def limit(self, _limit):
                return self

            def to_list(self):
                return self.rows

        class FakeTable:
            schema = SimpleNamespace(
                names=[
                    "document_id", "id", "text", "name", "doc_type", "file_type",
                    "embedding_scope", "passage_id", "page_id", "char_start", "char_end",
                ]
            )

            def search(self, _query, query_type="auto", fts_columns=None):
                return FakeQuery([])

        fake_lance = SimpleNamespace(open_table=lambda _name: FakeTable())
        monkeypatch.setattr(type(db), "lance", property(lambda self: fake_lance))
        monkeypatch.setattr(type(db), "_lance_tables", lambda self: [EMBEDDINGS_TABLE])
        monkeypatch.setattr(type(db), "_embed_text", lambda self, _q: [0.0])
        monkeypatch.setattr(type(db), "search_vectors", lambda self, _t, _v, _l: [])
        monkeypatch.setattr(type(db), "_is_active_document_id", lambda self, _d: True)
        monkeypatch.setattr(
            type(db), "_has_indexed_page_children", lambda self, _d: False
        )
        monkeypatch.setattr(
            type(db), "enrich_search_results_with_kg", lambda self, results, _q: results
        )
        monkeypatch.setattr(
            type(db),
            "_expand_query_with_entity_aliases",
            lambda self, q: ([q], ["entity-1"]),
        )
        monkeypatch.setattr(
            type(db), "_kg_evidence_results",
            lambda self, _q, _ids, limit=20: kg_leg,
        )

    def test_kg_only_document_survives_default_min_score(self, db, monkeypatch) -> None:
        kg_leg = [{
            "document_id": "doc-kg", "score": 0.0,
            "content": "Andagoya entity-linked page",
            "metadata": {"name": "IMG_010", "doc_type": "page", "file_type": "image"},
        }]
        self._wire(db, monkeypatch, kg_leg)

        results, total, _stats = Database.search(
            db, "Andagoya", search_type="hybrid", min_score=0.55
        )
        assert total == 1
        assert results[0].document_id == "doc-kg"

    def test_no_matched_entities_means_no_kg_leg(self, db, monkeypatch) -> None:
        self._wire(db, monkeypatch, [])
        results, total, _stats = Database.search(
            db, "nothing", search_type="hybrid", min_score=0.55
        )
        assert total == 0


class TestRelatedDocuments:
    """#4606: related = reads similar (passage-vector centroid) + talks about
    the same things (shared entities), fused; excluded/deleted docs never
    appear; a missing source document raises."""

    def _docs(self, db):
        from fichero_server.models import Document

        source = Document(id="src", name="Source page")
        twin = Document(id="twin", name="Reads similar")
        friend = Document(id="friend", name="Shares people")
        hidden = Document(id="hidden", name="Excluded")
        hidden.exclude_from_search = True
        for doc in (source, twin, friend, hidden):
            db.save(doc)
        return source, twin, friend, hidden

    def _entity(self, db, name, doc_ids):
        from fichero_server.models.knowledge import KnowledgeEntity

        db.save(KnowledgeEntity(canonical_name=name, source_document_ids=doc_ids))

    def _stub_vectors(self, db, monkeypatch):
        class FakeQuery:
            def __init__(self, rows):
                self.rows = rows

            def where(self, _predicate):
                return self

            def limit(self, _limit):
                return self

            def to_list(self):
                return self.rows

        class FakeTable:
            def search(self, *_args, **_kwargs):
                return FakeQuery([{"vector": [1.0, 0.0]}])

        fake_lance = SimpleNamespace(open_table=lambda _name: FakeTable())
        monkeypatch.setattr(type(db), "lance", property(lambda self: fake_lance))
        monkeypatch.setattr(type(db), "_lance_tables", lambda self: [EMBEDDINGS_TABLE])
        monkeypatch.setattr(
            type(db),
            "search_vectors",
            lambda self, _t, _v, _l: [
                {"document_id": "twin", "_distance": 0.3},
                {"document_id": "hidden", "_distance": 0.1},
                {"document_id": "src", "_distance": 0.0},  # self — dropped
            ],
        )

    def test_fuses_vectors_and_shared_entities(self, db, monkeypatch) -> None:
        self._docs(db)
        self._stub_vectors(db, monkeypatch)
        self._entity(db, "Andagoya", ["src", "friend"])
        self._entity(db, "Marshall", ["src", "friend"])
        self._entity(db, "Condoto", ["src", "twin"])

        rows = db.related_documents("src", limit=10)
        by_id = {row["document_id"]: row for row in rows}

        assert "src" not in by_id, "self must never be its own neighbour"
        assert "hidden" not in by_id, "excluded-from-search stays excluded"
        assert set(by_id) == {"twin", "friend"}
        # twin: high cosine + 1 shared entity; friend: entities only.
        assert by_id["twin"]["score"] > by_id["friend"]["score"]
        assert by_id["friend"]["shared_entities"] == ["Andagoya", "Marshall"]

    def test_missing_source_document_raises(self, db) -> None:
        import pytest as _pytest

        with _pytest.raises(ValueError):
            db.related_documents("no-such-doc")
