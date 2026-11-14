"""sharing.stale-note-edit-is-refused-and-offered-a-choice (#5348), the document half.

`PUT /api/documents/{id}` takes an optional `expected_updated_at`: when the node changed since the editor
read it, nothing is written and the edit is refused 409 with the current text, as notes are.
"""

from fichero_server.models import DocType, Document


def test_a_page_edit_made_against_an_old_version_is_refused_and_writes_nothing(client, db):
    doc = Document(id="shared-page", name="Page", doc_type=DocType.file, page_content="draft")
    db.save(doc)
    seen = client.get(f"/api/documents/{doc.id}").json()["updated_at"]

    assert client.put(f"/api/documents/{doc.id}", json={"page_content": "host words"}).status_code == 200
    stale = client.put(
        f"/api/documents/{doc.id}", json={"page_content": "mac words", "expected_updated_at": seen}
    )

    assert stale.status_code == 409, (stale.status_code, stale.text)
    detail = stale.json()["detail"]
    assert detail["reason"] == "stale" and detail["current_page_content"] == "host words"
    assert client.get(f"/api/documents/{doc.id}").json()["page_content"] == "host words"


def test_an_edit_against_the_current_version_lands_and_no_version_keeps_last_save_wins(client, db):
    doc = Document(id="shared-page-2", name="Page", doc_type=DocType.file, page_content="draft")
    db.save(doc)
    seen = client.get(f"/api/documents/{doc.id}").json()["updated_at"]

    ok = client.put(f"/api/documents/{doc.id}", json={"page_content": "one", "expected_updated_at": seen})
    assert ok.status_code == 200, ok.text
    assert client.put(f"/api/documents/{doc.id}", json={"page_content": "two"}).status_code == 200


def _as_the_app_sends_it(updated_at: str) -> str:
    """The app's date transcoder keeps milliseconds only: the engine's microseconds come back cut to three digits."""
    from datetime import datetime

    seen = datetime.fromisoformat(updated_at)
    return seen.isoformat(timespec="milliseconds")


def test_an_edit_against_the_current_version_as_the_app_sends_it_lands(client, db):
    """The app reads `updated_at` with microseconds and sends it back with milliseconds; that is the same version."""
    from datetime import datetime, timezone

    doc = Document(
        id="shared-page-ms", name="Page", doc_type=DocType.file, page_content="draft",
        updated_at=datetime(2026, 11, 13, 14, 2, 11, 123456, tzinfo=timezone.utc),
    )
    db.save(doc)
    seen = _as_the_app_sends_it(client.get(f"/api/documents/{doc.id}").json()["updated_at"])
    assert seen.endswith(".123+00:00"), seen

    ok = client.put(f"/api/documents/{doc.id}", json={"page_content": "mine", "expected_updated_at": seen})
    assert ok.status_code == 200, ok.text
    again = _as_the_app_sends_it(ok.json()["updated_at"])
    second = client.put(f"/api/documents/{doc.id}", json={"page_content": "mine too", "expected_updated_at": again})
    assert second.status_code == 200, second.text


def test_a_note_edit_against_the_current_version_as_the_app_sends_it_lands(client):
    note = client.post("/api/notes", json={"body": "draft"}).json()
    ok = client.patch(
        f"/api/notes/{note['id']}",
        json={"body": "mine", "expected_updated_at": _as_the_app_sends_it(note["updated_at"])},
    )
    assert ok.status_code == 200, ok.text
