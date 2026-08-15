from __future__ import annotations

from fichero_server.models.knowledge import KnowledgeClaim
from fichero_server.knowledge.paragraph import ParagraphStyle, render_paragraph_claims
from fichero_server.workflows.tools._entity_writer import save_claim


def _seed_claim(
    db,
    *,
    claim_id: str,
    subject: str,
    verb: str,
    obj: str,
    source_document_id: str,
    source_page_label: str,
    source_excerpt: str,
    source_char_start: int,
    source_char_end: int,
) -> str:
    return save_claim(
        db,
        text=f"{subject} {verb} {obj}",
        source_document_id=source_document_id,
        source_page_label=source_page_label,
        source_excerpt=source_excerpt,
        source_char_start=source_char_start,
        source_char_end=source_char_end,
        source_bbox=[10.0, 20.0, 30.0, 40.0],
        subject_canonical=subject,
        predicate_verb=verb,
        object_phrase=obj,
        confidence=1.0,
        metadata={"claim_id": claim_id},
    )


def test_render_paragraph_claims_list_style_preserves_sources_and_offsets(db) -> None:
    first_id = _seed_claim(
        db,
        claim_id="claim-1",
        subject="Leidy",
        verb="is",
        obj="a miner",
        source_document_id="doc-1",
        source_page_label="12",
        source_excerpt="Leidy is a miner",
        source_char_start=5,
        source_char_end=22,
    )
    second_id = _seed_claim(
        db,
        claim_id="claim-2",
        subject="Leidy",
        verb="is",
        obj="a guide",
        source_document_id="doc-2",
        source_page_label="13",
        source_excerpt="Leidy is a guide",
        source_char_start=31,
        source_char_end=48,
    )

    claims = [
        db.get(KnowledgeClaim, first_id),
        db.get(KnowledgeClaim, second_id),
    ]
    assert all(claim is not None for claim in claims)

    rendered = render_paragraph_claims(
        [claim for claim in claims if claim is not None],
        style=ParagraphStyle.list,
    )

    assert rendered.style == ParagraphStyle.list
    assert "- Leidy is a miner. [1]" in rendered.text
    assert "- Leidy is a guide. [2]" in rendered.text
    assert rendered.citations[0].source_document_id == "doc-1"
    assert rendered.citations[1].source_page_label == "13"
    assert rendered.markers[0].token == "[1]"
    assert rendered.markers[0].start == rendered.text.index("[1]")
    assert rendered.markers[1].token == "[2]"
    assert rendered.markers[1].start == rendered.text.index("[2]")


def test_render_paragraph_endpoint_groups_subjects_and_returns_citations(client, db) -> None:
    first_id = _seed_claim(
        db,
        claim_id="claim-1",
        subject="Leidy",
        verb="is",
        obj="a miner",
        source_document_id="doc-1",
        source_page_label="12",
        source_excerpt="Leidy is a miner",
        source_char_start=5,
        source_char_end=22,
    )
    second_id = _seed_claim(
        db,
        claim_id="claim-2",
        subject="Leidy",
        verb="is",
        obj="a guide",
        source_document_id="doc-2",
        source_page_label="13",
        source_excerpt="Leidy is a guide",
        source_char_start=31,
        source_char_end=48,
    )

    response = client.post(
        "/api/kg/render/paragraph",
        json={"claim_ids": [first_id, second_id], "style": "narrative"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["style"] == "narrative"
    assert body["text"] == "Leidy is a miner and a guide. ¹ ²"
    assert body["citations"][0]["marker_index"] == 1
    assert body["citations"][0]["source_document_id"] == "doc-1"
    assert body["citations"][1]["source_page_label"] == "13"
    assert body["markers"][0]["token"] == "¹"
    assert body["markers"][0]["start"] == body["text"].index("¹")
    assert body["markers"][1]["token"] == "²"
    assert body["markers"][1]["start"] == body["text"].index("²")
