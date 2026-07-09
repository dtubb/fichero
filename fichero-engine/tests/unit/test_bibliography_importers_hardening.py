"""Edge-case / hardening coverage for the bibliography import/parse/export logic.

Exercises the pure parser functions directly (no HTTP, no DB where avoidable):
read_bibtex / read_ris / read_csl_json / write_bibtex / detect_format from
``fichero.bibliography.importers``, plus the route-module helpers
``_parse_bibliography`` / ``_attach_record_impl`` / ``_patch_metadata_impl``.

These pin the "silent empty" and undo-payload contracts so a future refactor
can't quietly turn a skip into a crash or a half-parse.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from fichero.api.routes.bibliography import (
    _attach_record_impl,
    _parse_bibliography,
    _patch_metadata_impl,
)
from fichero.bibliography.importers import (
    detect_format,
    read_bibtex,
    read_csl_json,
    read_ris,
    write_bibtex,
)
from fichero.models import Document

# ---------------------------------------------------------------------------
# 1. detect_format + _parse_bibliography dispatch
# ---------------------------------------------------------------------------

BIBTEX_SAMPLE = "@book{a,\n  title = {A Work},\n  year = {1999}\n}\n"
RIS_SAMPLE = "TY  - BOOK\nTI  - A Work\nPY  - 1999\nER  - \n"
CSL_SAMPLE = '[{"title": "A Work", "issued": {"date-parts": [[1999]]}}]'


def test_detect_format_recognises_each_format():
    assert detect_format(BIBTEX_SAMPLE) == "bibtex"
    assert detect_format(RIS_SAMPLE) == "ris"
    assert detect_format(CSL_SAMPLE) == "csl_json"
    # A single CSL object (not a list) still starts with '{'.
    assert detect_format('{"title": "x"}') == "csl_json"


def test_detect_format_empty_and_unknown():
    assert detect_format("") == "unknown"
    assert detect_format("   \n  ") == "unknown"
    assert detect_format("just some prose, no markers") == "unknown"


def test_detect_format_ignores_leading_whitespace():
    assert detect_format("\n\n   @article{k, title={T}\n}") == "bibtex"


def test_parse_bibliography_autodetects(db=None):
    assert _parse_bibliography(BIBTEX_SAMPLE, None)[0]["title"] == "A Work"
    assert _parse_bibliography(RIS_SAMPLE, None)[0]["title"] == "A Work"
    assert _parse_bibliography(CSL_SAMPLE, None)[0]["title"] == "A Work"


def test_parse_bibliography_unrecognised_raises_400():
    with pytest.raises(HTTPException) as exc:
        _parse_bibliography("this is not a bibliography", None)
    assert exc.value.status_code == 400


def test_parse_bibliography_explicit_bad_format_raises_400():
    with pytest.raises(HTTPException) as exc:
        _parse_bibliography(BIBTEX_SAMPLE, "not-a-format")
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# 2. read_bibtex edge cases
# ---------------------------------------------------------------------------


def test_read_bibtex_multiple_entries():
    text = (
        "@book{a,\n  title = {First},\n  year = {1999}\n}\n"
        "@article{b,\n  title = {Second},\n  year = {2001}\n}\n"
    )
    entries = read_bibtex(text)
    assert [e["title"] for e in entries] == ["First", "Second"]
    assert entries[0]["date"] == "1999"


def test_read_bibtex_missing_fields_only_title():
    entries = read_bibtex("@misc{k,\n  title = {Just A Title}\n}\n")
    assert len(entries) == 1
    assert entries[0]["title"] == "Just A Title"
    assert "authors" not in entries[0]
    assert "date" not in entries[0]


def test_read_bibtex_unicode_and_multi_author():
    text = "@book{k,\n  title = {Æsthetics},\n  author = {Müller, Hans and Doe, Jane},\n  year = {2000}\n}\n"
    entries = read_bibtex(text)
    assert entries[0]["title"] == "Æsthetics"
    assert entries[0]["authors"] == ["Müller, Hans", "Doe, Jane"]


def test_read_bibtex_duplicate_cite_keys_kept_separately():
    # The parser ignores the cite key, so duplicates must not collapse.
    text = (
        "@book{dup,\n  title = {One},\n  year = {1999}\n}\n"
        "@book{dup,\n  title = {Two},\n  year = {2000}\n}\n"
    )
    entries = read_bibtex(text)
    assert [e["title"] for e in entries] == ["One", "Two"]


def test_read_bibtex_truncated_entry_skipped():
    # No closing brace on its own line -> not a valid block -> skipped.
    assert read_bibtex("@book{a,\n  title = {X}") == []


def test_read_bibtex_empty_string():
    assert read_bibtex("") == []


def test_read_bibtex_isbn_split_by_length():
    text = "@book{k,\n  title = {T},\n  isbn = {978-3-16-148410-0}\n}\n"
    entry = read_bibtex(text)[0]
    assert entry["isbn_13"] == "9783161484100"
    assert "isbn" not in entry


# ---------------------------------------------------------------------------
# 3. read_ris + read_csl_json
# ---------------------------------------------------------------------------


def test_read_ris_minimal_valid():
    text = "TY  - BOOK\nTI  - RIS Title\nAU  - Smith, Bob\nPY  - 2010\nSP  - 5\nEP  - 9\nER  - \n"
    entry = read_ris(text)[0]
    assert entry["title"] == "RIS Title"
    assert entry["authors"] == ["Smith, Bob"]
    assert entry["date"] == "2010"
    assert entry["pages"] == "5-9"


def test_read_ris_missing_er_terminator_yields_nothing():
    # An entry is only emitted on the ER terminator.
    assert read_ris("TY  - BOOK\nTI  - No Terminator\n") == []


def test_read_ris_empty_string():
    assert read_ris("") == []


def test_read_ris_multiple_authors_and_year_from_date():
    text = (
        "TY  - JOUR\nTI  - Multi\nAU  - Doe, Jane\nAU  - Roe, Ann\n"
        "PY  - 2015/06/01\nER  - \n"
    )
    entry = read_ris(text)[0]
    assert entry["authors"] == ["Doe, Jane", "Roe, Ann"]
    assert entry["date"] == "2015"  # extracted 4-digit year


def test_read_csl_json_minimal_valid():
    text = json.dumps(
        [{"title": "CSL", "author": [{"family": "Roe", "given": "Ann"}],
          "issued": {"date-parts": [[2020]]}}]
    )
    entry = read_csl_json(text)[0]
    assert entry["title"] == "CSL"
    assert entry["authors"] == ["Roe, Ann"]
    assert entry["date"] == "2020"


def test_read_csl_json_single_object_not_list():
    entry = read_csl_json('{"title": "Solo"}')[0]
    assert entry["title"] == "Solo"


def test_read_csl_json_missing_fields():
    # Object with no recognised keys -> an entry with no useful fields (but
    # still bibtex-rendered), never a crash.
    entries = read_csl_json('[{"unknownkey": 1}]')
    assert len(entries) == 1
    assert "title" not in entries[0]


def test_read_csl_json_malformed_returns_empty():
    assert read_csl_json("{not valid json") == []


def test_read_csl_json_empty_string():
    assert read_csl_json("") == []


# ---------------------------------------------------------------------------
# 4. write_bibtex round-trip
# ---------------------------------------------------------------------------


def test_write_bibtex_roundtrip_preserves_core_fields():
    entries = [{"title": "Round Trip", "authors": ["Doe, Jane"], "date": "1999"}]
    rendered = write_bibtex(entries)
    back = read_bibtex(rendered)
    assert len(back) == 1
    assert back[0]["title"] == "Round Trip"
    assert back[0]["authors"] == ["Doe, Jane"]
    assert back[0]["date"] == "1999"


def test_write_bibtex_entry_without_explicit_citekey():
    # No cite key supplied -> renderer must synthesise one, output still parses.
    rendered = write_bibtex([{"title": "No Key Here"}])
    assert rendered.startswith("@")
    assert read_bibtex(rendered)[0]["title"] == "No Key Here"


def test_write_bibtex_empty_list_is_empty_string():
    assert write_bibtex([]) == ""


def test_write_bibtex_skips_malformed_entry():
    # A wildly wrong-typed entry is skipped, not fatal (logged + dropped).
    rendered = write_bibtex([{"authors": "not-a-list-should-be-list"}])
    # Either it renders defensively or it is skipped; must never raise.
    assert isinstance(rendered, str)


def test_bibtex_roundtrip_preserves_unknown_fields_and_cite_key():
    text = """@book{demo-key,
  author = {Doe, Jane},
  title = {Round Trip},
  year = {1999},
  editor = {Roe, Ann},
  edition = {2},
  url = {https://example.org}
}"""
    entry = read_bibtex(text)[0]

    assert entry["metadata"]["bibtex_cite_key"] == "demo-key"
    assert entry["metadata"]["bibtex_fields"] == {
        "editor": "Roe, Ann",
        "edition": "2",
    }

    rendered = write_bibtex([dict(entry, bibtex="")])
    assert "@book{demo-key," in rendered
    assert "editor = {Roe, Ann}" in rendered
    assert "edition = {2}" in rendered
    assert "url = {https://example.org}" in rendered


# ---------------------------------------------------------------------------
# 5. _attach_record_impl (undo payload contract)
# ---------------------------------------------------------------------------


def test_attach_record_unknown_document_raises_404(db):
    with pytest.raises(HTTPException) as exc:
        _attach_record_impl(db, "no-such-id", BIBTEX_SAMPLE, "bibtex")
    assert exc.value.status_code == 404


def test_attach_record_unparsable_text_raises_400(db):
    doc = Document(name="paper.pdf")
    db.save(doc)
    with pytest.raises(HTTPException) as exc:
        _attach_record_impl(db, doc.id, "not a bibliography at all", None)
    assert exc.value.status_code == 400


def test_attach_record_success_returns_previous_metadata_as_undo(db):
    doc = Document(name="paper.pdf", source_metadata={"title": "Old"})
    db.save(doc)

    result_doc, before = _attach_record_impl(
        db, doc.id,
        "@book{k,\n  title = {New Title},\n  year = {2001}\n}\n",
        "bibtex",
    )
    assert result_doc.source_metadata["title"] == "New Title"
    # `before` is the undo payload — the metadata as it was pre-attach.
    assert before == {"title": "Old"}
    # Persisted.
    assert db.get(Document, doc.id).source_metadata["title"] == "New Title"


# ---------------------------------------------------------------------------
# 6. _patch_metadata_impl (undo payload contract)
# ---------------------------------------------------------------------------


def test_patch_metadata_unknown_document_raises_404(db):
    with pytest.raises(HTTPException) as exc:
        _patch_metadata_impl(db, "no-such-id", {"title": "X"})
    assert exc.value.status_code == 404


def test_patch_metadata_replaces_and_returns_previous(db):
    doc = Document(name="paper.pdf", source_metadata={"title": "Before", "keep": 1})
    db.save(doc)

    result_doc, before = _patch_metadata_impl(db, doc.id, {"title": "After"})
    # Replace semantics — old keys gone.
    assert result_doc.source_metadata == {"title": "After"}
    # Undo payload is the full prior dict.
    assert before == {"title": "Before", "keep": 1}
    assert db.get(Document, doc.id).source_metadata == {"title": "After"}
