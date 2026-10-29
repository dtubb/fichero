"""The catalogue is a folder's own record, all of it, once (#6267, `catalogue.scope-and-arrangement-are-attributes`,
`catalogue.promote-is-undoable-and-idempotent`): Scope and content and Arrangement are attributes too, and
`folder.promote_catalogue` brings a folder described earlier up to date with no model call."""
from __future__ import annotations

import fichero_server.api.routes.document.documents  # noqa: F401  (registers the actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.actions.undo import undo_set
from fichero_server.models import Artifact, DocType, Document
from fichero_server.recipes import catalogue_step

OLD = "Title: Wheat letters.\nDates: 1776.\nDescription: A short paragraph."
NEW = OLD + "\nScope and content: Letters about wheat.\nArrangement: By date, then by sender."
CTX = ActionContext(actor="ui", library_path="")


def test_scope_and_arrangement_are_parsed_as_attributes():
    got = catalogue_step.parse_fields(NEW)
    assert got["catalogue_scope_content"] == "Letters about wheat."
    assert got["catalogue_arrangement"] == "By date, then by sender."
    assert "Short paragraph" not in str(got)  # Description is still prose only


def _described_folder(db, text=OLD):
    box = Document(name="Box 1", doc_type=DocType.folder)
    db.save(box)
    art = Artifact(document_id=box.id, artifact_type=catalogue_step.ARTIFACT_TYPE, content=text, provider="p", model="m")
    db.save(art)
    catalogue_step.put_in_content(db, box.id, text, art.id)
    catalogue_step.put_in_attributes(db, box.id, text, art.id, run_id="r1", provider="p", model="m")
    return box.id, art


def _promote(db, **params):
    return registry.invoke(db, "folder.promote_catalogue", params, CTX)


def test_promote_gives_an_earlier_folder_the_new_keys_and_is_idempotent(db):
    box, art = _described_folder(db)
    art.content = NEW  # the saved description now carries the two fields; the folder's attributes do not
    db.save(art)
    assert "catalogue_scope_content" not in (db.get(Document, box).attributes or {})
    assert _promote(db).result["promoted"] == [box]
    folder = db.get(Document, box)
    assert folder.attributes["catalogue_scope_content"] == "Letters about wheat."
    assert folder.attributes["catalogue_title"] == "Wheat letters." and folder.page_content == NEW
    assert _promote(db, folder_id=box).result["promoted"] == []  # nothing left to change


def test_promote_is_undone_to_what_the_folder_held(db):
    box, art = _described_folder(db)
    art.content = NEW
    db.save(art)
    was = db.get(Document, box)
    before = (was.page_content, dict(was.attributes))
    audit_id = _promote(db, folder_id=box).audit_id
    undo_set(db, [audit_id], CTX)
    folder = db.get(Document, box)
    assert (folder.page_content, dict(folder.attributes)) == before


def test_promote_overwrites_a_machine_value_the_old_parser_got_wrong_and_undo_restores_it(db):
    """`catalogue.promote-is-undoable-and-idempotent`: the CURRENT parser's value replaces what an older parser wrote;
    a value a person set is left alone."""
    from fichero_server.workflows import attribute_sources as sources

    text = ("Title: Box.\nDates: 1776 - 1780.\nCondition: Good.\nAccess points: Ana Ruiz; Sevilla.\n"
            "Description: x.")
    box, art = _described_folder(db, text)
    folder = db.get(Document, box)
    folder.attributes = {**folder.attributes, "catalogue_condition": "Good. Ana Ruiz; Sevilla.", "catalogue_date_start": "1780",
                         "catalogue_title": "Mine"}
    folder.metadata = sources.with_sources(folder.metadata, {"catalogue_title": {"by": "person"}})
    db.save(folder)
    audit_id = _promote(db, folder_id=box).audit_id
    attrs = db.get(Document, box).attributes
    assert attrs["catalogue_condition"] == "Good." and attrs["catalogue_date_start"] == "1776"
    assert attrs["catalogue_title"] == "Mine"
    undo_set(db, [audit_id], CTX)
    attrs = db.get(Document, box).attributes
    assert attrs["catalogue_condition"] == "Good. Ana Ruiz; Sevilla." and attrs["catalogue_date_start"] == "1780"


def test_access_points_after_a_closing_bracket_are_not_the_condition():
    got = catalogue_step.parse_fields("Condition: Faded [uncertain] Access points: Ana Ruiz; Sevilla.\nDescription: x.")
    assert got["catalogue_condition"] == "Faded [uncertain]"
    assert got["catalogue_access_points"] == ["Ana Ruiz", "Sevilla"]


def test_the_english_uncertain_marker_is_spanish_in_a_spanish_attribute():
    text = "Condition: Mancha [uncertain] en la hoja.\nDescription: x."
    assert catalogue_step.parse_fields(text, "Spanish")["catalogue_condition"] == "Mancha [incierto] en la hoja."
    assert "[uncertain]" in catalogue_step.parse_fields(text, "English")["catalogue_condition"]


def test_a_rerun_is_version_two_and_promote_reads_the_latest(db, monkeypatch):
    from fichero_server.llm import LLMConfig

    answer = {"text": OLD}

    async def fake(material, config, system=None, permissive_guardrails=False):
        return answer["text"]

    monkeypatch.setattr("fichero_server.llm.chat_with_fallback", fake)
    box = Document(name="Box", doc_type=DocType.folder)
    db.save(box)
    page = Document(name="p", doc_type=DocType.page, parent_id=box.id, page_content="Letter one")
    db.save(page)
    config = LLMConfig(provider="fake", model="fake")
    catalogue_step.describe_folders(db, [page.id], config, run_id="r1")
    page.page_content = "Letter one, changed"
    db.save(page)
    answer["text"] = NEW
    catalogue_step.describe_folders(db, [page.id], config, run_id="r2")
    arts = sorted(db.query(Artifact, document_id=box.id), key=lambda a: a.version)
    assert [a.version for a in arts] == [1, 2] and arts[1].source_artifact_id == arts[0].id
    assert catalogue_step._latest(db, box.id).id == arts[1].id


def _folder_with_old_text(db, parent_id=None, name="Box"):
    box = Document(name=name, doc_type=DocType.folder, parent_id=parent_id)
    db.save(box)
    db.save(Artifact(document_id=box.id, artifact_type=catalogue_step.ARTIFACT_TYPE, content=NEW, provider="p", model="m"))
    return box.id


def test_recursive_promote_reaches_every_depth(db):
    top = _folder_with_old_text(db, name="Top")
    mid = _folder_with_old_text(db, top, "Mid")
    low = _folder_with_old_text(db, mid, "Low")
    assert set(_promote(db, folder_id=top).result["promoted"]) == {top, mid, low}
    assert db.get(Document, low).attributes["catalogue_title"] == "Wheat letters."
    assert _promote(db, folder_id=top, recursive=False).result["promoted"] == []


def test_undo_restores_content_queues_a_reembed_and_leaves_other_keys(db, monkeypatch):
    box, art = _described_folder(db)
    art.content = NEW
    db.save(art)
    queued: list = []
    monkeypatch.setattr("fichero_server.actions.page_text_cache.queue_reembed", lambda _db, ids: queued.append(ids))
    audit_id = _promote(db, folder_id=box).audit_id
    folder = db.get(Document, box)
    folder.attributes = {**folder.attributes, "mine": "kept"}  # a later edit to a key promote never touched
    folder.metadata = {**folder.metadata, "note": "kept"}
    db.save(folder)
    queued.clear()
    undo_set(db, [audit_id], CTX)
    back = db.get(Document, box)
    assert back.page_content == OLD and [box] in queued
    assert "catalogue_scope_content" not in back.attributes and back.attributes["mine"] == "kept"
    assert back.metadata["note"] == "kept"


def test_a_language_code_is_matched_not_a_prefix():
    text = "Condition: bien [uncertain]."
    assert "[incierto]" in catalogue_step.parse_fields(text, "es-CO")["catalogue_condition"]
    assert "[uncertain]" in catalogue_step.parse_fields(text, "estonian")["catalogue_condition"]


def _promoted_then(db, edit):
    box, art = _described_folder(db)
    art.content = NEW
    db.save(art)
    audit_id = _promote(db, folder_id=box).audit_id
    folder = db.get(Document, box)
    edit(folder)
    db.save(folder)
    undo_set(db, [audit_id], CTX)
    return db.get(Document, box)


def test_undo_leaves_a_value_a_person_set_after_promote_and_other_sources(db):
    from fichero_server.workflows.attribute_sources import BY_PERSON, SOURCES

    def edit(folder):
        folder.attributes = {**folder.attributes, "catalogue_scope_content": "My own scope."}
        folder.metadata = {**folder.metadata, SOURCES: {**folder.metadata[SOURCES], "catalogue_scope_content": {"by": BY_PERSON}}}

    back = _promoted_then(db, edit)
    assert back.attributes["catalogue_scope_content"] == "My own scope."
    assert back.metadata[SOURCES]["catalogue_scope_content"] == {"by": BY_PERSON}
    assert "catalogue_arrangement" not in back.attributes  # promote's other keys are put back
    assert back.metadata[SOURCES]["catalogue_title"]["by"] == "machine"  # a key promote did not change keeps its source


def test_undo_leaves_content_changed_since_promote(db):
    back = _promoted_then(db, lambda folder: setattr(folder, "page_content", "A person rewrote this."))
    assert back.page_content == "A person rewrote this."
    assert "catalogue_content_from" in back.metadata  # the key that goes with the content stays with it


DATES_OLD = "Title: Wheat letters.\nDates: 1776."
DATES_NEW = "Title: Wheat letters.\nDates: 1780 - 1790."


def _promote_dates_then(db, edit):
    box, art = _described_folder(db, DATES_OLD)
    art.content = DATES_NEW
    db.save(art)
    audit_id = _promote(db, folder_id=box).audit_id
    folder = db.get(Document, box)
    edit(folder)
    db.save(folder)
    undo_set(db, [audit_id], CTX)
    return db.get(Document, box)


def test_undo_keeps_the_dates_group_when_a_person_edited_the_text(db):
    back = _promote_dates_then(db, lambda f: f.attributes.update({"catalogue_dates": "about 1785"}))
    assert back.attributes["catalogue_dates"] == "about 1785"
    assert (back.attributes["catalogue_date_start"], back.attributes["catalogue_date_end"]) == ("1780", "1790")
    assert back.attributes["catalogue_date_normalised"] == "1780/1790"
    from fichero_server.workflows.attribute_sources import SOURCES

    assert back.metadata[SOURCES]["catalogue_dates"] == {"by": "person"}  # a plain edit carries a person's source


def test_undo_keeps_the_dates_group_when_a_person_confirmed_the_dates(db):
    from fichero_server.workflows.attribute_sources import SOURCES

    def confirm(folder):
        sources = dict(folder.metadata[SOURCES])
        sources["catalogue_dates"] = {**sources["catalogue_dates"], "accepted_by": "someone"}
        folder.metadata = {**folder.metadata, SOURCES: sources}

    back = _promote_dates_then(db, confirm)
    assert back.attributes["catalogue_dates"] == "1780 - 1790."
    assert back.attributes["catalogue_date_start"] == "1780" and back.attributes["catalogue_date_normalised"] == "1780/1790"
