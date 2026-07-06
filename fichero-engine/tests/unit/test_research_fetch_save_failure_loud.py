"""#2507: a failed source-save during document-fetch must surface, not be masked.

execute_document_fetch fetched a URL and optionally saved it as a Layer-1
source. The save was wrapped in `except Exception: pass`, so a DB-write failure
left source_id=None while the response still said success with no error — the
caller believed the page was saved when it wasn't. The fix logs loudly and
reports the save failure in the response error.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import fitz
import pytest

from fichero.models import DocType, Document


class _FakeResp:
    text = "<title>Example</title><body>hi</body>"
    headers = {"content-type": "text/html"}


def _pdf_bytes(pages: list[str]) -> bytes:
    pdf = fitz.open()
    for text in pages:
        page = pdf.new_page()
        page.insert_text((72, 72), text)
    data = pdf.tobytes()
    pdf.close()
    return data


def _patch_fetch_ok():
    """Bypass SSRF gates + the real HTTP GET so only the save path is exercised."""
    return [
        patch(
            "fichero.api.routes.research_tools._is_sandbox_violation",
            AsyncMock(return_value=False),
        ),
        patch(
            "fichero.api.routes.research_tools._is_safe_url",
            AsyncMock(return_value=(True, "")),
        ),
        patch(
            "fichero.api.routes.research_tools._safe_http_get",
            AsyncMock(return_value=_FakeResp()),
        ),
    ]


def test_save_failure_is_reported_not_silently_swallowed(client, db, monkeypatch):
    real_save = db.save

    def _failing_save(obj, *a, **k):
        # Only the fetched web-page source save blows up; everything else real.
        if isinstance(obj, Document) and obj.doc_type == DocType.file:
            raise RuntimeError("disk full")
        return real_save(obj, *a, **k)

    monkeypatch.setattr(db, "save", _failing_save)

    ctxs = _patch_fetch_ok()
    for c in ctxs:
        c.start()
    try:
        r = client.post(
            "/api/research/tools/document-fetch",
            json={"url": "https://example.com", "project_id": "p1", "create_as_source": True},
        )
    finally:
        for c in ctxs:
            c.stop()

    assert r.status_code == 200
    data = r.json()
    # Fetch still succeeded...
    assert data["success"] is True
    # ...but the save failure is surfaced, not masked.
    assert data["source_id"] is None
    assert data["error"] and "failed to save as source" in data["error"]


def test_successful_save_has_no_error(client, db):
    ctxs = _patch_fetch_ok()
    for c in ctxs:
        c.start()
    try:
        r = client.post(
            "/api/research/tools/document-fetch",
            json={"url": "https://example.com", "project_id": "p1", "create_as_source": True},
        )
    finally:
        for c in ctxs:
            c.stop()

    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["source_id"]  # a real id
    assert data["error"] is None


def test_browser_save_pdf_imports_document_and_page_children(client, db):
    pdf_bytes = _pdf_bytes(["Marshall went to Istmina.", "Page two."])

    class _PdfResp:
        content = pdf_bytes
        headers = {"content-type": "application/pdf"}

    ctxs = [
        patch(
            "fichero.api.routes.research_tools._is_sandbox_violation",
            AsyncMock(return_value=False),
        ),
        patch(
            "fichero.api.routes.research_tools._is_safe_url",
            AsyncMock(return_value=(True, "")),
        ),
        patch(
            "fichero.api.routes.research_tools._safe_http_get",
            AsyncMock(return_value=_PdfResp()),
        ),
    ]
    for c in ctxs:
        c.start()
    try:
        r = client.post(
            "/api/research/tools/browser-save",
            json={
                "url": "https://example.com/archive/book.pdf",
                "project_id": "project-1",
            },
        )
    finally:
        for c in ctxs:
            c.stop()

    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["document_name"] == "book.pdf"
    parent = db.get(Document, data["document_id"])
    assert parent is not None
    assert parent.file_type.value == "pdf"
    assert parent.metadata["source_url"] == "https://example.com/archive/book.pdf"
    children = db.query(Document, parent_id=parent.id, doc_type=DocType.page)
    assert [child.sequence for child in children] == [1, 2]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
