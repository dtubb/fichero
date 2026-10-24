"""The Catalogue stage (#6087, `catalogue.folder-description-fields`, `source.recipe.catalogue-follows-new-material`):
a folder's description is written from its pages, deepest folder first, up to the one length setting, and redone only
where new pages changed what a folder covers."""
from __future__ import annotations

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document
from fichero_server.recipes import catalogue_step

CONFIG = LLMConfig(provider="fake", model="fake")


@pytest.fixture
def asked(monkeypatch):
    """The model, faked: the folder's material is what it is asked about; each call is kept."""
    calls: list[str] = []

    async def fake(material, config, system=None, permissive_guardrails=False):
        calls.append(material)
        return "Title: A box.\nScope and content: Letters about wheat."

    monkeypatch.setattr("fichero_server.llm.chat_with_fallback", fake)
    return calls


def _node(db, name, doc_type, parent=None, text=""):
    doc = Document(name=name, doc_type=doc_type, parent_id=parent, page_content=text)
    db.save(doc)
    return doc.id


def _tree(db):
    top = _node(db, "Top", DocType.folder)
    box = _node(db, "Box 1", DocType.folder, top)
    pages = [_node(db, f"p{i}", DocType.page, box, f"Letter {i} about wheat") for i in range(2)]
    return top, box, pages


def test_each_folder_above_the_pages_is_described_deepest_first(db, asked):
    top, box, pages = _tree(db)
    account = catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    assert account["described"] == 2 and not account["failed"]
    assert "Letter 0 about wheat" in asked[0] and "Box 1" in asked[0]
    assert "Description of subfolder Box 1" in asked[1]  # the parent is told what its subfolder holds


def test_a_second_run_changes_nothing(db, asked):
    _top, _box, pages = _tree(db)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    again = catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    assert again["described"] == 0 and again["unchanged"] == 2 and len(asked) == 2


def test_a_new_folder_redoes_itself_and_its_parent_only(db, asked):
    top, box, pages = _tree(db)
    other = _node(db, "Box 0", DocType.folder, top)
    old = [_node(db, "q", DocType.page, other, "Old letter")]
    catalogue_step.describe_folders(db, pages + old, CONFIG, run_id=None)
    asked.clear()
    fresh = _node(db, "Box 2", DocType.folder, top)
    new = [_node(db, f"n{i}", DocType.page, fresh, f"New letter {i}") for i in range(3)]
    account = catalogue_step.describe_folders(db, new, CONFIG, run_id=None)
    assert account["described"] == 2  # Box 2 and Top; Box 0 and Box 1 are not asked again
    assert len(asked) == 2 and not any(m.startswith(("Folder name: Box 0", "Folder name: Box 1")) for m in asked)


def test_a_folder_with_no_reading_is_left_without_a_description(db, asked):
    top = _node(db, "Empty", DocType.folder)
    page = _node(db, "blank", DocType.page, top, "")
    account = catalogue_step.describe_folders(db, [page], CONFIG, run_id=None)
    assert account["no_text"] == 1 and not asked


def test_the_description_is_held_to_the_one_length_setting(db, monkeypatch):
    async def long(material, config, system=None, permissive_guardrails=False):
        return " ".join(f"Word{i} here." for i in range(400))  # 800 words, over 500

    monkeypatch.setattr("fichero_server.llm.chat_with_fallback", long)
    _top, _box, pages = _tree(db)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    art = catalogue_step._latest(db, _box)
    assert len(art.content.split()) <= catalogue_step.FOLDER_DESCRIPTION_MAX_WORDS


def test_the_catalogue_step_is_the_last_work_step_before_the_exports():
    from fichero_server.recipes.assemble import STEP_ORDER

    assert STEP_ORDER[-3:] == ("describe-for-the-catalogue", "export", "publish")


def test_the_start_plan_runs_it_as_a_catalogue_card_with_the_steps_model():
    from fichero_server.recipes import start

    assert start.OTHER_CARDS["describe-for-the-catalogue"] == "catalogue"
    assert "describe-for-the-catalogue" not in start.BY_HAND_FIX


def test_a_spanish_folder_is_described_in_spanish(db, monkeypatch):
    """The language is the records' own (the workflow's "auto"), not a fixed English (## 1112)."""
    systems: list[str] = []

    async def fake(material, config, system=None, permissive_guardrails=False):
        systems.append(system)
        return "Título: Cartas."

    monkeypatch.setattr("fichero_server.llm.chat_with_fallback", fake)
    monkeypatch.setattr("fichero_server.llm.lang_detect.configured_primary_language", lambda: None)
    top = _node(db, "Caja", DocType.folder)
    page = _node(db, "p1", DocType.page, top,
                 "Muy señor mío: le escribo para decirle que la cosecha de trigo ha sido buena este año y que "
                 "los vecinos de la villa han pagado sus deudas al señor de la casa en la fecha acordada.")
    catalogue_step.describe_folders(db, [page], CONFIG, run_id=None)
    assert "Spanish" in systems[0]
    assert catalogue_step._latest(db, top).data["language"] == "Spanish"


def test_the_model_is_told_to_describe_only_and_a_banned_word_is_flagged(db, monkeypatch):
    systems: list[str] = []

    async def fake(material, config, system=None, permissive_guardrails=False):
        systems.append(system)
        return "Scope and content: The letters reveals a harvest."

    monkeypatch.setattr("fichero_server.llm.chat_with_fallback", fake)
    _top, box, pages = _tree(db)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    assert "NO ANALYSIS" in systems[0] and "500 words" in systems[0] and "reveals" in systems[0]
    assert catalogue_step._latest(db, box).data["flags"]  # the banned word stands but is flagged, never silent


def test_a_generative_text_model_is_a_card_for_the_catalogue_job():
    """`describe-for-the-catalogue` had no card, so Start said "no model" whatever the Mac or the keys (e2e finding)."""
    from fichero_server.recipes.discovery import TEXT_MODEL_JOBS, _describes_folders
    from fichero_server.recipes.cards import seed_cards

    assert "describe-for-the-catalogue" in TEXT_MODEL_JOBS
    text = [c for c in seed_cards() if {"split-into-entries", "find-statements"} <= c.jobs and not c.jobs & {"read-a-line", "read-a-page"}]
    assert all("describe-for-the-catalogue" in _describes_folders(c).jobs for c in text)
    spacy = [c for c in seed_cards() if c.id.startswith("spacy:")]
    assert spacy and not any("describe-for-the-catalogue" in _describes_folders(c).jobs for c in spacy)
