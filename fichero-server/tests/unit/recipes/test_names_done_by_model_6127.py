"""A free spaCy draft is not "names already done" for a step that chose a real model (never-rerun-a-model-pass, #6127),
to the spec `source.recipe.done-is-not-redone`.

WHY: a folder-scoped Start plan for the names step (Sonnet) said "already done on all 874 pages" when Sonnet ran on one folder only;
the other pages carried the import-time spaCy draft (es_core_news_sm), which counted as done."""

from __future__ import annotations

import pytest

from fichero_server.models import DocType, Document, FileType, KnowledgeEntity
from fichero_server.recipes import done
from fichero_server.workflows.tools._entity_writer import run_attribution

SONNET = "claude-sonnet-4-5"
CARD = {"steps": ["find-names"], "job": "find-names-tag-words", "card": "workflow", "workflow_id": "w",
        "provider_override": "anthropic", "model_override": SONNET}


def _page(db, name):
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image)
    db.save(doc)
    return doc.id


def _entity(db, page, attribution):
    entity = KnowledgeEntity(canonical_name=f"Nombre {page[:6]}", source_document_ids=[page])
    entity.add_attribution({**attribution, "document_id": page} if attribution.get("role") == "extractor" else attribution)
    db.save(entity)


def _todo(db, pages, card=CARD):
    return done.split_done(db, card, pages)


def test_a_spacy_draft_is_not_done_for_sonnet(client, db):
    page = _page(db, "draft")
    _entity(db, page, run_attribution("spacy", "es_core_news_sm", "import"))
    assert _todo(db, [page]) == ([page], 0)


def test_a_sonnet_result_is_done(client, db):
    page = _page(db, "sonnet")
    _entity(db, page, run_attribution("anthropic", SONNET, "run1"))
    assert _todo(db, [page]) == ([], 1)


def test_a_persons_names_are_done(client, db):
    page = _page(db, "person")
    _entity(db, page, {"role": "editor", "name": "owner", "basis": "asserted"})
    assert _todo(db, [page]) == ([], 1)


def test_a_draft_is_still_done_for_the_free_step(client, db):
    page = _page(db, "free")
    _entity(db, page, run_attribution("spacy", "es_core_news_sm", "import"))
    free = {**CARD, "provider_override": "spacy", "model_override": "es_core_news_sm"}
    assert _todo(db, [page], free) == ([], 1)


def test_one_entity_on_two_pages_is_done_only_where_sonnet_read(client, db):
    drafted, read = _page(db, "a"), _page(db, "b")
    entity = KnowledgeEntity(canonical_name="Pedro", source_document_ids=[drafted, read])
    entity.add_attribution({**run_attribution("spacy", "es_core_news_sm", "import"), "document_id": drafted})
    entity.add_attribution({**run_attribution("anthropic", SONNET, "run1"), "document_id": read})
    db.save(entity)
    assert _todo(db, [drafted, read]) == ([drafted], 1)


def test_an_entity_with_no_extractor_is_done(client, db):
    page = _page(db, "bare")
    db.save(KnowledgeEntity(canonical_name="Sin Autor", source_document_ids=[page]))
    assert _todo(db, [page]) == ([], 1)


def test_an_older_entry_of_the_model_stays_done_after_a_later_draft(client, db):
    a, b = _page(db, "a"), _page(db, "b")
    entity = KnowledgeEntity(canonical_name="Pedro", source_document_ids=[a, b])
    entity.add_attribution(run_attribution("anthropic", SONNET, "run1"))  # older: names no page
    entity.add_attribution({**run_attribution("spacy", "es_core_news_sm", "import"), "document_id": a})
    db.save(entity)
    assert _todo(db, [a, b]) == ([], 2)


def test_a_run_of_a_workflows_model_counts_for_a_card_that_names_it_by_the_workflow(client, db, monkeypatch):
    """The card the run saved carries no model_override; its workflow's model is the one it read with (as `names_model`)."""
    import json

    from fichero_server.execution import jobs
    from fichero_server.models import Workflow

    db.save(Workflow(id="w2", name="names", model=SONNET))
    card = {k: v for k, v in CARD.items() if k != "model_override"} | {"workflow_id": "w2"}
    detail = json.dumps({"runs": [card], "steps": [{"ran_on": ["p1"]}]})
    monkeypatch.setattr(jobs, "find_jobs", lambda *a, **k: [{"id": "j"}])
    monkeypatch.setattr(jobs, "read_job", lambda *a, **k: {"detail": detail})
    assert done.pages_a_run_did(db, "find-names-tag-words", done.names_model(db, card)) == {"p1"}


def test_a_name_on_many_pages_is_one_step_not_one_per_page(client, db):
    pages = [_page(db, f"p{i}") for i in range(5)]
    entity = KnowledgeEntity(canonical_name="Pedro", source_document_ids=pages)
    for page in pages:
        entity.add_attribution({**run_attribution("anthropic", SONNET, "run1"), "document_id": page})
    db.save(entity)
    assert len(entity.attribution_chain) == 1
    assert _todo(db, pages) == ([], 5)


# --- an older entry that names no page counts for the pages its run covered (#6285) ---


def _run(db, run_id, pages, status="completed"):
    """The workflow run's record, with the pages the server resolved it to (what `pages_a_run_did` cannot see for a
    run that was not a recipe step)."""
    from datetime import datetime, timezone

    from fichero_server.db import activity_records as records

    records.upsert_run(db, thread_id=run_id, workflow_id="w", workflow_name="names", python_code=None, execution_log=None,
                       workflow_snapshot=None, node_name_map=None, progress_timeline=None, diagram_mermaid=None,
                       status=status, started_at=datetime.now(timezone.utc),
                       resolved_scope={"resolved_ids": list(pages), "resolved_count": len(pages)}, estimated_cost=None)


def _library_with_old_sonnet_entry(db, run_id):
    """10 pages, spaCy drafts on all; one common name carries an older Sonnet entry that names no page."""
    pages = [_page(db, f"p{i}") for i in range(10)]
    entity = KnowledgeEntity(canonical_name="Pedro", source_document_ids=pages)
    entity.add_attribution(run_attribution("anthropic", SONNET, run_id))  # older: names no page
    for page in pages:
        entity.add_attribution({**run_attribution("spacy", "es_core_news_sm", "import"), "document_id": page})
    db.save(entity)
    return pages


def test_an_older_entry_naming_no_page_counts_only_for_the_pages_its_run_covered(client, db):
    pages = _library_with_old_sonnet_entry(db, "run-old")
    _run(db, "run-old", pages[:1])
    todo, finished = _todo(db, pages)
    assert (len(todo), finished) == (9, 1)
    assert pages[0] not in todo


@pytest.mark.parametrize("status", ["failed", "cancelled", "stopped"])
def test_a_run_that_did_not_complete_does_not_mark_its_unreached_pages_done(client, db, status):
    """Sonnet read page 1 and the run died / was stopped at page 2: its scope was all 10 pages, but 8 were never read.
    The older entry names no page, so none of the scope counts: 10 to do, 0 done."""
    pages = _library_with_old_sonnet_entry(db, "run-died")
    _run(db, "run-died", pages, status=status)
    todo, finished = _todo(db, pages)
    assert (len(todo), finished) == (10, 0)


def test_a_page_a_failed_run_named_stays_done_and_the_rest_are_read_again(client, db):
    pages = _library_with_old_sonnet_entry(db, "run-died")
    other = KnowledgeEntity(canonical_name="Ana", source_document_ids=[pages[0]])
    other.add_attribution({**run_attribution("anthropic", SONNET, "run-died"), "document_id": pages[0]})
    db.save(other)
    _run(db, "run-died", pages, status="failed")
    todo, finished = _todo(db, pages)
    assert (len(todo), finished) == (9, 1)
    assert pages[0] not in todo


def test_an_older_entry_whose_run_cannot_be_found_counts_for_all_the_entitys_pages(client, db):
    pages = _library_with_old_sonnet_entry(db, "run-gone")
    assert _todo(db, pages) == ([], 10)
    pages = _library_with_old_sonnet_entry(db, None)
    assert _todo(db, pages) == ([], 10)


def test_an_older_entry_of_a_recipe_step_run_is_done_for_the_folder_and_not_rerun(client, db, monkeypatch):
    import json

    from fichero_server.execution import jobs
    from fichero_server.models import Workflow

    db.save(Workflow(id="w3", name="names", model=SONNET))
    pages = _library_with_old_sonnet_entry(db, "run-step")
    _run(db, "run-step", pages[:4])
    card = {k: v for k, v in CARD.items() if k != "model_override"} | {"workflow_id": "w3"}
    detail = json.dumps({"runs": [card], "steps": [{"ran_on": pages[:4]}]})
    monkeypatch.setattr(jobs, "find_jobs", lambda *a, **k: [{"id": "j"}])
    monkeypatch.setattr(jobs, "read_job", lambda *a, **k: {"detail": detail})
    todo, finished = _todo(db, pages, card)
    assert (len(todo), finished) == (6, 4)
    assert not set(pages[:4]) & set(todo)


# --- the free layer is told by the card's provider, or its workflow's, in any case (#6285) ---


def test_a_card_with_no_override_whose_workflow_is_spacy_in_mixed_case_is_the_free_layer(client, db):
    from fichero_server.models import Workflow

    db.save(Workflow(id="w4", name="names", provider="SpaCy_NER", model="es_core_news_sm"))
    card = {"steps": ["find-names"], "job": "find-names-tag-words", "card": "workflow", "workflow_id": "w4"}
    assert done.names_model(db, card) is None
    page = _page(db, "free2")
    _entity(db, page, run_attribution("spacy", "es_core_news_sm", "import"))
    assert _todo(db, [page], card) == ([], 1)


def test_a_card_override_in_mixed_case_is_the_free_layer(client, db):
    assert done.names_model(db, {**CARD, "provider_override": "SpaCy"}) is None
