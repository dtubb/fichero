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
