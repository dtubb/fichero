"""`GET /api/segments` — a bounded page of segments across a scope (#4941).

`source.editor.library-lists-segments` says project-wide questions about segments
should be ordinary Library searches. Every segments read before this one was scoped
to one document or one segment, so a Library listing segments would have asked once
per page of the book — the N+1 the one-store seam exists to avoid, which is why the
paging belongs in the engine rather than in a view's loop.

What these pin is the scope resolution, the bound, and the two ways an empty answer
can happen — because "no rows" and "no documents" are different facts a caller has
to be able to tell apart.
"""

from __future__ import annotations

import pytest

from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import Segment, SegmentPass


def _folder(db, name: str = "Marshall Diaries") -> Document:
    folder = Document(name=name, doc_type=DocType.folder, status=Status.completed)
    db.save(folder)
    return folder


def _page(db, parent: Document, name: str) -> Document:
    page = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        status=Status.completed, parent_id=parent.id,
    )
    db.save(page)
    return page


def _segments(db, doc: Document, count: int, *, kind: str = "line", furniture: bool = False):
    pass_row = SegmentPass(
        document_id=doc.id, name="kraken", provenance_kind=ProvenanceKind.workflow
    )
    db.save(pass_row)
    made = []
    for index in range(count):
        row = Segment(
            document_id=doc.id, pass_id=pass_row.id, kind=kind,
            doc_kind=f"{doc.id}:{kind}",
            anchor=SourceAnchor(document_id=doc.id, rect=[0.1, 0.1 * index, 0.5, 0.05]),
            bbox_x=0.1, bbox_y=0.1 * index, bbox_w=0.5, bbox_h=0.05, tile="",
            provenance_kind=ProvenanceKind.workflow,
            is_furniture=furniture,
            metadata={"box_index": index},
        )
        db.save(row)
        made.append(row)
    return pass_row, made


class TestTheScope:
    def test_a_folder_resolves_to_its_descendants(self, client, db):
        folder = _folder(db)
        first = _page(db, folder, "0001.jpg")
        second = _page(db, folder, "0002.jpg")
        _segments(db, first, 3)
        _segments(db, second, 2)
        # A page in ANOTHER folder must not appear.
        elsewhere = _folder(db, "Other")
        _segments(db, _page(db, elsewhere, "0003.jpg"), 4)

        body = client.get("/api/segments", params={"parent_id": folder.id}).json()

        assert body["total"] == 5, "three from the first page and two from the second"
        assert body["count"] == 5
        assert set(body["document_ids"]) == {folder.id, first.id, second.id}

    def test_explicit_document_ids_are_the_scope(self, client, db):
        folder = _folder(db)
        first = _page(db, folder, "0001.jpg")
        second = _page(db, folder, "0002.jpg")
        _segments(db, first, 3)
        _segments(db, second, 2)

        body = client.get(
            "/api/segments", params={"document_ids": first.id}
        ).json()

        assert body["total"] == 3, "only the document asked for"
        assert body["document_ids"] == [first.id]

    def test_giving_both_or_neither_is_refused_by_name(self, client, db):
        """Two scopes cannot be intersected here and no scope would mean the whole
        library — the refusal says which, rather than picking one."""
        folder = _folder(db)

        neither = client.get("/api/segments")
        both = client.get(
            "/api/segments", params={"parent_id": folder.id, "document_ids": folder.id}
        )

        assert neither.status_code == 422, neither.text
        assert both.status_code == 422, both.text
        assert "exactly one" in neither.json()["detail"]

    def test_an_empty_scope_and_an_empty_page_are_tellable_apart(self, client, db):
        """Both answer no rows, and they are different facts: a folder with no
        documents versus documents with no segments. `document_ids` is what says
        which, and a caller that cannot tell will report the wrong thing to a
        person."""
        empty_folder = _folder(db, "Empty")
        with_pages = _folder(db, "Unconverted")
        _page(db, with_pages, "0001.jpg")  # a page, but no segment rows

        no_documents = client.get(
            "/api/segments", params={"parent_id": empty_folder.id}
        ).json()
        no_segments = client.get(
            "/api/segments", params={"parent_id": with_pages.id}
        ).json()

        assert no_documents["total"] == 0 and no_segments["total"] == 0
        assert no_documents["document_ids"] == [empty_folder.id]
        assert len(no_segments["document_ids"]) == 2, "the folder and its page"


class TestTheBoundAndTheOrder:
    def test_the_page_is_bounded_and_the_total_is_the_whole_match(self, client, db):
        folder = _folder(db)
        page = _page(db, folder, "0001.jpg")
        _segments(db, page, 7)

        body = client.get(
            "/api/segments", params={"parent_id": folder.id, "limit": 3}
        ).json()

        assert body["count"] == 3, "the page is capped"
        assert body["total"] == 7, "and the caller is told how much there is"

    def test_paging_never_repeats_or_drops_a_row(self, client, db):
        """A stable order is the whole reason this is `document_id, box_index, id` and
        not `created_at`: rows written in the same transaction share a timestamp, so a
        page break could show one row twice and never show another."""
        folder = _folder(db)
        page = _page(db, folder, "0001.jpg")
        _segments(db, page, 6)

        first = client.get(
            "/api/segments", params={"parent_id": folder.id, "limit": 3, "offset": 0}
        ).json()
        second = client.get(
            "/api/segments", params={"parent_id": folder.id, "limit": 3, "offset": 3}
        ).json()

        ids = [row["id"] for row in first["items"]] + [row["id"] for row in second["items"]]
        assert len(set(ids)) == 6, f"a row was repeated or dropped across the page break: {ids}"

    @pytest.mark.parametrize("limit", [0, 1001])
    def test_an_unbounded_request_is_refused(self, client, db, limit):
        """`source.store.bounded-reads`. A caller cannot ask for a whole project in one
        request: a library view never needs it, and an agent asking for it is asking
        for the thing that takes the engine down."""
        folder = _folder(db)

        response = client.get(
            "/api/segments", params={"parent_id": folder.id, "limit": limit}
        )

        assert response.status_code == 422, response.text


class TestTheFilters:
    def test_one_kind_only(self, client, db):
        folder = _folder(db)
        page = _page(db, folder, "0001.jpg")
        _segments(db, page, 2, kind="line")
        _segments(db, page, 3, kind="word")

        body = client.get(
            "/api/segments", params={"parent_id": folder.id, "kind": "word"}
        ).json()

        assert body["total"] == 3
        assert {row["kind"] for row in body["items"]} == {"word"}

    def test_furniture_can_be_left_out(self, client, db):
        """A running head is on the page and is not the text of the document, so a
        project-wide list of lines must be able to exclude it — the same rule the
        derived text applies."""
        folder = _folder(db)
        page = _page(db, folder, "0001.jpg")
        _segments(db, page, 2, kind="line")
        _segments(db, page, 1, kind="line", furniture=True)

        with_all = client.get(
            "/api/segments", params={"parent_id": folder.id}
        ).json()
        without = client.get(
            "/api/segments", params={"parent_id": folder.id, "include_furniture": False}
        ).json()

        assert with_all["total"] == 3
        assert without["total"] == 2

    def test_a_deleted_segment_never_comes_back(self, client, db):
        folder = _folder(db)
        page = _page(db, folder, "0001.jpg")
        _pass, rows = _segments(db, page, 3)
        from fichero_server.core.timeutil import utc_now

        rows[0].deleted_at = utc_now()
        db.save(rows[0])

        body = client.get("/api/segments", params={"parent_id": folder.id}).json()

        assert body["total"] == 2, "a list of a project's segments is a list of what is there"
