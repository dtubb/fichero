"""`source.extract.corrected-in-place` (#5602), the engine half: from a mark on a tied page a person corrects
the name (re-points the mention to another entity, or fixes its words), the statement's date, or rejects the
statement; each is one audited action, undone by `POST /api/actions/audit/{id}/undo`, and a later run of the
extraction keeps the person's correction.

Through the real paths, on the page of `test_names_as_mentions.py` (PAGE XML lines, tied by the tie job, then
Extract Entities with its model stubbed at `chat_structured_with_fallback`, or Extract People): the marks read
back from `GET /api/segments/{id}/statements`, corrected through `POST /api/entities/{id}/mentions/repoint`,
`.../respan`, `PATCH /api/claims/{id}` and `PATCH /api/claims/{id}/transition`.

What breaks without these: a mention filed under the wrong person with no way to move it from the line, and a
re-run of the extraction putting back the name or the span a person took away.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.models.knowledge import KnowledgeClaim
from fichero_server.workflows.tools.extract_all import _EntitiesOnly, _EntityOnly
from fichero_server.workflows.tools.extractors import _SECTION_SCHEMAS, _SECTIONS, _run_extractor
from tests.unit.check.test_tie_text_to_lines import _lines, _run, reader  # noqa: F401  (fixture)
from tests.unit.workflows.test_names_as_mentions import _entities, _entity, _ok, page  # noqa: F401  (fixture)

LLM = LLMConfig(provider="openai", model="gpt-4o-mini")


def _marks(client, segment_id):
    return _ok(client.get(f"/api/segments/{segment_id}/statements"))


def _named(client, segment_id):
    return sorted((m["name"], m["excerpt"]) for m in _marks(client, segment_id)["mentions"])


def _undo(client, audit_id):
    _ok(client.post(f"/api/actions/audit/{audit_id}/undo"))


def _last_audit(client, action_name):
    items = _ok(client.get("/api/actions/audit"))["items"]
    return next(i["id"] for i in items if i["action_name"] == action_name and not i["undone"])


@pytest.mark.asyncio
async def test_a_name_re_pointed_from_its_line_stays_re_pointed_and_undoes(client, db, test_package, page, reader):
    """"correct the name ... from its mark on the page": the second line's "Ruiz" is Francisco, not Pedro.
    WHY: the line's mark carries the span that names the mention; moving it is one action, a re-run of Extract
    Entities proposing Pedro again does not take it back, and undo returns it to Pedro."""
    _run(client, db, page)
    line = [row.id for row in _lines(db, page["kraken"].id)]
    answer = _EntitiesOnly(people=[_EntityOnly(name="Pedro Ruiz", aliases=["Ruiz"]),
                                   _EntityOnly(name="Francisco Ruiz", aliases=[])])
    await _entities(test_package, page, LLM, answer)
    (ruiz,) = _marks(client, line[1])["mentions"]
    assert (ruiz["name"], ruiz["excerpt"], ruiz["corrected_by_person"]) == ("Pedro Ruiz", "Ruiz", False)
    assert page["text"][ruiz["source_char_start"]:ruiz["source_char_end"]] == "Ruiz"
    francisco = _entity(client, db, "Francisco Ruiz")

    moved = _ok(client.post(f"/api/entities/{ruiz['entity_id']}/mentions/repoint", json={
        "document_id": page["doc"].id, "char_start": ruiz["source_char_start"],
        "char_end": ruiz["source_char_end"], "to_entity_id": francisco["id"]}))
    assert (moved["entity_id"], moved["segment_id"], moved["excerpt"]) == (francisco["id"], line[1], "Ruiz")
    (now,) = _marks(client, line[1])["mentions"]
    assert (now["name"], now["corrected_by_person"]) == ("Francisco Ruiz", True)
    # The person's mention replaces the "not written on the page" placeholder; Pedro keeps his first line.
    assert [s["source_excerpt"] for s in _entity(client, db, "Francisco Ruiz")["source_supports"]] == ["Ruiz"]
    assert [s["source_excerpt"] for s in _entity(client, db, "Pedro Ruiz")["source_supports"]] == ["Pedro Ruiz"]

    await _entities(test_package, page, LLM, answer)
    assert _named(client, line[1]) == [("Francisco Ruiz", "Ruiz")]
    assert _named(client, line[0]) == [("Pedro Ruiz", "Pedro Ruiz")]

    _undo(client, moved["audit_id"])
    assert _named(client, line[1]) == [("Pedro Ruiz", "Ruiz")]
    assert [s["source_excerpt"] for s in _entity(client, db, "Pedro Ruiz")["source_supports"]] == [
        "Pedro Ruiz", "Ruiz"]


@pytest.mark.asyncio
async def test_a_mentions_words_fixed_on_its_line_stay_fixed_and_undo(client, db, test_package, page, reader):
    """"fix its surface span": the model read only "Mena"; the person marks "Juan de Mena". WHY: the mark is
    the mention's words; a re-run finding "Mena" again must not put the short span back beside the fixed one."""
    _run(client, db, page)
    line = [row.id for row in _lines(db, page["kraken"].id)]
    answer = _EntitiesOnly(people=[_EntityOnly(name="Mena", aliases=[])])
    await _entities(test_package, page, LLM, answer)
    (mena,) = _marks(client, line[2])["mentions"]
    assert mena["excerpt"] == "Mena"
    full = page["text"].index("Juan de Mena")

    fixed = _ok(client.post(f"/api/entities/{mena['entity_id']}/mentions/respan", json={
        "document_id": page["doc"].id, "char_start": mena["source_char_start"],
        "char_end": mena["source_char_end"], "new_char_start": full, "new_char_end": full + len("Juan de Mena")}))
    assert (fixed["excerpt"], fixed["segment_id"]) == ("Juan de Mena", line[2])
    (now,) = _marks(client, line[2])["mentions"]
    assert (now["excerpt"], now["corrected_by_person"]) == ("Juan de Mena", True)
    assert "firmó ante Juan de Mena."[now["char_start"]:now["char_end"]] == "Juan de Mena"

    await _entities(test_package, page, LLM, answer)
    assert _named(client, line[2]) == [("Mena", "Juan de Mena")]

    _undo(client, fixed["audit_id"])
    assert _named(client, line[2]) == [("Mena", "Mena")]

    # A span that is not words of the page is refused, and nothing changes.
    refused = client.post(f"/api/entities/{mena['entity_id']}/mentions/respan", json={
        "document_id": page["doc"].id, "char_start": mena["source_char_start"],
        "char_end": mena["source_char_end"], "new_char_start": 5, "new_char_end": 5000})
    assert refused.status_code == 422, refused.text
    assert _named(client, line[2]) == [("Mena", "Mena")]


async def _people(test_package, page):
    section = next(s for s in _SECTIONS if s["name"] == "people_extract")
    answer = _SECTION_SCHEMAS[section["schema_key"]](items=[{
        "name": "Juan de Mena", "verb": "witnessed", "object": "the signature",
        "source_text": "firmó ante Juan de Mena."}])
    with patch("fichero_server.workflows.tools.extractors.chat_structured_with_fallback",
               new=AsyncMock(return_value=answer)):
        await _run_extractor(
            section,
            {"text": page["text"], "records": [{"doc_id": page["doc"].id, "text": page["text"]}]},
            {"library_path": str(test_package), "selected_doc_ids": [page["doc"].id], "task_id": "run-people"},
            LLM,
        )


@pytest.mark.asyncio
async def test_a_statements_date_and_rejection_from_its_line_survive_a_re_run_and_undo(
        client, db, test_package, page, reader):
    """"correct a date (the claim's date)" and "reject the statement", from the statement marked on its line.
    WHY: both go through the one action for the claim (`claim.patch`, `claim.transition`); a re-run of the
    extractor reproducing the statement matches the corrected row and changes neither."""
    _run(client, db, page)
    line = [row.id for row in _lines(db, page["kraken"].id)]
    await _people(test_package, page)
    (mark,) = _marks(client, line[2])["claims"]
    assert "firmó ante Juan de Mena."[mark["char_start"]:mark["char_end"]] == "firmó ante Juan de Mena."
    claim_id = mark["claim_id"]

    _ok(client.patch(f"/api/claims/{claim_id}", json={"time_start": "1650-03-01"}))
    dated = _last_audit(client, "claim.patch")
    _ok(client.patch(f"/api/claims/{claim_id}/transition", json={"to_state": "rejected", "reason": "misread"}))
    rejected = _last_audit(client, "claim.transition")
    assert [c["curation_state"] for c in _marks(client, line[2])["claims"]] == ["rejected"]

    await _people(test_package, page)
    claims = [c for c in db.query(KnowledgeClaim, source_document_id=page["doc"].id)
              if c.subject_canonical == "Juan de Mena"]
    assert [(c.id, c.curation_state.value, c.time_start) for c in claims] == [(claim_id, "rejected", "1650-03-01")]

    _undo(client, rejected)
    assert _ok(client.get(f"/api/claims/{claim_id}"))["curation_state"] == "unreviewed"
    _undo(client, dated)
    assert _ok(client.get(f"/api/claims/{claim_id}"))["time_start"] is None
