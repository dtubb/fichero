"""Hardening for the bibliography extractor (#908) — pure logic + stubbed I/O.

No real PDF parsing or LLM calls:
- ``fitz.open`` is monkeypatched to return a fake doc with a canned ``.metadata``.
- The LLM boundary (``fichero_server.llm.chat_structured_with_fallback``) and the layer
  functions on the extractor module are monkeypatched, so ``extract_full`` runs
  entirely offline.
Async functions are driven with ``asyncio.run`` (no pytest-asyncio dependency).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import fitz

import fichero_server.bibliography.extractor as ex
from fichero_server.bibliography.extractor import (
    _merge_metadata,
    extract_from_first_pages,
    extract_from_pdf_metadata,
    extract_full,
)
from fichero_server.models import Document


# ===========================================================================
# 1. _merge_metadata — base wins, actual semantics
# ===========================================================================


def test_merge_base_nonempty_wins_over_new():
    merged = _merge_metadata({"title": "Curated"}, {"title": "Fresh", "date": "2020"})
    assert merged["title"] == "Curated"  # base wins
    assert merged["date"] == "2020"  # new key added


def test_merge_skips_empty_and_none_new_values():
    merged = _merge_metadata({}, {"title": "T", "date": "", "authors": [], "x": None})
    assert merged == {"title": "T"}  # falsy new values skipped


def test_merge_empty_base_returns_new_truthy():
    assert _merge_metadata({}, {"title": "Only"}) == {"title": "Only"}


def test_merge_both_empty_is_empty():
    assert _merge_metadata({}, {}) == {}


def test_merge_base_empty_value_is_overwritten_by_new():
    # A falsy base value is NOT protected — new fills it. (Actual code semantics.)
    assert _merge_metadata({"title": ""}, {"title": "X"}) == {"title": "X"}


def test_merge_is_shallow_not_deep():
    # Nested dicts are not deep-merged; a truthy base value wins wholesale.
    merged = _merge_metadata({"metadata": {"a": 1}}, {"metadata": {"b": 2}})
    assert merged == {"metadata": {"a": 1}}


def test_merge_does_not_mutate_base():
    base = {"title": "Curated"}
    _merge_metadata(base, {"date": "2020"})
    assert base == {"title": "Curated"}


# ===========================================================================
# 2. extract_from_pdf_metadata — mapping + graceful degradation
# ===========================================================================


class _FakeDoc:
    def __init__(self, metadata):
        self.metadata = metadata

    def close(self):
        pass


def _patch_fitz(monkeypatch, metadata):
    monkeypatch.setattr(fitz, "open", lambda _p: _FakeDoc(metadata))


def _pdf(tmp_path):
    p = tmp_path / "paper.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return p


def test_pdf_metadata_maps_fields(monkeypatch, tmp_path):
    _patch_fitz(
        monkeypatch,
        {
            "title": "  A Title  ",
            "author": "Jane Doe; Bob Smith",
            "subject": "A subject",
            "keywords": "kw1, kw2",
            "creationDate": "D:20200315120000+00'00'",
        },
    )
    out = extract_from_pdf_metadata(_pdf(tmp_path))
    assert out["title"] == "A Title"  # trimmed
    assert out["authors"] == ["Jane Doe", "Bob Smith"]  # ; and , split
    assert out["date"] == "2020"  # year pulled from PDF date
    assert out["metadata"]["pdf_subject"] == "A subject"
    assert out["metadata"]["pdf_keywords"] == "kw1, kw2"


def test_pdf_metadata_empty_info_degrades_to_empty(monkeypatch, tmp_path):
    _patch_fitz(monkeypatch, {})
    assert extract_from_pdf_metadata(_pdf(tmp_path)) == {}


def test_pdf_metadata_none_info_no_crash(monkeypatch, tmp_path):
    # doc.metadata is None -> `info = doc.metadata or {}` -> {}.
    _patch_fitz(monkeypatch, None)
    assert extract_from_pdf_metadata(_pdf(tmp_path)) == {}


def test_pdf_metadata_non_pdf_suffix_returns_empty(monkeypatch, tmp_path):
    _patch_fitz(monkeypatch, {"title": "x"})
    txt = tmp_path / "notes.txt"
    txt.write_text("hi")
    assert extract_from_pdf_metadata(txt) == {}


def test_pdf_metadata_missing_file_returns_empty(monkeypatch, tmp_path):
    _patch_fitz(monkeypatch, {"title": "x"})
    assert extract_from_pdf_metadata(tmp_path / "nope.pdf") == {}


def test_pdf_metadata_open_failure_returns_empty(monkeypatch, tmp_path):
    def _boom(_p):
        raise RuntimeError("corrupt")

    monkeypatch.setattr(fitz, "open", _boom)
    assert extract_from_pdf_metadata(_pdf(tmp_path)) == {}


def test_pdf_metadata_none_path_returns_empty():
    # Regression: None used to raise TypeError inside Path(None). Now guarded.
    assert extract_from_pdf_metadata(None) == {}
    assert extract_from_pdf_metadata("") == {}


# ===========================================================================
# 3. Async: extract_from_first_pages + extract_full (LLM boundary stubbed)
# ===========================================================================


def test_extract_from_first_pages_maps_llm_result(monkeypatch):
    result = SimpleNamespace(
        title="LLM Title",
        authors=["Doe, Jane"],
        date="2021",
        publisher="ACME",
        journal="",
        volume="",
        issue="",
        pages="",
        abstract="",
        language="en",
        doi=" 10.1/x ",
        isbn="978-3-16-148410-0",
    )

    async def fake_chat(**kwargs):
        return result

    monkeypatch.setattr(ex, "chat_structured_with_fallback", fake_chat, raising=False)
    # The function imports chat_structured_with_fallback from fichero_server.llm locally.
    import fichero_server.llm as llm_mod

    monkeypatch.setattr(llm_mod, "chat_structured_with_fallback", fake_chat, raising=False)

    out = asyncio.run(extract_from_first_pages("cover text", llm_config=object()))
    assert out["title"] == "LLM Title"
    assert out["authors"] == ["Doe, Jane"]
    assert out["date"] == "2021"
    assert out["publisher"] == "ACME"
    assert out["language"] == "en"
    assert out["doi"] == "10.1/x"  # trimmed
    assert out["isbn_13"] == "9783161484100"  # hyphens stripped, length->key
    assert "journal" not in out  # empty fields skipped


def test_extract_from_first_pages_llm_failure_returns_empty(monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("no model")

    import fichero_server.llm as llm_mod

    monkeypatch.setattr(llm_mod, "chat_structured_with_fallback", boom, raising=False)
    assert asyncio.run(extract_from_first_pages("text", llm_config=object())) == {}


def test_extract_full_no_llm_merges_existing_over_pdf(monkeypatch):
    doc = Document(name="paper.pdf", source_metadata={"title": "Curated"}, path="/x/paper.pdf")

    monkeypatch.setattr(
        ex, "extract_from_pdf_metadata",
        lambda _p: {"title": "PDF Title", "date": "1999"},
    )

    out = asyncio.run(extract_full(doc, llm_config=None))
    assert out["title"] == "Curated"  # existing wins over PDF
    assert out["date"] == "1999"  # PDF fills the gap


def test_extract_full_merge_order_existing_pdf_llm(monkeypatch):
    doc = Document(name="paper.pdf", source_metadata={"title": "Curated"}, path="/x/paper.pdf")

    monkeypatch.setattr(
        ex, "extract_from_pdf_metadata",
        lambda _p: {"title": "PDF Title", "publisher": "PDF Pub"},
    )
    monkeypatch.setattr(ex, "_gather_cover_pages_text", lambda _d: "cover text")

    async def fake_first_pages(_text, _cfg):
        return {"title": "LLM Title", "publisher": "LLM Pub", "date": "2020"}

    monkeypatch.setattr(ex, "extract_from_first_pages", fake_first_pages)

    out = asyncio.run(extract_full(doc, llm_config=object()))
    assert out["title"] == "Curated"  # existing wins
    assert out["publisher"] == "PDF Pub"  # PDF wins over LLM
    assert out["date"] == "2020"  # LLM fills the last gap


def test_extract_full_no_path_no_llm_returns_existing(monkeypatch):
    doc = Document(name="note", source_metadata={"title": "Only"}, path=None)
    out = asyncio.run(extract_full(doc, llm_config=None))
    assert out == {"title": "Only"}
