"""The review is built from the project and a profile (`source.job.review-is-built-from-the-project-and-a-profile`, #5723).

Spec: an English secretary-hand project is never sent "carta de poder" or "ç/c/z"; a Spanish colonial one is; a project
with no profile for its language and period is told so and gets the generic review, never the Spanish one. The profiles
are data files (`recipes/seed/review-profiles/`): the code names no language, so the matrix below (Spanish colonial,
German Kurrent, Aramaic right to left, Chinese in columns) is chosen to differ in script, direction and spacing.
WHY: the Paleographer Review preset's three prompts were Spanish colonial whatever the project said.
"""
from __future__ import annotations

import pytest
from fichero_server.recipes.review_profiles import (
    GENERIC,
    choose,
    lens_ids,
    profiles,
    review_prompt,
)

ENGLISH = {"purposes": ["transcribe"], "languages": ["en"], "scripts": ["Latn"], "materials": ["handwriting"],
           "period": "1600"}
SPANISH = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
           "period": "1650"}
SPANISH_MODERN = {**SPANISH, "period": "1950"}
MATRIX = [  # (answers, the profile it must get, a word of its direction the prompt must carry)
    (SPANISH, "es-colonial", "left to right"),
    ({"purposes": ["transcribe"], "languages": ["de"], "scripts": ["Latn"], "materials": ["handwriting"],
      "period": "1850"}, "de-kurrent", "left to right"),
    ({"purposes": ["transcribe"], "languages": ["arc"], "scripts": ["Syrc"], "materials": ["handwriting"],
      "directions": {"Syrc": "rtl"}}, "aramaic", "right to left"),
    ({"purposes": ["transcribe"], "languages": ["zh"], "scripts": ["Hant"], "materials": ["handwriting"],
      "directions": {"Hant": "ttb"}}, "zh", "columns running top to bottom"),
]


def test_the_shipped_profiles_are_found_and_each_has_every_lens():
    """A floor under the rest, so they cannot pass by finding nothing; every profile has the generic one's lenses."""
    assert {"generic", "es-colonial", "de-kurrent", "aramaic", "zh", "en-secretary", "latin", "es-moderna"} <= set(profiles())
    assert len(lens_ids()) == 3
    assert all(set(p.lenses) == set(lens_ids()) for p in profiles().values())


@pytest.mark.parametrize("lens", lens_ids())
def test_an_english_secretary_hand_project_is_never_sent_the_spanish_review(lens):
    prompt, said = review_prompt(lens, ENGLISH)
    assert "carta de poder" not in prompt and "ç/c/z" not in prompt and "mer[ce]d" not in prompt
    assert "secretary" in said, "English handwriting of 1600 has its own profile since #6128"


@pytest.mark.parametrize("lens", lens_ids())
def test_a_spanish_colonial_project_is_sent_the_spanish_colonial_review(lens):
    prompt, said = review_prompt(lens, SPANISH)
    assert "ç/c/z" in prompt and "language: Spanish" in prompt
    assert "colonial" in said


def test_spanish_outside_the_profiles_period_gets_the_generic_review_and_is_told_so():
    """A profile that states a period that misses the project's is refused, as a reader card is (#5714)."""
    profile, said = choose(SPANISH_MODERN)
    assert profile.id == GENERIC and "Spanish" in said and "1950" in said
    assert "ç/c/z" not in review_prompt(lens_ids()[0], SPANISH_MODERN)[0]


def test_a_project_that_states_nothing_gets_the_generic_review_and_is_told_so():
    for answers in (None, {}, {"purposes": ["transcribe"]}):
        profile, said = choose(answers)
        assert profile.id == GENERIC and "no language" in said


@pytest.mark.parametrize("answers,profile_id,direction", MATRIX, ids=[m[1] for m in MATRIX])
def test_each_script_gets_its_profile_and_its_direction_is_said(answers, profile_id, direction):
    """Nothing assumes spaces, direction or an alphabet (#5728): the profile and the direction come from data."""
    profile, _said = choose(answers)
    assert profile.id == profile_id
    prompt, _ = review_prompt("orthography", answers)
    assert direction in prompt and profile.context in prompt


def test_a_lens_no_profile_has_is_refused_naming_the_lenses():
    with pytest.raises(ValueError, match="abbreviations"):
        review_prompt("no-such-lens", SPANISH)


def test_no_shipped_review_carries_the_spanish_colonial_prompt_5723():
    """Every shipped preset's review node is built from the project and its profile: none carries the Spanish colonial
    genres and expansions as its own prompt (Transcribe (Auto-Detect) did, for every project it routed to review).
    WHY: an English or German project sent "carta de poder" and "mer[ce]d" is reviewed against the wrong hand."""
    import json
    from pathlib import Path

    import fichero_server

    presets = Path(fichero_server.__file__).parent / "resources" / "default_workflows"
    carrying = [f"{path.name}:{node['id']}" for path in sorted(presets.glob("*.json"))
                for node in json.loads(path.read_text()).get("nodes", []) if node.get("tool") == "transcribe_review"
                and any(mark in (node.get("config") or {}).get("prompt", "") for mark in ("carta de poder", "mer[ce]d"))]
    assert carrying == []


def test_one_pass_through_several_lenses_is_given_each_lens_5723():
    """A node's `lens` may name several, comma-separated (Auto-Detect reviews once through all three): the prompt holds
    each lens's text, and an unknown one in the list is refused."""
    prompt = review_prompt("abbreviations,orthography,names-and-dates", None)[0]
    assert all(lens["text"].strip().splitlines()[0] in prompt for lens in profiles()["generic"].lenses.values())
    with pytest.raises(ValueError, match="no review lens 'spelling'"):
        review_prompt("abbreviations,spelling", None)
