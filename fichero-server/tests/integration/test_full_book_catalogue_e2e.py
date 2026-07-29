"""Opt-in full-book Catalogue/KG E2E for tubb2020shift.pdf (#1317)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest


def _book_path() -> Path | None:
    """Path to the opt-in full-book fixture, from FICHERO_FULL_BOOK_E2E_PDF.

    No hardcoded default — the fixture is a personal, machine-specific file, so
    the path must come from the environment (the test skips when it is unset).
    """
    env = os.environ.get("FICHERO_FULL_BOOK_E2E_PDF")
    return Path(env) if env else None


def _full_book_enabled() -> bool:
    return os.environ.get("FICHERO_RUN_FULL_BOOK_E2E") == "1"


def _items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        value = payload.get("items")
        if isinstance(value, list):
            return value
        value = payload.get("entities") or payload.get("claims") or payload.get("citations")
        if isinstance(value, list):
            return value
    return []


def _poll_thread(client, thread_id: str, timeout: float = 900.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/workflows/execution/threads/{thread_id}/status")
        assert response.status_code == 200, response.text
        last = response.json()
        if last.get("state") in {"done", "error", "cancelled"}:
            return last
        time.sleep(2)
    pytest.fail(f"Catalogue workflow did not finish within {timeout}s; last={last}")


def test_items_handles_list_and_envelopes():
    assert _items([{"id": "a"}]) == [{"id": "a"}]
    assert _items({"items": [{"id": "b"}]}) == [{"id": "b"}]
    assert _items({"claims": [{"id": "c"}]}) == [{"id": "c"}]
    assert _items({"unexpected": []}) == []


def test_full_book_e2e_is_opt_in(monkeypatch):
    monkeypatch.delenv("FICHERO_RUN_FULL_BOOK_E2E", raising=False)
    assert not _full_book_enabled()
    monkeypatch.setenv("FICHERO_RUN_FULL_BOOK_E2E", "1")
    assert _full_book_enabled()


def test_book_path_has_no_hardcoded_default(monkeypatch):
    # Regression (#2702): the fixture path must come from the environment, never a
    # hardcoded personal path — unset env yields None so the E2E skips cleanly.
    monkeypatch.delenv("FICHERO_FULL_BOOK_E2E_PDF", raising=False)
    assert _book_path() is None
    monkeypatch.setenv("FICHERO_FULL_BOOK_E2E_PDF", "/tmp/some/book.pdf")
    assert _book_path() == Path("/tmp/some/book.pdf")


def test_tubb2020shift_catalogue_populates_kg(client):
    if not _full_book_enabled():
        pytest.skip("Set FICHERO_RUN_FULL_BOOK_E2E=1 to run the full-book E2E")

    book = _book_path()
    if book is None:
        pytest.skip("Set FICHERO_FULL_BOOK_E2E_PDF to the full-book fixture path")
    if not book.exists():
        pytest.skip(f"Full-book fixture not found: {book}")

    ingest = client.post(
        "/api/ingest/file",
        json={"path": str(book), "copy_mode": False},
    )
    assert ingest.status_code == 200, ingest.text
    document_id = ingest.json()["document_id"]

    workflows_response = client.get("/api/workflows")
    assert workflows_response.status_code == 200, workflows_response.text
    workflows = _items(workflows_response.json())
    catalogue = next(
        (workflow for workflow in workflows if "catalogue" in workflow.get("name", "").lower()),
        None,
    )
    assert catalogue is not None, "Catalogue workflow not found"

    execute = client.post(
        "/api/workflows/execution/execute",
        json={"workflow_id": catalogue["id"], "inputs": {"document_id": document_id}},
    )
    assert execute.status_code in {200, 202}, execute.text
    thread_id = execute.json().get("thread_id")
    assert thread_id

    status = _poll_thread(client, thread_id)
    assert status.get("state") == "done", status

    entities = client.get("/api/entities", params={"document_id": document_id, "limit": 50})
    assert entities.status_code == 200, entities.text
    assert _items(entities.json()), "Catalogue run produced no page/document entities"

    claims = client.get("/api/claims", params={"source_document_id": document_id, "limit": 50})
    assert claims.status_code == 200, claims.text
    claim_items = _items(claims.json())
    assert claim_items, "Catalogue run produced no source-backed claims"
    assert any(
        claim.get("source_page_label") or claim.get("source_page_labels")
        for claim in claim_items
    ), "Claims lack source page labels for OntologyBrowser click-through"

    citations = client.get("/api/citations", params={"document_id": document_id, "limit": 20})
    assert citations.status_code != 500, citations.text
