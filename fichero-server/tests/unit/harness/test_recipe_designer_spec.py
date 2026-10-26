"""spec: recipe-designer

Pins the shape of the recipe-designer spec so it cannot rot while its build order is worked: every `designer.*`
behaviour still owed a build (tagged MISSING, GAP, BROKEN or PARTIAL) is placed in exactly one build-order step, a step
places no behaviour the spec does not define, and the model-chooser behaviours of 2026-10-26 sit in Stage 16.
"""
import re
from pathlib import Path

SPEC = Path(__file__).parents[4] / "docs/contributor_manual/specs/source/recipe-designer.md"
ID = r"designer\.[a-z0-9.+_-]*[a-z0-9]"
MODEL_IDS = {
    "designer.model.every-model-step-chooses",
    "designer.model.chooser-is-one-component",
    "designer.model.one-resident-local-model",
    "designer.model.where-it-runs-is-part-of-the-choice",
}


def _section(text: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\b.*?(?=^## |\Z)", text, re.S | re.M)
    assert m, f"section {title!r} missing"
    return m.group(0)


def _spec():
    text = SPEC.read_text()
    tagged = re.findall(rf"^\s*- `({ID})` \[(\w+)", text, re.M)
    defined = {i for i, _ in tagged}
    owed = {i for i, tag in tagged if tag in {"MISSING", "GAP", "BROKEN", "PARTIAL"}}
    order = _section(text, "Build order")
    steps = re.findall(r"^- Behaviours: (.*)$", order, re.M)
    placed = [i for line in steps for i in re.findall(rf"`({ID})`", line)]
    stage16 = re.search(r"^### Stage 16\b.*", order, re.S | re.M)
    return defined, owed, placed, stage16.group(0) if stage16 else ""


def test_every_owed_behaviour_is_in_exactly_one_build_order_step():
    _, owed, placed, _ = _spec()
    assert owed, "no behaviours found"
    assert len(placed) == len(set(placed)), "a behaviour is placed in two steps"
    assert owed <= set(placed), f"in no step: {sorted(owed - set(placed))}"


def test_no_step_places_an_undefined_behaviour():
    defined, _, placed, _ = _spec()
    assert set(placed) <= defined, f"not defined: {sorted(set(placed) - defined)}"


def test_the_model_chooser_behaviours_are_defined_and_in_stage_16():
    defined, owed, placed, stage16 = _spec()
    assert MODEL_IDS <= owed
    assert MODEL_IDS == {i for i in re.findall(rf"`({ID})`", stage16)}


def test_the_metadata_language_behaviour_is_defined_and_placed():
    defined, owed, placed, _ = _spec()
    assert "designer.onboarding.metadata-language" in owed and "designer.onboarding.metadata-language" in placed
