"""spec: recipes-run

Pins the shape of the recipes-run spec (docs/contributor_manual/specs/source/recipes-run.md) so it cannot rot while its
build order is worked: every `recipes-run.*` behaviour still owed a build (tagged GAP, BROKEN or PARTIAL) is placed in
exactly one build-order step, a step places no behaviour the spec does not define, and the behaviours the owner's rulings
of 2026-10-26 created are defined and placed.
"""
import re
from pathlib import Path

SPEC = Path(__file__).parents[4] / "docs/contributor_manual/specs/source/recipes-run.md"
ID = r"recipes-run\.[a-z0-9.+_-]*[a-z0-9]"
RULING_IDS = {
    "recipes-run.restart.resumes-at-once-gently",
    "recipes-run.memory.gate-shown",
    "recipes-run.order.search-entities-once-at-the-end",
}


def _section(text: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\b.*?(?=^## |\Z)", text, re.S | re.M)
    assert m, f"section {title!r} missing"
    return m.group(0)


def _spec():
    text = SPEC.read_text()
    tagged = re.findall(rf"^\s*- `({ID})` — \*\*\[(\w+)\]", text, re.M)
    defined = {i for i, _ in tagged}
    owed = {i for i, tag in tagged if tag in {"MISSING", "GAP", "BROKEN", "PARTIAL"}}
    order = _section(text, "Build order")
    steps = re.findall(r"^- Behaviours: (.*)$", order, re.M)
    placed = [i for line in steps for i in re.findall(rf"`({ID})`", line)]
    return defined, owed, placed


def test_every_owed_behaviour_is_in_exactly_one_build_order_step():
    _, owed, placed = _spec()
    assert owed, "no behaviours found"
    assert len(placed) == len(set(placed)), "a behaviour is placed in two steps"
    assert owed <= set(placed), f"in no step: {sorted(owed - set(placed))}"


def test_no_step_places_an_undefined_behaviour():
    defined, _, placed = _spec()
    assert set(placed) <= defined, f"not defined: {sorted(set(placed) - defined)}"


def test_the_rulings_behaviours_are_defined_and_placed():
    _, owed, placed = _spec()
    assert RULING_IDS <= owed and RULING_IDS <= set(placed)


def test_the_spec_is_approved_under_its_own_milestone():
    head = SPEC.read_text()[:1500]
    assert re.search(r"Status:\s*APPROVED", head) and "Milestone: recipes-run" in head
