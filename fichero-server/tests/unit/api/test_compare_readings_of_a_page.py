"""Scoring one reading of a page against another (#5389).

WHY: Fichero has one CER, with a definition and normalisation policies (#3905), and nothing could
reach it, so an imported draft (a Qwen-VL TEI pass) could not be measured against a new reading
(Gemini) at all. Comparing readers, choosing a recipe's model and training all need this number.
Agreement is not accuracy: unless someone is named as having checked the reference, the answer
must say `agreement`; if it said `cer`, an unchecked draft would pass for ground truth.
"""
from __future__ import annotations

import fichero_server.api.routes.document.content_representations  # noqa: F401  (registers the actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import Artifact, SegmentPass

from .seeded_converted_page import seed_page


def _second_reading(db, page, text):
    other = Artifact(document_id=page.id, artifact_type="transcription", provider="google",
                     model="gemini-3-flash", content=text)
    db.save(other)
    return other


def test_two_results_score_as_agreement_with_the_definition(db, client):
    _, page, first = seed_page(db, count=2)
    other = _second_reading(db, page, first.content.replace("a", "o", 1))
    r = client.post(f"/api/documents/{page.id}/readings/compare", json={
        "reference": {"artifact_id": first.id}, "hypothesis": {"artifact_id": other.id}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["measure"] == "agreement"
    assert body["definition"] and "gemini-3-flash" in body["hypothesis_label"]
    [score] = body["scores"]
    assert score["distance"] == 1 and 0 < score["rate"] < 1


def test_a_named_checker_makes_it_cer_and_several_policies_show_the_spread(db, client):
    _, page, first = seed_page(db, count=2)
    other = _second_reading(db, page, first.content.upper())
    r = client.post(f"/api/documents/{page.id}/readings/compare", json={
        "reference": {"artifact_id": first.id}, "hypothesis": {"artifact_id": other.id},
        "reference_checked_by": "Javier", "policies": ["diplomatic", "lenient"]})
    body = r.json()
    assert body["measure"] == "cer" and "checked by Javier" in body["reference_label"]
    assert [s["policy"] for s in body["scores"]] == ["diplomatic", "lenient"]


def test_a_pass_can_be_scored_against_a_result(db, client):
    _, page, first = seed_page(db, count=2)
    registry.invoke(db, "segment.convert_and_edit", {"document_id": page.id},
                    ActionContext(actor="test", is_bootstrap=True))
    [p] = db.query(SegmentPass, document_id=page.id)
    r = client.post(f"/api/documents/{page.id}/readings/compare", json={
        "reference": {"pass_id": p.id}, "hypothesis": {"artifact_id": first.id}})
    assert r.status_code == 200, r.text
    assert r.json()["scores"][0]["reference_chars"] > 0


def test_refusals_are_named_not_numbers(db, client):
    _, page, first = seed_page(db, count=2)
    empty = _second_reading(db, page, "")
    url = f"/api/documents/{page.id}/readings/compare"
    r = client.post(url, json={"reference": {"artifact_id": empty.id}, "hypothesis": {"artifact_id": first.id}})
    assert r.status_code == 422 and "no denominator" in r.text
    r = client.post(url, json={"reference": {"artifact_id": first.id}, "hypothesis": {"artifact_id": first.id},
                               "policies": ["vibes"]})
    assert r.status_code == 422 and "unknown normalisation policy" in r.text
    _, other_page, elsewhere = seed_page(db, count=1)
    r = client.post(url, json={"reference": {"artifact_id": first.id}, "hypothesis": {"artifact_id": elsewhere.id}})
    assert r.status_code == 404
