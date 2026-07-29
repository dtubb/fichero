from fichero_server.books.page_offset import PageOffset, page_offset_from_inputs, resolve_printed_page
from fichero_server.models import DocType, Document


def test_page_offset_from_anchor_maps_printed_to_sequence():
    resolver = PageOffset.from_anchor(printed_page=1, sequence=13)

    assert resolver.printed_to_sequence(42) == 54


def test_page_offset_from_inputs_uses_explicit_offset():
    resolver = page_offset_from_inputs(page_offset=12)

    assert resolver.printed_to_sequence(1) == 13


def test_page_offset_from_inputs_prefers_complete_anchor_pair():
    resolver = page_offset_from_inputs(
        page_offset=99,
        anchor_printed_page=10,
        anchor_sequence=15,
    )

    assert resolver.printed_to_sequence(20) == 25


def test_page_offset_from_inputs_defaults_to_zero_for_missing_inputs():
    resolver = page_offset_from_inputs(anchor_printed_page=10)

    assert resolver.printed_to_sequence(7) == 7


def test_resolve_printed_page_uses_sequence_offset(db):
    parent = Document(name="book.pdf", doc_type=DocType.file)
    db.save(parent)
    page = Document(
        name="page 13",
        parent_id=parent.id,
        doc_type=DocType.page,
        sequence=13,
        page_content="chapter starts",
    )
    db.save(page)

    resolved = resolve_printed_page(
        db,
        parent_id=parent.id,
        printed_page=1,
        page_offset=12,
    )

    assert resolved is not None
    assert resolved.id == page.id
