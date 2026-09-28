"""A reading typed against one that no longer counts is refused and nothing is lost
(`source.textedit.stale-keeps-your-words`, #5001; the token decided 2026-09-28 by the lead as a default).

On the imported Syriac page's first line, through `POST /api/actions/invoke` as the Reader's app half
sends it. What breaks without these: a person's words written over a correction they never saw (a
silent second candidate the page then shows as theirs), or a refusal that loses the typed words by not
saying what counts now, so the page cannot offer keep-mine / take-theirs / compare.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import ContentRepresentation
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import


def _invoke(client, name, params):
    return client.post("/api/actions/invoke", json={"name": name, "params": params})


def _first_line(db, client):
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    line = min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])
    [reading] = client.get(f"/api/segments/{line['id']}/readings").json()["items"]
    return doc_id, line, reading


def _counting(client, line):
    return client.get(f"/api/segments/{line['id']}/readings").json()["counting"]["transcription"]


def test_a_write_against_a_reading_that_no_longer_counts_writes_nothing_and_names_what_counts(db, client):
    doc_id, line, file_reading = _first_line(db, client)
    # Somebody else corrects the line while I am typing against the file's reading.
    theirs = _invoke(client, "representation.create", {
        "document_id": doc_id, "segment_id": line["id"], "kind": "transcription",
        "content": file_reading["content"] + " (theirs)", "corrects_representation_id": file_reading["id"]})
    assert theirs.status_code == 200, theirs.text
    theirs_id = theirs.json()["result"]["id"]
    assert _counting(client, line)["representation_id"] == theirs_id
    before = len(db.query(ContentRepresentation, segment_id=line["id"]))

    mine = _invoke(client, "representation.create", {
        "document_id": doc_id, "segment_id": line["id"], "kind": "transcription",
        "content": file_reading["content"] + " (mine)", "corrects_representation_id": file_reading["id"],
        "expected_counting_id": file_reading["id"]})
    assert mine.status_code == 409, mine.text
    detail = mine.json()["detail"]
    assert detail["reason"] == "stale"
    assert detail["counting_representation_id"] == theirs_id
    assert detail["counting_text"] == file_reading["content"] + " (theirs)"
    assert len(db.query(ContentRepresentation, segment_id=line["id"])) == before, "nothing was written"
    assert _counting(client, line)["representation_id"] == theirs_id


def test_keep_mine_is_the_same_words_sent_again_against_what_counts_now_and_it_lands(db, client):
    doc_id, line, file_reading = _first_line(db, client)
    theirs_id = _invoke(client, "representation.create", {
        "document_id": doc_id, "segment_id": line["id"], "kind": "transcription",
        "content": file_reading["content"] + " (theirs)", "corrects_representation_id": file_reading["id"]}
    ).json()["result"]["id"]
    kept = _invoke(client, "representation.create", {
        "document_id": doc_id, "segment_id": line["id"], "kind": "transcription",
        "content": file_reading["content"] + " (mine)", "corrects_representation_id": theirs_id,
        "expected_counting_id": theirs_id})
    assert kept.status_code == 200, kept.text
    counting = _counting(client, line)
    assert counting["representation_id"] == kept.json()["result"]["id"]
    assert counting["basis"] == "correction", "mine now counts, as a correction of theirs"


def test_a_write_that_names_what_counts_lands_and_no_token_is_todays_behaviour(db, client):
    doc_id, line, file_reading = _first_line(db, client)
    fresh = _invoke(client, "representation.create", {
        "document_id": doc_id, "segment_id": line["id"], "kind": "transcription",
        "content": file_reading["content"] + " (fresh)", "corrects_representation_id": file_reading["id"],
        "expected_counting_id": file_reading["id"]})
    assert fresh.status_code == 200, fresh.text
    # No token: a second correction of the (now superseded) file reading still lands, as before.
    untokened = _invoke(client, "representation.create", {
        "document_id": doc_id, "segment_id": line["id"], "kind": "transcription",
        "content": file_reading["content"] + " (untokened)", "corrects_representation_id": file_reading["id"]})
    assert untokened.status_code == 200, untokened.text
    # A token without the segment it names is refused as a mistake, not ignored.
    orphan = _invoke(client, "representation.create", {
        "document_id": doc_id, "kind": "transcription", "content": "x", "expected_counting_id": file_reading["id"]})
    assert orphan.status_code in (400, 422), orphan.text
