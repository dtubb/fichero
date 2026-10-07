"""Groups keep their place, answer their size and carry their pages' date (#5569 items 1-3, #5570).

Found organising Istmina '1948 Sentencias' (203 loose pages into 8 judgments):
every new group got sort_order 0 and listed by name, create-group answered
child_count 0, and a group of dated pages had no date. Driven through the real
routes.
"""

from fichero_server.histdate import gregorian_to_jdn
from fichero_server.models import DocType, Document


def _box(db, names: list[str]) -> tuple[Document, list[Document]]:
    """A folder nobody has reordered: every page at sort_order 0, listed by name."""
    folder = Document(name="1948 Sentencias", doc_type=DocType.folder)
    db.save(folder)
    pages = [Document(name=name, parent_id=folder.id) for name in names]
    for page in pages:
        db.save(page)
    return folder, pages


def _listed_names(client, folder_id: str) -> list[str]:
    response = client.get(f"/api/documents/{folder_id}/children")
    assert response.status_code == 200
    return [item["name"] for item in response.json()["items"]]


def _dated(page: Document, year: int, month: int, day: int, display: str) -> Document:
    jdn = gregorian_to_jdn(year, month, day)
    page.date_original = display
    page.date_jdn = jdn
    page.date_jdn_end = jdn
    page.date_meta = {"status": "dated", "source": "extracted", "precision": "day", "display": display}
    return page


def test_a_new_group_takes_its_first_pages_place_in_an_unordered_folder(client, db):
    folder, pages = _box(db, ["p01", "p02", "p03", "p04", "p05"])
    # "Zeta" sorts after every page by name; it must still list where p02 was.
    grouped = client.post(
        "/api/documents/groups", json={"name": "Zeta judgment", "child_ids": [pages[1].id, pages[2].id]}
    )
    assert grouped.status_code == 200
    assert _listed_names(client, folder.id) == ["p01", "Zeta judgment", "p04", "p05"]


def test_a_group_lists_its_pages_in_the_order_they_were_given(client, db):
    _, pages = _box(db, ["a", "b", "c"])
    grouped = client.post(
        "/api/documents/groups", json={"name": "Letter", "child_ids": [pages[2].id, pages[0].id, pages[1].id]}
    )
    assert _listed_names(client, grouped.json()["id"]) == ["c", "a", "b"]


def test_create_group_answers_how_many_pages_it_holds(client, db):
    _, pages = _box(db, ["a", "b", "c"])
    grouped = client.post(
        "/api/documents/groups", json={"name": "Letter", "child_ids": [page.id for page in pages]}
    )
    assert grouped.json()["child_count"] == 3
    assert client.get(f"/api/documents/{grouped.json()['id']}").json()["child_count"] == 3


def test_ungroup_puts_every_page_back_in_its_place(client, db):
    folder, pages = _box(db, ["p01", "p02", "p03", "p04", "p05"])
    grouped = client.post(
        "/api/documents/groups", json={"name": "Zeta", "child_ids": [pages[3].id, pages[1].id]}
    )
    assert _listed_names(client, folder.id) == ["p01", "p03", "Zeta", "p05"]
    assert client.post(f"/api/documents/groups/{grouped.json()['id']}/ungroup").status_code == 200
    assert _listed_names(client, folder.id) == ["p01", "p02", "p03", "p04", "p05"]


def test_a_folder_already_in_order_is_left_as_it_was(client, db):
    folder = Document(name="Ordered", doc_type=DocType.folder)
    db.save(folder)
    pages = [Document(name=f"p{i}", parent_id=folder.id, sort_order=10 * i) for i in range(3)]
    for page in pages:
        db.save(page)
    grouped = client.post(
        "/api/documents/groups", json={"name": "G", "child_ids": [pages[1].id, pages[2].id]}
    )
    assert grouped.json()["sort_order"] == 10
    assert db.get(Document, pages[0].id).sort_order == 0


def test_a_group_of_dated_pages_carries_their_range(client, db):
    folder, pages = _box(db, ["p1", "p2", "p3"])
    _dated(pages[0], 1948, 3, 2, "2 March 1948")
    _dated(pages[2], 1948, 3, 15, "15 March 1948")
    for page in pages:
        db.save(page)
    grouped = client.post(
        "/api/documents/groups", json={"name": "Sentencia", "child_ids": [page.id for page in pages]}
    ).json()
    assert grouped["date_jdn"] == gregorian_to_jdn(1948, 3, 2)
    assert grouped["date_jdn_end"] == gregorian_to_jdn(1948, 3, 15)
    assert grouped["date_meta"]["display"] == "2 March 1948 – 15 March 1948"
    assert grouped["date_meta"]["source"] == "pages"
    listed = client.get(f"/api/documents/{folder.id}/children").json()["items"]
    assert listed[0]["date_meta"]["display"] == "2 March 1948 – 15 March 1948"


def test_a_group_made_before_its_pages_were_dated_reads_their_date(client, db):
    """The Istmina groups were made from undated pages; a later page date shows on the group."""
    folder, pages = _box(db, ["p1", "p2"])
    group_id = client.post(
        "/api/documents/groups", json={"name": "Sentencia", "child_ids": [page.id for page in pages]}
    ).json()["id"]
    assert client.get(f"/api/documents/{group_id}").json()["date_jdn"] is None
    db.save(_dated(db.get(Document, pages[1].id), 1948, 7, 9, "9 July 1948"))
    assert client.get(f"/api/documents/{group_id}").json()["date_meta"]["display"] == "9 July 1948"
    listed = client.get(f"/api/documents/{folder.id}/children").json()["items"]
    assert listed[0]["date_jdn"] == gregorian_to_jdn(1948, 7, 9)


def test_a_group_with_its_own_date_keeps_it(client, db):
    folder, pages = _box(db, ["p1", "p2"])
    _dated(pages[0], 1948, 3, 2, "2 March 1948")
    db.save(pages[0])
    group_id = client.post(
        "/api/documents/groups", json={"name": "Sentencia", "child_ids": [page.id for page in pages]}
    ).json()["id"]
    group = db.get(Document, group_id)
    _dated(group, 1948, 4, 1, "1 April 1948")
    group.date_meta["source"] = "user"
    db.save(group)
    assert client.get(f"/api/documents/{group_id}").json()["date_meta"]["display"] == "1 April 1948"
    assert client.get(f"/api/documents/{folder.id}/children").json()["items"][0]["date_meta"]["display"] == "1 April 1948"


def _image(test_package, db, name: str, colour: str, folder: Document) -> Document:
    from PIL import Image

    from fichero_server.models import FileType

    path = test_package / "files" / "gr" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (60, 90), colour).save(path, format="PNG")
    page = Document(
        name=name, path=str(path.relative_to(test_package)), file_type=FileType.image, parent_id=folder.id
    )
    db.save(page)
    return page


def test_a_groups_picture_is_its_first_page(client, db, test_package):
    """A group has no file; it drew 'Preview unavailable' everywhere (#5570)."""
    folder = Document(name="Box", doc_type=DocType.folder)
    db.save(folder)
    second = _image(test_package, db, "b.png", "blue", folder)
    first = _image(test_package, db, "a.png", "red", folder)
    group_id = client.post(
        "/api/documents/groups", json={"name": "Letter", "child_ids": [first.id, second.id]}
    ).json()["id"]
    for route in ("thumbnail", "display"):
        group_picture = client.get(f"/api/storage/{route}/{group_id}")
        assert group_picture.status_code == 200, route
        assert group_picture.content == client.get(f"/api/storage/{route}/{first.id}").content
        assert group_picture.content != client.get(f"/api/storage/{route}/{second.id}").content


def test_the_reader_reads_a_groups_pages_as_one_document(client, db):
    folder, pages = _box(db, ["leaf 2", "leaf 1"])
    pages[0].page_content = "SECOND LEAF TEXT"
    pages[1].page_content = "FIRST LEAF TEXT"
    for page in pages:
        db.save(page)
    group_id = client.post(
        "/api/documents/groups", json={"name": "Sentencia", "child_ids": [pages[1].id, pages[0].id]}
    ).json()["id"]
    html = client.get(f"/view/document/{group_id}").text
    assert "FIRST LEAF TEXT" in html and "SECOND LEAF TEXT" in html
    assert html.index("FIRST LEAF TEXT") < html.index("SECOND LEAF TEXT")
