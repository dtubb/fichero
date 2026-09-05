"""A PDF's text layer is read once per DOCUMENT, not once per page.

`process_vision` fans a PDF out to one task per page child, and every task
carried the parent PDF's path. Two of the things each task did with that path
opened the whole document and walked EVERY page:

* `_try_pdf_text_layer` — PyMuPDF open, `get_text()` on each page;
* `_pdf_text_layer_geometry` — the same walk, collecting word boxes.

Once per page, over an N-page document, that is N opens and N x N page
extractions. Seven pages meant forty-nine extractions where seven belong, on
the one path a loose image never touches — an image has no text layer to try.

The striking part is that this was already understood. `_pdf_text_layer_geometry`
HAS a cached wrapper, whose docstring says exactly why it exists: "a per-page
fan-out calls into the same parent PDF once per page; without this the word
extraction would be re-run O(N) times per document." The cure was written, and
then applied to one of the two twins — and one call site went on calling the
uncached geometry function directly while the cached wrapper sat beside it,
used elsewhere in the same file.

Counted, never timed: these assert how many times the document is opened. A
timing test would pass on a fast machine with the bug still in place.

No engine, no model, no real PDF.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from fichero_server.workflows.tools import vision_base

PAGE_TEXT = "Mis padecimientos en la causa que se me ha seguido. " * 2


class _FakePage:
    def get_text(self, _mode="text"):
        return PAGE_TEXT


class _FakeDoc:
    def __init__(self, pages: int) -> None:
        self._pages = [_FakePage() for _ in range(pages)]

    def __iter__(self):
        return iter(self._pages)

    def __len__(self):
        return len(self._pages)

    def __getitem__(self, index):
        return self._pages[index]

    def close(self):
        pass


@pytest.fixture
def counting_fitz(monkeypatch):
    """A fake PyMuPDF that counts how many times a document is opened."""
    opens: list[str] = []

    def fake_open(path):
        opens.append(str(path))
        return _FakeDoc(7)

    module = MagicMock()
    module.open = fake_open
    monkeypatch.setitem(sys.modules, "fitz", module)

    # lru_cache is process-global: a previous test's entries would make this
    # one pass for the wrong reason.
    vision_base._try_pdf_text_layer_cached.cache_clear()
    yield opens
    vision_base._try_pdf_text_layer_cached.cache_clear()


def test_seven_pages_open_the_document_once(counting_fitz) -> None:
    """The whole point: one open for a 7-page fan-out."""
    for _page in range(7):
        result = vision_base._try_pdf_text_layer_cached("/soto.pdf")
        assert result is not None

    assert len(counting_fitz) == 1, (
        f"the document was opened {len(counting_fitz)} times for 7 pages — "
        "each page is re-extracting the entire PDF"
    )


def test_without_the_cache_it_really_is_once_per_page(counting_fitz) -> None:
    """Proof the CACHE is what prevents it, not something else.

    If the uncached function did not open per call, the test above would be
    passing for a reason that has nothing to do with the fix.
    """
    for _page in range(7):
        vision_base._try_pdf_text_layer("/soto.pdf")

    assert len(counting_fitz) == 7


def test_the_cache_returns_a_tuple_not_a_shared_list(counting_fitz) -> None:
    """A cache must not hand two callers the same mutable object.

    This is why the cached geometry twin returns a tuple, and why this one
    does: a caller that mutated the list would corrupt every later caller's
    view of the document.
    """
    first = vision_base._try_pdf_text_layer_cached("/soto.pdf")
    second = vision_base._try_pdf_text_layer_cached("/soto.pdf")

    assert isinstance(first, tuple)
    assert first is second  # the cache is doing its job
    assert len(first) == 7


def test_different_documents_are_cached_separately(counting_fitz) -> None:
    """Caching per document must not collapse two documents into one."""
    a = vision_base._try_pdf_text_layer_cached("/soto.pdf")
    b = vision_base._try_pdf_text_layer_cached("/other.pdf")

    assert len(counting_fitz) == 2
    assert a is not b


def test_no_call_site_reads_the_text_layer_uncached() -> None:
    """The regression that produced this bug was a call site, not a function.

    The cached geometry wrapper already existed and was used elsewhere while
    `_process_file` called the uncached one directly. Guarding the functions
    alone would not have caught that, so this pins the CALL SITES: every use
    outside the cache wrappers themselves must go through a cache.
    """
    from pathlib import Path

    source = Path(vision_base.__file__).read_text(encoding="utf-8")

    offenders = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(("def ", "#", '"""', "*")):
            continue
        for uncached in ("_try_pdf_text_layer(", "_pdf_text_layer_geometry("):
            if uncached in stripped and "_cached" not in stripped:
                # The cache wrappers are the one legitimate caller of each.
                if stripped.startswith("result = "):
                    continue
                offenders.append(f"{lineno}: {stripped}")

    assert not offenders, (
        "these call sites read a PDF's text layer WITHOUT the cache, so they "
        "re-open and re-walk the whole document once per page:\n  "
        + "\n  ".join(offenders)
    )
