"""Printed-page to page-document resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass

from fichero_server.db import Database
from fichero_server.models import DocType, Document


@dataclass(frozen=True)
class PageOffset:
    """Resolve printed page numbers to PDF page `sequence` values."""

    offset: int = 0

    @classmethod
    def from_anchor(cls, printed_page: int, sequence: int) -> "PageOffset":
        """Build an offset from a known printed-page to sequence anchor."""

        return cls(offset=sequence - printed_page)

    def printed_to_sequence(self, printed_page: int) -> int:
        """Return the PDF sequence corresponding to a printed page."""

        return printed_page + self.offset


def page_offset_from_inputs(
    *,
    page_offset: int | None = None,
    anchor_printed_page: int | None = None,
    anchor_sequence: int | None = None,
) -> PageOffset:
    """Create a resolver from either an explicit offset or an anchor pair."""

    if anchor_printed_page is not None and anchor_sequence is not None:
        return PageOffset.from_anchor(anchor_printed_page, anchor_sequence)
    return PageOffset(offset=page_offset or 0)


def page_children(db: Database, parent_id: str) -> list[Document]:
    """Return page children for a parent document sorted by sequence."""

    children = db.query(Document, parent_id=parent_id)
    pages = [doc for doc in children if doc.doc_type == DocType.page]
    return sorted(pages, key=lambda doc: doc.sequence or 0)


def resolve_printed_page(
    db: Database,
    *,
    parent_id: str,
    printed_page: int,
    page_offset: int | None = None,
    anchor_printed_page: int | None = None,
    anchor_sequence: int | None = None,
) -> Document | None:
    """Resolve a printed page number to a page child document.

    First tries an exact `sequence` match. If imported pages lack sequence
    values, falls back to the 1-based sorted page order.
    """

    resolver = page_offset_from_inputs(
        page_offset=page_offset,
        anchor_printed_page=anchor_printed_page,
        anchor_sequence=anchor_sequence,
    )
    sequence = resolver.printed_to_sequence(printed_page)
    pages = page_children(db, parent_id)
    for page in pages:
        if page.sequence == sequence:
            return page

    if 1 <= sequence <= len(pages):
        return pages[sequence - 1]
    return None

