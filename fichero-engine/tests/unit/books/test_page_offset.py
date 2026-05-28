from fichero.books.page_offset import PageOffset, resolve_printed_page
from fichero.models import DocType, Document


def test_page_offset_from_anchor_maps_printed_to_sequence():
    resolver = PageOffset.from_anchor(printed_page=1, sequence=13)

    assert resolver.printed_to_sequence(42) == 54


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

