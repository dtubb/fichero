"""#6128 (`source.job.review-is-built-from-the-project-and-a-profile`): the review is not titled for a role, and what it
looks for comes from the project's script, language and date, with the guidance the per-script Transcribe presets carry."""
from __future__ import annotations

import json

import pytest

from fichero_server.recipes.review_profiles import RENAMED, choose, lens_ids, review_prompt
from fichero_server.workflows.default_workflows import _PRESETS_DIR

BASE = {"purposes": ["transcribe"], "scripts": ["Latn"], "materials": ["handwriting"]}
SPANISH_1590S = {**BASE, "languages": ["es"], "period": "1590s"}
ENGLISH_1620 = {**BASE, "languages": ["en"], "period": "1620"}
SPANISH_1790 = {**BASE, "languages": ["es"], "period": "1790"}
LATIN_1300 = {**BASE, "languages": ["la"], "period": "1300"}


def test_no_user_facing_string_says_paleographer_review():
    """The preset's display name, its labels and descriptions, and what refers to it by name."""
    for path in sorted(_PRESETS_DIR.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert "Paleographer Review" not in text, path.name
    review = json.loads((_PRESETS_DIR / "transcribe_paleography_review.json").read_text(encoding="utf-8"))
    assert review["name"] == RENAMED["Paleographer Review"] == "Review the Reading"
    pipeline = json.loads((_PRESETS_DIR / "transcribe_review_pipeline.json").read_text(encoding="utf-8"))
    refs = [n["config"].get("workflow_ref") for n in pipeline["nodes"] if n.get("tool") == "sub_workflow"]
    assert "Review the Reading" in refs


@pytest.mark.parametrize("lens", lens_ids())
def test_a_spanish_1590s_project_is_sent_the_s_xvi_xvii_guidance(lens):
    prompt, said = review_prompt(lens, SPANISH_1590S)
    assert "colonial" in said and "ç/c/z" in prompt


@pytest.mark.parametrize("lens", lens_ids())
def test_an_english_1620_secretary_hand_project_is_sent_the_secretary_guidance(lens):
    prompt, said = review_prompt(lens, ENGLISH_1620)
    assert "secretary" in said
    assert "ç/c/z" not in prompt and "carta de poder" not in prompt
    assert {"abbreviations": "ye = th[e]", "orthography": "secretary c/t/e", "names-and-dates": "Collect every"}[lens] in prompt


def test_a_spanish_1790_project_is_sent_the_s_xviii_xix_guidance_not_the_colonial_one():
    prompt, said = review_prompt("abbreviations", SPANISH_1790)
    assert "XVIII" in said and "Ex.mo" in prompt


def test_a_latin_project_is_sent_the_latin_guidance():
    prompt, said = review_prompt("abbreviations", LATIN_1300)
    assert "Latin" in said and "Tironian" in prompt


def test_the_profile_is_chosen_by_script_language_and_date_only():
    assert choose({**SPANISH_1590S, "period": "1590"})[0].id == "es-colonial"
    assert choose({**ENGLISH_1620, "period": "1950"})[0].id == "generic"


def test_a_page_reviewed_under_the_old_name_still_counts_reviewed_6128(db):
    """A preset's workflow id is uuid5(name): the rename made a new id, so a review run before it must still count as done
    for a step with no model of its own (`recipes.done._has_review` / `_by_the_step`), not be reviewed again."""
    from fichero_server.models import Artifact, DocType, Document
    from fichero_server.recipes.done import REVIEWED, _has_review
    from fichero_server.workflows.default_workflows import preset_workflow_id

    page = Document(name="p", doc_type=DocType.page)
    db.save(page)
    db.save(Artifact(document_id=page.id, artifact_type=REVIEWED, content="reviewed",
                     workflow_id=preset_workflow_id("Paleographer Review")))
    new_id = preset_workflow_id("Review the Reading")
    assert new_id != preset_workflow_id("Paleographer Review")
    assert _has_review(db, page.id, None, new_id), "reviewed under the old id counts for the new one"
    other = preset_workflow_id("Some Other Preset")
    assert not _has_review(db, page.id, None, other), "another workflow's review is still not this step's"
