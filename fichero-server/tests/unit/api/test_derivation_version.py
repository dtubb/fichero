"""A cached page text says which derivation wrote it, and an older one is re-derived once.

WHY: `page_content` is a CACHE of `document_text`. #5148 changed the derivation -- a region's own
TextEquiv stopped doubling its lines -- and every page cached before the fix kept the doubled
text, because nothing on those pages changed and only a change refreshed the cache. The stamp
(`DERIVATION_VERSION`, in `Document.metadata`) makes the cache say which derivation produced it;
a read that finds an older stamp re-derives the page once. If the guard below is ignored -- the
derivation's code changes and the version does not -- that is #5148's stale-text bug again: every
existing page silently keeps the old text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
import fichero_server.api.routes.document.segment_readings as sr
from fichero_server.actions.page_text_cache import DERIVATION_STAMP
from fichero_server.models import Document
from tests.unit.api.test_page_text_counts_each_character_once import _imported


def test_the_derivation_cannot_change_without_its_version():
    """Fails when the source of the functions that derive a page's text changes and the pinned
    digest does not. It makes a person DECIDE: if the change alters what a page's text comes out
    as, bump the version (so every cached page is re-derived on its next read) and re-pin; if it
    is a refactor with the same output, re-pin alone and say so in the commit. Re-pinning without
    bumping after a change of output is the #5148 bug: pages cached under the old code keep its
    text."""
    assert sr.derivation_source_digest() == sr.DERIVATION_SOURCE_SHA256, (
        "document_text's derivation changed. If its OUTPUT changed, bump DERIVATION_VERSION; "
        f"either way re-pin DERIVATION_SOURCE_SHA256 = {sr.derivation_source_digest()!r}"
    )


def _reader_content(client, doc_id: str) -> str:
    html = client.get(f"/view/document/{doc_id}").text
    data = json.loads(re.search(r"const documentData = (\{.*?\});\n", html, re.S).group(1))
    return data["pages"][0]["content"]


def test_a_page_cached_under_an_older_derivation_is_rederived_once(db, client, tmp_path: Path, monkeypatch):
    doc_id = _imported(db, tmp_path)
    doc = db.get(Document, doc_id)
    assert doc.metadata.get(DERIVATION_STAMP) == sr.DERIVATION_VERSION, "a refresh stamps the cache"

    # What a library imported before #5148 holds: the doubled text, under the previous version.
    doc.page_content = "北堂書鈔目錄 卷第一 帝王部一 北堂書鈔目錄 卷第一 帝王部一 北堂書鈔目錄 一 北堂書鈔目錄 一"
    doc.metadata = {**doc.metadata, DERIVATION_STAMP: sr.DERIVATION_VERSION - 1}
    db.save(doc)

    calls = []
    original = sr.document_text
    monkeypatch.setattr(sr, "document_text", lambda *a, **k: (calls.append(1), original(*a, **k))[1])

    first = _reader_content(client, doc_id)
    assert first.count("卷第一") == 1, first
    assert len(calls) == 1, "the stale page is re-derived on its first read"
    assert db.get(Document, doc_id).metadata[DERIVATION_STAMP] == sr.DERIVATION_VERSION

    second = _reader_content(client, doc_id)
    assert second == first
    assert len(calls) == 1, "and not again after that"


def test_a_page_that_is_not_a_derived_cache_is_left_alone(db, client, monkeypatch):
    """No working pass: its `page_content` came from somewhere else (OCR, a person) and is not
    this derivation's to rewrite."""
    from fichero_server.models import DocType, FileType, Status

    doc = Document(name="plain", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/plain.jpg", status=Status.completed, page_content="typed by hand")
    db.save(doc)
    calls = []
    original = sr.document_text
    monkeypatch.setattr(sr, "document_text", lambda *a, **k: (calls.append(1), original(*a, **k))[1])
    assert _reader_content(client, doc.id) == "typed by hand"
    assert calls == []
    assert DERIVATION_STAMP not in (db.get(Document, doc.id).metadata or {})
