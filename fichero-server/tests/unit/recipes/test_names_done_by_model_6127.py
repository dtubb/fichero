"""A free spaCy draft is not "names already done" for a step that chose a real model (never-rerun-a-model-pass, #6127),
to the spec `source.recipe.done-is-not-redone`.

WHY: a folder-scoped Start plan for the names step (Sonnet) said "already done on all 874 pages" when Sonnet ran on one folder only;
the other pages carried the import-time spaCy draft (es_core_news_sm), which counted as done."""

from __future__ import annotations

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
