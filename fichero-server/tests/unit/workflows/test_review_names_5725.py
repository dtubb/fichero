"""The review is given the project's confirmed names and places (`source.job.review-uses-the-projects-names-and-places`, #5725).

Spec: a stub reviewer given "Popayán" in the list and a reading "Popaian" returns the list's spelling for that line.
The list is the project's VERIFIED entities (a name, a place, an organisation) with every other name they carry; an
entity nobody confirmed, a rejected one, a merged one and a concept are not on it. WHY: one place was spelled three ways
across a project's pages, and each review kept whichever the reader happened to produce.
"""
from __future__ import annotations

import re

import pytest

from fichero_server.models.knowledge import (
    EntityCurationState,
    EntityName,
    EntityType,
    KnowledgeEntity,
)
from tests.unit.workflows.test_review_corrects_the_lines_5654 import (  # noqa: F401
    REVIEWER,
    _lines,
    _page_text,
    page,
)

LISTED = re.compile(r"^- (?P<canon>.+?)(?: \(also written: (?P<variants>.+)\))?$", re.MULTILINE)


def _listed(prompt: str):
    """The entries of the confirmed-names list only (the rest of a prompt has bullets of its own)."""
    return list(LISTED.finditer(prompt.partition("confirmed names and places")[2]))


def _entity(db, name, kind=EntityType.location, state=EntityCurationState.verified, aliases=(), names=(), **kw):
    db.save(KnowledgeEntity(canonical_name=name, entity_type=kind, curation_state=state, aliases=list(aliases),
                            names=[EntityName(text=t) for t in names], **kw))


def _applying_the_list(prompt: str, reading: str) -> str:
    """A reviewer that does what it is told: a form listed as a variant is written as the confirmed spelling."""
    for found in _listed(prompt):
        for variant in (found["variants"] or "").split("; "):
            if variant:
                reading = reading.replace(variant, found["canon"])
    return reading


async def _answer(page, monkeypatch, reading):  # noqa: F811
    from fichero_server import llm
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.transcribe_review import transcribe_review

    seen = {}
    rows = _lines(page)

    async def reviewer(images, prompt, config, **kw):
        seen["prompt"] = prompt
        return "\n".join(f"{row.id} | certain | {_applying_the_list(prompt, reading if i == 1 else 'y lo firmo')}"
                         for i, row in enumerate(rows))

    monkeypatch.setattr(llm, "vision", reviewer)
    result = await transcribe_review(
        inputs={"files": page["src"]["files"], "documents": page["src"]["documents"], "skip_if_artifact_exists": False},
        state={"library_path": page["library"], "task_id": "run-names"},
        llm_config=LLMConfig(provider=REVIEWER[0], model=REVIEWER[1]))
    assert not result.get("error"), result.get("error")
    return seen["prompt"]


@pytest.mark.asyncio
async def test_a_reading_of_a_confirmed_names_variant_comes_back_in_the_confirmed_spelling_5725(page, monkeypatch):  # noqa: F811
    _entity(page["db"], "Popayán", aliases=["Popaian"])
    prompt = await _answer(page, monkeypatch, "vezino de Popaian")
    assert "Popayán" in prompt
    assert "vezino de Popayán" in _page_text(page)[0]


@pytest.mark.asyncio
async def test_without_the_list_the_variant_stays(page, monkeypatch):  # noqa: F811
    """The control: the stub only corrects what the list tells it, so the test above cannot pass by itself."""
    prompt = await _answer(page, monkeypatch, "vezino de Popaian")
    assert "confirmed names" not in prompt
    assert "vezino de Popaian" in _page_text(page)[0]


@pytest.mark.asyncio
async def test_only_what_a_person_confirmed_is_listed_with_every_other_name_it_carries_5725(page, monkeypatch):  # noqa: F811
    db = page["db"]
    _entity(db, "北京", names=["Beijing", "Peking"])
    _entity(db, "Gaspar de Lara", kind=EntityType.person)
    _entity(db, "Tunja", state=EntityCurationState.unreviewed)
    _entity(db, "Quito", state=EntityCurationState.rejected)
    _entity(db, "Cali", state=EntityCurationState.merged)
    _entity(db, "Honra", kind=EntityType.concept)
    prompt = await _answer(page, monkeypatch, "vezino de Popaian")
    listed = {m["canon"]: m["variants"] for m in _listed(prompt)}
    assert listed == {"北京": "Beijing; Peking", "Gaspar de Lara": None}


@pytest.mark.asyncio
async def test_a_project_with_no_confirmed_name_is_sent_no_empty_list_5725(page, monkeypatch):  # noqa: F811
    _entity(page["db"], "Tunja", state=EntityCurationState.unreviewed)
    assert "confirmed names" not in await _answer(page, monkeypatch, "vezino de Popaian")


def test_a_graph_larger_than_the_limit_says_how_many_are_left_out_5725(tmp_path):
    from fichero_server.recipes import known_names

    class Db:
        def query(self, model):
            return [KnowledgeEntity(canonical_name=f"Lugar {i:04}", entity_type=EntityType.location,
                                    curation_state=EntityCurationState.verified) for i in range(known_names.LIMIT + 2)]

    text = known_names.instruction(Db())
    assert len(_listed(text)) == known_names.LIMIT and "2 more confirmed names are not listed" in text
