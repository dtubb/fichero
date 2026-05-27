"""Tests for the explicit KG writer workflow node (#1285)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fichero.workflows.tools.kg_writer import kg_writer


def test_kg_writer_forwards_payload_to_helper(monkeypatch):
    calls = []

    class FakeDB:
        pass

    def fake_get_database(library_path):
        return FakeDB()

    def fake_write_kg_rows(
        db,
        section,
        items,
        target_doc_id,
        **kwargs,
    ):
        calls.append(
            {
                "db": db,
                "section": section["name"],
                "items": items,
                "target_doc_id": target_doc_id,
                **kwargs,
            }
        )

    monkeypatch.setattr("fichero.db.db_manager.get_database", fake_get_database)
    monkeypatch.setattr(
        "fichero.workflows.tools.kg_writer._write_kg_rows",
        fake_write_kg_rows,
    )

    payload = [
        {
            "section_name": "people_extract",
            "items": [{"name": "Leidy", "verb": "is", "object": "a miner"}],
            "target_doc_id": "doc-1",
            "page_label": "Page 1",
            "source_excerpt": "Leidy is a miner.",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "grounding_text": "Leidy is a miner.",
        }
    ]

    result = asyncio.run(
        kg_writer(
            {"kg_payload": payload},
            state={"library_path": "/tmp/library"},
            llm_config=SimpleNamespace(provider="openai", model="gpt-4o-mini"),
        )
    )

    assert len(calls) == 1
    assert calls[0]["section"] == "people_extract"
    assert calls[0]["target_doc_id"] == "doc-1"
    assert result["value"] == payload


def test_kg_writer_empty_payload_is_noop_not_error():
    """#1285 — extract_all writes KG inline; downstream kg_writer receives
    an empty payload and must succeed rather than failing the workflow."""
    result = asyncio.run(
        kg_writer(
            {"kg_payload": []},
            state={"library_path": "/tmp/library"},
            llm_config=SimpleNamespace(provider="apple", model="apple"),
        )
    )
    assert "error" not in result
    assert result["value"] == []


def test_kg_writer_missing_payload_key_is_noop_not_error():
    """#1285 — kg_writer receives no kg_payload key at all (empty edge)."""
    result = asyncio.run(
        kg_writer(
            {},
            state={"library_path": "/tmp/library"},
            llm_config=SimpleNamespace(provider="apple", model="apple"),
        )
    )
    assert "error" not in result
