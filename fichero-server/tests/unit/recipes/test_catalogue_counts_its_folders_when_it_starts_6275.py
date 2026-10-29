"""The Catalogue step counts its folders when it starts (#6275), after the reading steps before it have finished, not from
the Start plan, which was made before any page had text and said 0 folders. Test: the plan has 0 folders with text, then
reading fills 2 folders; the catalogue step writes 2."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from tests.unit.recipes.test_every_stage_resumes_after_a_stop_1134 import (  # noqa: F401  (fixtures)
    CATALOGUE,
    LINES,
    READ,
    _described,
    _finished,
    _folders,
    _recipe,
    _save,
    _start,
    _memory_is_not_the_question,
    engine,
    pages,
    stubs,
)


def test_the_catalogue_step_describes_the_folders_the_reading_filled(client, db, pages, tmp_path, stubs, monkeypatch,
                                                                     with_material):
    import fichero_server.llm as llm
    from fichero_server.models import DocType, Document

    _folders(db, pages)
    texted = [d for d in db.query(Document) if d.doc_type == DocType.page and (d.page_content or "").strip()]
    assert not texted, "the plan is made before any page has text"

    async def describe(material, config=None, system=None, permissive_guardrails=False):
        return "Title: A box.\nScope and content: Letters."

    monkeypatch.setattr(llm, "chat_with_fallback", describe)
    monkeypatch.setattr("fichero_server.recipes.runner.BATCH_PAGE_LIMIT", 1)  # a batch a folder
    _save(client, _recipe(tmp_path, LINES, READ, CATALOGUE))

    run = _finished(client, _start(client))

    assert run["state"] == "done", run
    assert _described(db) == {"Top", "Box 0", "Box 1"}, run

