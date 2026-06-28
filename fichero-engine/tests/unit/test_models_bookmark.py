"""Document.bookmark must not silently swallow a corrupt bookmark (#2507)."""

from __future__ import annotations

from fichero.models import Document


def test_corrupt_bookmark_logs_warning_and_returns_none(caplog) -> None:
    """A stored-but-undecodable bookmark is a real failure (lost security-scoped
    access) — it must be logged, not silently read as 'no bookmark'."""
    doc = Document(id="doc-bm-1", name="ext.jpg")
    doc.metadata["bookmark"] = "not-valid-base64!"  # raises on b64decode

    with caplog.at_level("WARNING"):
        result = doc.bookmark

    assert result is None
    assert any(
        "Could not decode security-scoped bookmark" in rec.message
        and "doc-bm-1" in rec.message
        for rec in caplog.records
    ), "a corrupt bookmark must be logged with the document id, not swallowed"


def test_valid_bookmark_round_trips_without_warning(caplog) -> None:
    """Regression: a healthy bookmark decodes cleanly and emits no warning."""
    doc = Document(id="doc-bm-2", name="ext.jpg")
    doc.set_bookmark(b"raw-bookmark-bytes")

    with caplog.at_level("WARNING"):
        result = doc.bookmark

    assert result == b"raw-bookmark-bytes"
    assert not any("bookmark" in rec.message.lower() for rec in caplog.records)


def test_missing_bookmark_returns_none_silently(caplog) -> None:
    """No bookmark at all is a legitimate empty state — no warning, just None."""
    doc = Document(id="doc-bm-3", name="ext.jpg")

    with caplog.at_level("WARNING"):
        result = doc.bookmark

    assert result is None
    assert not any("bookmark" in rec.message.lower() for rec in caplog.records)
