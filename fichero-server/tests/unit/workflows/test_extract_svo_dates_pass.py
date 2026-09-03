"""Stage 3 writes date claims directly — dates have no entity row (#1470).

Dates are claim-only (`_SECTIONS` declares `entity_type=None` for them), so
`extract_svo_only`'s per-entity loop can never produce a date claim: the loop
iterates persisted KnowledgeEntity rows and stage 2 rightly never upserts one
for a date. When Catalogue became the 1–6 stage chain (2026-09-03) that gap
silenced the timeline probe contract — no `time_start`/`time_end`/`date_values`
ever landed on a claim again. Stage 3 now runs a direct per-record dates pass
(`_SECTION_SCHEMAS["dates"]` + `_write_kg_rows`); this pins it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.llm.language_policy import parse_policy
from fichero_server.models import DocType, Document, FileType
from fichero_server.models.knowledge import KnowledgeClaim
from fichero_server.workflows.tools import extract_svo_only as svo


@pytest.fixture(autouse=True)
def _no_seeding(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    # Keep the language policy off the real app DB.
    monkeypatch.setattr(svo, "configured_policy", lambda: parse_policy(None))


def test_dates_pass_writes_a_date_claim_with_temporal_fields(
    tmp_path: Path, monkeypatch
):
    library_path = tmp_path / "dates.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)
    db.save(
        Document(
            id="d1",
            name="fixture.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content=(
                "Regression Person signed the fixture deed in Regression "
                "Place in 1842."
            ),
        )
    )

    async def fake_structured(**kwargs):
        schema = kwargs.get("schema")
        assert getattr(schema, "__name__", "") == "_Section_Dates", schema
        return schema(
            items=[
                {
                    "date": "1842",
                    "date_normalized": "1842",
                    "verb": "dated",
                    "object": "the fixture deed",
                    "source_text": "in 1842",
                }
            ]
        )

    monkeypatch.setattr(svo, "chat_structured_with_fallback", fake_structured)

    result = asyncio.run(
        svo.extract_svo_only(
            {"documents": [{"id": "d1"}]},
            {
                "library_path": str(library_path),
                "selected_doc_ids": ["d1"],
                "task_id": "dates-pass-test",
            },
            LLMConfig(provider="fake", model="fake-model"),
        )
    )
    assert result["summary"]["claims_extracted"] == 1

    date_claims = [
        c
        for c in db.query(KnowledgeClaim, source_document_id="d1")
        if "1842" in (c.text or "")
    ]
    assert date_claims, "the dates pass wrote no claim"
    claim = date_claims[0]
    assert claim.text == "1842: dated the fixture deed."
    assert claim.time_start or claim.time_end or claim.date_values, (
        "date claim missing parsed temporal fields — the #1470 timeline "
        "probe contract is dark again"
    )
    assert (claim.metadata or {}).get("date_normalized") == "1842"


def test_a_failed_dates_call_loses_one_record_not_the_stage(
    tmp_path: Path, monkeypatch
):
    """Soft-fail parity with the per-entity loop: a dates-model failure is
    logged and skipped, the stage still completes."""
    library_path = tmp_path / "dates-fail.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)
    db.save(
        Document(
            id="d1",
            name="fixture.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content="Some page text without cooperative models.",
        )
    )

    async def exploding(**kwargs):
        raise RuntimeError("model fell over")

    monkeypatch.setattr(svo, "chat_structured_with_fallback", exploding)

    result = asyncio.run(
        svo.extract_svo_only(
            {"documents": [{"id": "d1"}]},
            {
                "library_path": str(library_path),
                "selected_doc_ids": ["d1"],
                "task_id": "dates-fail-test",
            },
            LLMConfig(provider="fake", model="fake-model"),
        )
    )
    assert result["summary"]["claims_extracted"] == 0
    assert result["summary"]["documents_processed"] == 1
