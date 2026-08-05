"""A splitter that returns pages but NO text has failed too (#4555).

The shipped app extracts kreuzberg's bundled pdfium to
``Data/tmp/kreuzberg-pdfium/`` and dlopens it, which Gatekeeper blocks. When
that happens extraction can still return the right NUMBER of page records with
EMPTY content. The fitz fallback was gated on ``not page_records``, false in
that case, so it never ran: every page was stamped ``is_blank: true``, the PDF
had no searchable text, and per-page transcription had nothing to work from.

The distinction that must be preserved is a genuine SCAN, which also has no
text layer and for which ``is_blank: true`` is the correct answer. Warning on
every scan would train everyone to ignore the warning that matters.
"""
from __future__ import annotations

from fichero_server.importers.ingest import _choose_pdf_page_records


def _pages(*texts: str) -> list[dict]:
    return [
        {"page_number": i + 1, "content": text, "is_blank": not text.strip()}
        for i, text in enumerate(texts)
    ]


def test_blank_kreuzberg_pages_fall_back_to_fitz_text():
    """RED before the fix: kreuzberg's records are non-empty, so the old
    ``not page_records`` gate kept them and every page stayed blank."""
    kreuzberg = _pages("", "", "")
    fitz = _pages("Page 1 of 3", "Page 2 of 3", "Page 3 of 3")

    records, reason = _choose_pdf_page_records(kreuzberg, fitz)

    assert records == fitz, "fitz found the text layer; its split must win"
    assert reason is not None, "a silent recovery hides why the first path failed"
    assert "NO text on any of them" in reason
    assert "3/3" in reason


def test_a_real_scan_keeps_its_honest_blank_result():
    """Both extractors finding no text is a fact about the PAGES, not a defect.

    Guards against 'fixing' this by warning on every scan.
    """
    kreuzberg = _pages("", "", "")
    fitz = _pages("", "", "")

    records, reason = _choose_pdf_page_records(kreuzberg, fitz)

    assert records == kreuzberg, (
        "kreuzberg's records may carry per-page artifacts fitz never produced"
    )
    assert reason is None, "nothing failed, so nothing may claim it did"


def test_kreuzberg_text_is_kept_and_fitz_is_not_consulted():
    kreuzberg = _pages("real text", "more text")
    records, reason = _choose_pdf_page_records(kreuzberg, _pages("junk", "junk"))

    assert records == kreuzberg
    assert reason is None


def test_no_pages_at_all_still_falls_back_and_names_the_cause():
    """The pre-existing #2430 behaviour, now carrying kreuzberg's own reason
    rather than a generic one."""
    fitz = _pages("Page 1", "Page 2")

    records, reason = _choose_pdf_page_records(
        [], fitz, "dependency missing (No module named 'kreuzberg')"
    )

    assert records == fitz
    assert reason is not None
    assert "dependency missing" in reason, (
        f"the reason must name WHY kreuzberg produced nothing: {reason!r}"
    )


def test_both_extractors_empty_reports_nothing_usable():
    records, reason = _choose_pdf_page_records([], [])

    assert records == []
    assert reason is None, (
        "the caller already logs the both-failed case loudly (#2430); this "
        "must not double-report it as a fallback"
    )


def test_partial_fitz_recovery_is_reported_with_real_counts():
    """A half-recovered PDF must say so — 'recovered' with 1 of 5 pages is a
    materially different fact from a clean recovery."""
    records, reason = _choose_pdf_page_records(
        _pages("", "", "", "", ""), _pages("", "text", "", "", "")
    )

    assert len(records) == 5
    assert reason is not None
    assert "1/5" in reason, f"expected honest counts in: {reason!r}"
