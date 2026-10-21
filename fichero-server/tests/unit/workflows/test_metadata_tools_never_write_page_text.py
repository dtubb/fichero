"""A tool whose answer is not the page's text never writes it onto the page, and a page it overwrote gets its text back
(`source.read.metadata-tools-never-write-page-text`, #6002, P1 release bar: Classify Script over a PDF left each page's text as its
`{script_type, confidence, notes}` JSON in every release up to 2026.10.11).

NOT RUN on the Pro (the owner's presentation hour, 2026-10-21): the tester runs it on the M4.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import pkgutil
from unittest.mock import patch

import pytest

from fichero_server.maintenance import page_text_repair
from fichero_server.models import Artifact, DocType, Document, FileType
from fichero_server.workflows.tools import vision_base

CLASSIFICATION = json.dumps({"script_type": "manuscript", "confidence": 0.9, "notes": "a secretary hand"})
TRANSCRIPT = "Don Juan de Mosquera vendió una casa."


def _metadata_tool_configs() -> list[vision_base.VisionToolConfig]:
    """Every vision tool in the engine that does not write page text (update_page_content False): the sweep."""
    import fichero_server.workflows.tools as tools

    found = []
    for module in pkgutil.iter_modules(tools.__path__):
        try:
            loaded = importlib.import_module(f"{tools.__name__}.{module.name}")
        except Exception:  # noqa: BLE001 -- a module that needs an optional dependency is not a vision tool here
            continue
        config = getattr(loaded, "TOOL_CONFIG", None)
        if isinstance(config, vision_base.VisionToolConfig) and not config.update_page_content:
            found.append(config)
    return found


METADATA_TOOLS = _metadata_tool_configs()


def _pdf_with_pages(db, n=2):
    parent = Document(name="book.pdf", doc_type=DocType.file, file_type=FileType.pdf, path="/book.pdf")
    db.save(parent)
    pages = []
    for i in range(n):
        page = Document(name=f"p{i + 1}", doc_type=DocType.page, parent_id=parent.id, sequence=i + 1,
                        page_content=TRANSCRIPT)
        db.save(page)
        pages.append(page)
    return parent, pages


def test_the_sweep_finds_classify_script_and_other_metadata_tools():
    assert "script_classification" in {c.artifact_type for c in METADATA_TOOLS}


@pytest.mark.parametrize("config", METADATA_TOOLS, ids=lambda c: c.artifact_type)
def test_a_metadata_tool_over_a_pdf_leaves_each_pages_text_and_saves_its_artifact(db, config):
    from fichero_server.llm import LLMConfig

    parent, pages = _pdf_with_pages(db)
    with patch("fichero_server.db.db_manager") as manager:
        manager.get_database.return_value = db
        asyncio.run(vision_base._propagate_to_page_children(
            parent.id, [CLASSIFICATION, CLASSIFICATION], "/lib.fichero", artifact_type=config.artifact_type,
            llm_config=LLMConfig(provider="openai", model="gpt-5"), update_page_content=config.update_page_content))

    for page in pages:
        assert db.get(Document, page.id).page_content == TRANSCRIPT, "the tool replaced the page's text"
        assert [a for a in db.query(Artifact, document_id=page.id) if a.artifact_type == config.artifact_type], "no artifact"


def test_a_transcribing_tool_still_writes_the_page_text_but_not_over_a_persons_edit(db):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.curation_guard import PAGE_CONTENT_USER_EDITED_KEY

    parent, (first, second) = _pdf_with_pages(db)
    second.metadata = {PAGE_CONTENT_USER_EDITED_KEY: "2026-10-21T00:00:00"}
    second.page_content = "a person's text"
    db.save(second)
    with patch("fichero_server.db.db_manager") as manager:
        manager.get_database.return_value = db
        asyncio.run(vision_base._propagate_to_page_children(
            parent.id, ["new reading one", "new reading two"], "/lib.fichero", artifact_type="transcription",
            llm_config=LLMConfig(provider="openai", model="gpt-5"), update_page_content=True))
    assert db.get(Document, first.id).page_content == "new reading one"
    assert db.get(Document, second.id).page_content == "a person's text"


def _overwritten(db, *, transcript=True, edited=False):
    _parent, (page, _other) = _pdf_with_pages(db)
    if transcript:
        db.save(Artifact(document_id=page.id, artifact_type="transcription", content=TRANSCRIPT, provider="openai",
                         model="gpt-5"))
    db.save(Artifact(document_id=page.id, artifact_type="script_classification", content=CLASSIFICATION,
                     provider="openai", model="gpt-5"))
    page.page_content = CLASSIFICATION
    if edited:
        page.metadata = {"page_content_user_edited_at": "2026-10-21T00:00:00"}
    db.save(page)
    return page


def test_the_repair_restores_the_transcription_and_a_second_run_changes_nothing(db):
    page = _overwritten(db)
    counted = page_text_repair.repair_classification_page_text(db, dry_run=True)
    assert counted["restored"] == [page.id] and db.get(Document, page.id).page_content == CLASSIFICATION  # counting writes nothing
    done = page_text_repair.repair_on_open(db)
    assert done["restored"] == [page.id] and db.get(Document, page.id).page_content == TRANSCRIPT
    again = page_text_repair.repair_on_open(db)
    assert again["restored"] == []  # nothing left to restore


def test_the_repair_never_touches_a_text_a_person_saved(db):
    page = _overwritten(db, edited=True)
    result = page_text_repair.repair_on_open(db)
    assert result["left_edited"] == [page.id] and db.get(Document, page.id).page_content == CLASSIFICATION


def test_a_page_with_nothing_to_restore_keeps_its_text_and_gets_the_flag(db):
    from fichero_server.llm.read_guard import READ_FLAG_KEY, read_flag_of

    page = _overwritten(db, transcript=False)
    counted = page_text_repair.repair_classification_page_text(db, dry_run=True)
    assert counted["flagged"] == [page.id] and read_flag_of(db.get(Document, page.id)) is None  # counting marks nothing
    result = page_text_repair.repair_on_open(db)
    assert result["flagged"] == [page.id] and result["restored"] == []
    kept = db.get(Document, page.id)
    assert kept.page_content == CLASSIFICATION, "the page was blanked or changed"
    assert read_flag_of(kept)["kind"] == page_text_repair.NEEDS_REREADING and READ_FLAG_KEY in kept.metadata
    again = page_text_repair.repair_on_open(db)
    assert again["newly_flagged"] == [] and db.get(Document, page.id).page_content == CLASSIFICATION  # idempotent


def test_a_real_text_that_mentions_script_type_is_not_a_classification():
    assert not page_text_repair.is_classification_json("the script_type of this hand is secretary")
    assert not page_text_repair.is_classification_json(json.dumps({"script_type": "x", "confidence": 1, "chapter": 2}))
    assert page_text_repair.is_classification_json("```json\n" + CLASSIFICATION + "\n```")


def _repair_rows(db):
    return db.execute_fetchall("SELECT state, reason FROM jobs WHERE id LIKE 'repair-page-text-%'")


def test_the_repair_records_one_finished_activity_row_when_it_changed_something(db):
    _parent, (restorable, hopeless) = _pdf_with_pages(db)
    db.save(Artifact(document_id=restorable.id, artifact_type="transcription", content=TRANSCRIPT, provider="openai",
                     model="gpt-5"))
    for page in (restorable, hopeless):
        page.page_content = CLASSIFICATION
        db.save(page)
    page_text_repair.repair_on_open(db)
    assert _repair_rows(db) == [("done", "1 page restored, 1 needs re-reading")]
    page_text_repair.repair_on_open(db)  # nothing new: no second row
    assert len(_repair_rows(db)) == 1


def test_the_repair_records_no_row_when_there_is_nothing_to_repair(db):
    _pdf_with_pages(db)
    page_text_repair.repair_on_open(db)
    assert _repair_rows(db) == []


def test_a_later_successful_read_clears_the_needs_re_reading_flag_and_a_metadata_tool_does_not(db):
    from fichero_server.llm import LLMConfig
    from fichero_server.llm.read_guard import read_flag_of

    page = _overwritten(db, transcript=False)
    page_text_repair.repair_on_open(db)
    assert read_flag_of(db.get(Document, page.id)) is not None
    parent_id = page.parent_id
    llm = LLMConfig(provider="openai", model="gpt-5")
    with patch("fichero_server.db.db_manager") as manager:
        manager.get_database.return_value = db
        asyncio.run(vision_base._propagate_to_page_children(  # a classifier again: nothing is written, the flag stays
            parent_id, [CLASSIFICATION, CLASSIFICATION], "/lib.fichero", artifact_type="script_classification",
            llm_config=llm, update_page_content=False))
        assert read_flag_of(db.get(Document, page.id)) is not None
        asyncio.run(vision_base._propagate_to_page_children(  # a real read: the text is written and the flag is answered
            parent_id, [TRANSCRIPT, TRANSCRIPT], "/lib.fichero", artifact_type="transcription", llm_config=llm,
            update_page_content=True))
    again = db.get(Document, page.id)
    assert again.page_content == TRANSCRIPT and read_flag_of(again) is None


def test_the_flag_is_typed_on_the_document_and_the_inspector_responses(client, db):
    page = _overwritten(db, transcript=False)
    page_text_repair.repair_on_open(db)
    expected = {"kind": page_text_repair.NEEDS_REREADING, "measure": None,
                "reason": "a classifier's answer had replaced this page's text and no transcription or text layer is left "
                          "to restore it from: read the page again"}
    assert client.get(f"/api/documents/{page.id}").json()["read_flag"] == expected
    assert client.get(f"/api/documents/{page.id}/inspector").json()["read_flag"] == expected
    other = _pdf_with_pages(db)[1][0]
    assert client.get(f"/api/documents/{other.id}").json()["read_flag"] is None
    assert client.get(f"/api/documents/{other.id}/inspector").json()["read_flag"] is None


def test_the_repair_queues_the_embed_and_does_not_run_it_inline(db, monkeypatch):
    queued = []
    monkeypatch.setattr("fichero_server.actions.page_text_cache.queue_reembed", lambda _db, ids: queued.append(list(ids)))
    page = _overwritten(db)
    monkeypatch.setattr(db, "embed", lambda *_a, **_k: pytest.fail("the repair embedded inline"), raising=False)
    page_text_repair.repair_on_open(db)
    assert queued == [[page.id]]


def test_a_flagged_reads_measure_rides_on_the_typed_flag():
    from fichero_server.llm.read_guard import READ_FLAG_KEY, ReadFlag, typed_read_flag

    flag = ReadFlag(kind="repetition", reason="the same phrase twelve times", measure={"repeats": 12})
    holder = Document(name="p", doc_type=DocType.page, metadata={READ_FLAG_KEY: flag.as_data()})
    info = typed_read_flag(holder)
    assert (info.kind, info.reason, info.measure) == ("repetition", "the same phrase twelve times", {"repeats": 12})


def _flagged(db):
    from fichero_server.llm.read_guard import read_flag_of

    page = _overwritten(db, transcript=False)
    page_text_repair.repair_on_open(db)
    assert read_flag_of(db.get(Document, page.id)) is not None
    return page


def test_a_persons_edit_clears_the_flag(client, db):
    from fichero_server.llm.read_guard import read_flag_of

    page = _flagged(db)
    assert client.put(f"/api/documents/{page.id}", json={"page_content": "my own reading"}).status_code == 200
    saved = db.get(Document, page.id)
    assert saved.page_content == "my own reading" and read_flag_of(saved) is None


def test_text_derived_from_the_lines_clears_the_flag(db):
    from fichero_server.actions import page_text_cache
    from fichero_server.core.timeutil import utc_now
    from fichero_server.llm.read_guard import read_flag_of

    page = _flagged(db)
    page_text_cache._store(db, db.get(Document, page.id), "line one line two", utc_now(), None)
    saved = db.get(Document, page.id)
    assert saved.page_content == "line one line two" and read_flag_of(saved) is None


def test_the_fan_in_join_clears_the_flag(db):
    from fichero_server.llm.read_guard import read_flag_of

    page = _flagged(db)
    failures = vision_base._write_joined_page_content(
        indices_by_doc={page.id: [0, 1]}, texts=["first", "second"], library_path=str(db.path))
    saved = db.get(Document, page.id)
    assert not failures and saved.page_content == "first\nsecond" and read_flag_of(saved) is None
