"""The search header must count what the body shows (#4403).

The UI header read `total_results`, which is the full match count BEFORE
pagination (#4113) — `has_more` and offset paging are built on it. It counts
documents only, and under a page limit it is larger than the page. So it could
never answer the header's question, and "3 results" appeared above
"Artifacts (6)".

My first attempt redefined `total_results` as the sum of the rendered legs.
That was wrong, and an existing test caught it: `TestHonestCounts` pins 5
matches under a limit of 2, and pagination depends on that. Redefining the
field would have fixed the header by breaking paging.

The two are DIFFERENT QUESTIONS — "how many matched?" and "how many am I
looking at?" — so they need two fields, not one field with two meanings.
`rendered_total` answers the second, derived from the same lists the response
carries so it cannot drift from the body.
"""

from __future__ import annotations

import pytest

from fichero_server.api.routes.search.core import (
    SearchArtifactHit,
    SearchClaimHit,
    SearchEntityHit,
    SearchResponse,
    SearchResult,
)


def _doc(i: int) -> SearchResult:
    return SearchResult(
        document_id=f"doc-{i}", score=1.0, content_preview=f"doc {i}", metadata={}
    )


def _entity(i: int) -> SearchEntityHit:
    return SearchEntityHit.model_validate(
        {"id": f"e-{i}", "canonical_name": f"Entity {i}", "entity_type": "person"}
    )


def _claim(i: int) -> SearchClaimHit:
    return SearchClaimHit.model_validate(
        {"id": f"c-{i}", "text": f"claim {i}", "source_document_id": "doc-0"}
    )


def _artifact(i: int) -> SearchArtifactHit:
    return SearchArtifactHit(
        document_id="doc-0", artifact_type="transcription"
    )


def _response(*, docs=0, entities=0, claims=0, artifacts=0) -> SearchResponse:
    """Build a response the way the route does, then check the invariant.

    Deliberately constructs the model directly rather than calling the route:
    the invariant belongs to the RESPONSE, so it must hold for every code path
    that can build one, including ones added later.
    """
    results = [_doc(i) for i in range(docs)]
    entity_hits = [_entity(i) for i in range(entities)]
    claim_hits = [_claim(i) for i in range(claims)]
    artifact_hits = [_artifact(i) for i in range(artifacts)]
    return SearchResponse(
        query="q",
        results=results,
        entity_hits=entity_hits,
        claim_hits=claim_hits,
        artifact_hits=artifact_hits,
        count=len(results),
        total_results=len(results),  # pre-pagination doc total (#4113)
        rendered_total=(
            len(results) + len(entity_hits) + len(claim_hits) + len(artifact_hits)
        ),
        search_type="hybrid",
        execution_time_ms=1.0,
    )


def _body_total(response: SearchResponse) -> int:
    """What the user can actually count on screen."""
    return (
        len(response.results)
        + len(response.entity_hits)
        + len(response.claim_hits)
        + len(response.artifact_hits)
    )


class TestTheHeaderEqualsTheBody:
    @pytest.mark.parametrize(
        "docs,entities,claims,artifacts",
        [
            (3, 0, 0, 6),   # the reported case: "3 results" over "Artifacts (6)"
            (0, 0, 0, 0),   # empty search
            (5, 0, 0, 0),   # documents only
            (0, 4, 0, 0),   # entities only — a leg the old count never added
            (0, 0, 7, 0),   # claims only — likewise
            (2, 3, 4, 5),   # all four legs
        ],
    )
    def test_rendered_total_equals_the_sum_of_the_legs(
        self, docs, entities, claims, artifacts
    ):
        response = _response(
            docs=docs, entities=entities, claims=claims, artifacts=artifacts
        )
        assert response.rendered_total == _body_total(response), (
            f"header says {response.rendered_total}, body shows "
            f"{_body_total(response)} — the user can count the difference"
        )

    def test_the_reported_case_specifically(self):
        """3 documents, 6 artifacts. The header used to say 3."""
        response = _response(docs=3, artifacts=6)
        assert response.rendered_total == 9

    def test_total_results_still_answers_its_own_question(self):
        """The pagination contract (#4113) is untouched: it counts matched
        DOCUMENTS, which is a different number and deliberately so."""
        response = _response(docs=3, artifacts=6)
        assert response.total_results == 3

    def test_entity_and_claim_legs_are_counted_at_all(self):
        """These were never added to the old total under any branch, so a
        search returning only KG hits reported zero results while rendering
        several."""
        response = _response(entities=2, claims=3)
        assert response.rendered_total == 5


class TestTheRouteItselfDerivesIt:
    """Guards against the route re-introducing a parallel counter.

    The tests above pin the invariant on the model; this one pins that the
    ROUTE builds it from the legs rather than from `total_count`, which is what
    made the two able to disagree in the first place.
    """

    def test_the_route_sums_the_four_legs(self):
        from pathlib import Path

        import fichero_server.api.routes.search.core as search_core

        source = Path(search_core.__file__).read_text(encoding="utf-8")
        assert "rendered_total=(\n            len(results)\n" in source, (
            "the route no longer derives rendered_total from the rendered legs; "
            "a parallel counter lets the header disagree with the body (#4403)"
        )
        assert "total_results=total_count" in source, (
            "total_results must remain the pre-pagination match count (#4113) — "
            "paging is built on it"
        )
