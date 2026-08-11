"""Tests for the built-in deterministic `mock` LLM provider (#1566).

The mock provider IS the production path under test here — no
monkeypatching of llm internals. It exists so a full catalogue /
extraction run can be debugged end-to-end (output, persistence, per-page
artifacts, UI) with ZERO paid LLM calls and zero network.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig, _is_local_or_builtin_provider, chat, chat_structured
from fichero_server.models import Artifact, DocType, Document
from fichero_server.llm.providers import ProviderType, get_provider_info
from fichero_server.workflows.tools import extract_all as extract_all_module


def test_mock_registers_as_local_and_builtin():
    """mock inherits every free / no-PAID gate via _is_local_or_builtin_provider."""
    assert _is_local_or_builtin_provider("mock") is True

    info = get_provider_info("mock")
    assert info is not None
    assert info.type is ProviderType.mock
    assert info.is_local is True
    assert info.is_builtin is True
    assert info.default_model == "mock"


@pytest.mark.asyncio
async def test_chat_structured_returns_extraction_instance():
    """chat_structured with provider=mock returns the requested schema."""
    config = LLMConfig(provider="mock", model="mock")
    result = await chat_structured(
        prompt="A page of mock source text describing people and places.",
        schema=extract_all_module._Extraction,
        config=config,
    )
    assert isinstance(result, extract_all_module._Extraction)
    # Grounded SVO so the extraction is not rejected as "thin".
    assert result.people
    assert result.people[0].name
    assert result.people[0].verb
    assert result.people[0].source_text


@pytest.mark.asyncio
async def test_chat_returns_deterministic_string():
    """Plain chat() (catalogue narrative path) returns a fixed string."""
    config = LLMConfig(provider="mock", model="mock")
    first = await chat("Summarise this folder.", config)
    second = await chat("Summarise this folder.", config)
    assert isinstance(first, str)
    assert first
    assert first == second  # deterministic


@pytest.mark.asyncio
async def test_mock_structured_fails_loud_on_unsupported_required_field():
    """Unknown schema with a required-no-default field raises, never drops."""
    from pydantic import BaseModel

    from fichero_server.llm.mock import mock_structured_response

    class _Needy(BaseModel):
        required_field: str  # no default, no default_factory

    with pytest.raises(ValueError, match="required"):
        mock_structured_response(_Needy, "prompt")


@pytest.mark.asyncio
async def test_extract_all_mock_writes_claims_and_artifacts(db, test_package, caplog):
    """A full extract_all run with provider=mock writes KG claim rows +
    per-page Artifact rows, with no exception and no paid-cost warning."""
    from fichero_server.models.knowledge import KnowledgeClaim

    folder = Document(name="Folder", path="/tmp/folder", doc_type=DocType.folder)
    page1 = Document(name="p1", path="/tmp/folder/p1.png", doc_type=DocType.page)
    page2 = Document(name="p2", path="/tmp/folder/p2.png", doc_type=DocType.page)
    db.save(folder)
    db.save(page1)
    db.save(page2)

    state = {
        "library_path": str(test_package),
        "selected_doc_ids": [folder.id],
    }
    llm_config = LLMConfig(provider="mock", model="mock")
    inputs = {
        "text": "Ada signed the ledger in Mockton.",
        "records": [
            {"doc_id": page1.id, "text": "Ada signed the ledger in Mockton."},
            {"doc_id": page2.id, "text": "Ada signed the ledger in Mockton again."},
        ],
        "persist_kg": True,
    }

    with caplog.at_level(logging.WARNING):
        result = await extract_all_module.extract_all(inputs, state, llm_config)

    assert "error" not in result or not result.get("error")

    # KG claim rows persisted (≥1).
    claims = db.query(KnowledgeClaim)
    assert len(claims) >= 1, "expected at least one KnowledgeClaim row"

    # Per-page Artifact rows persisted (≥1).
    artifacts = db.query(Artifact)
    assert len(artifacts) >= 1, "expected at least one Artifact row"

    # No PAID / incurs-cost warning for a free built-in provider.
    text = caplog.text.lower()
    assert "paid" not in text
    assert "incurs cost" not in text


@pytest.mark.asyncio
async def test_extract_all_mock_emits_workflow_change_events(
    app_db,
    monkeypatch,
    tmp_path,
):
    from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

    monkeypatch.setattr(
        "fichero_server.workflows.tools.extractors._build_alias_index",
        lambda _db: [],
    )
    monkeypatch.setattr(
        "fichero_server.knowledge.entity_vectors.index_entity",
        lambda **_kwargs: None,
        raising=False,
    )

    package = tmp_path / f"extract-events-{uuid4().hex}.fichero"
    package.mkdir()
    for child in ("lance", "storage", "files"):
        (package / child).mkdir()
    db = db_manager.get_database(package)

    try:
        folder = Document(name="Folder", path="/tmp/folder", doc_type=DocType.folder)
        page1 = Document(name="p1", path="/tmp/folder/p1.png", doc_type=DocType.page)
        page2 = Document(name="p2", path="/tmp/folder/p2.png", doc_type=DocType.page)
        db.save(folder)
        db.save(page1)
        db.save(page2)

        events: list[tuple[str, dict]] = []

        def _spy_emit(library_path: str, **kwargs) -> None:
            events.append((library_path, kwargs))

        monkeypatch.setattr(
            "fichero_server.workflows.tools._workflow_change_emit.emit_change",
            _spy_emit,
        )

        result = await extract_all_module.extract_all(
            {
                "text": "Ada signed the ledger in Mockton.",
                "records": [
                    {"doc_id": page1.id, "text": "Ada signed the ledger in Mockton."},
                    {"doc_id": page2.id, "text": "Ada signed the ledger in Mockton again."},
                ],
                "persist_kg": True,
            },
            {"library_path": str(package), "selected_doc_ids": [folder.id]},
            LLMConfig(provider="mock", model="mock"),
        )

        assert not result.get("error")
        # Extraction now fans out per-document change events: entity/claim/document
        # (the KG writer) plus artifact.created (the per-page artifact writer). Assert
        # by type rather than by fixed order/length so adding a domain doesn't break it.
        emitted_types = {event[1]["type"] for event in events}
        assert {"entity.updated", "claim.updated"}.issubset(emitted_types)
        assert all(event[0] == str(package) for event in events)
        assert all(event[1]["actor"] == "workflow" for event in events)

        entity_event = next(e[1] for e in events if e[1]["type"] == "entity.updated")
        claim_event = next(e[1] for e in events if e[1]["type"] == "claim.updated")
        assert entity_event["entity_ids"]
        assert claim_event["claim_ids"]

        entity_ids = {entity.id for entity in db.query(KnowledgeEntity)}
        claim_ids = {claim.id for claim in db.query(KnowledgeClaim)}
        assert set(entity_event["entity_ids"]).issubset(entity_ids)
        assert set(claim_event["claim_ids"]).issubset(claim_ids)
    finally:
        db_manager.close_database(package)


@pytest.mark.asyncio
async def test_mock_provider_serves_vision_calls(caplog):
    """#4345: chat() and structured_output() had a mock branch, vision() did
    not — every vision node in a mock run died with "Unknown LLM provider:
    'mock'". The mock is the production path here; no internals are patched."""
    from fichero_server.llm import vision

    one_by_one_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )

    text = await vision(
        images=[one_by_one_png],
        prompt="Describe this image.",
        config=LLMConfig(provider="mock", model="mock"),
    )

    assert isinstance(text, str) and text.strip()
    assert "1 image" in text
    # Deterministic: same inputs, same answer.
    again = await vision(
        images=[one_by_one_png],
        prompt="Describe this image.",
        config=LLMConfig(provider="mock", model="mock"),
    )
    assert again == text
    # ...and prompt-sensitive, so distinct pages stay distinguishable.
    other = await vision(
        images=[one_by_one_png],
        prompt="Transcribe the text.",
        config=LLMConfig(provider="mock", model="mock"),
    )
    assert other != text
