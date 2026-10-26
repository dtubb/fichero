"""spec: segments-and-geometry
spec: readings-and-apparatus
spec: segment-editor

The approved source-model slice files

Pins the shape of the source-model slice files approved on 2026-10-26 so they cannot rot while their behaviours are worked:
each header says APPROVED in the bold form within its first 20 lines, each declares a real `Manual:` pointer, every behaviour
bullet carries a state tag and an issue, and, once a file has a `## Build order`, every behaviour that owes a build is in
exactly one step (the plan the runner proposes is checked the same way by scripts/check_spec_build_order_shape.py).
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[4]
DIR = ROOT / "docs/contributor_manual/specs/source"
SLICES = ["segments-and-geometry", "readings-and-apparatus", "segment-editor"]
BEHAVIOUR = re.compile(r"^- `([a-z][a-z0-9+_-]*(?:\.[a-z0-9+_-]+)+)` (?:— )?\*{0,2}\[(\w+)[^\]]*\]\*{0,2}(.*)", re.M)


def _text(name):
    return (DIR / f"{name}.md").read_text()


@pytest.mark.parametrize("name", SLICES)
def test_header_is_approved_in_the_bold_form_with_a_real_manual_pointer(name):
    text = _text(name)
    assert any("**Status: APPROVED" in line for line in text.splitlines()[:20])
    pointer = re.search(r"^> Manual: (\S+)", text, re.M)
    assert pointer and not pointer.group(1).upper().startswith("TBD")
    assert (ROOT / pointer.group(1)).exists(), pointer.group(1)


@pytest.mark.parametrize("name", SLICES)
def test_every_owed_behaviour_cites_an_issue(name):
    owed = [(i, rest) for i, tag, rest in BEHAVIOUR.findall(_text(name)) if tag in {"MISSING", "GAP", "BROKEN", "PARTIAL"}]
    assert owed
    assert not [i for i, rest in owed if "#" not in rest and "→ #" not in rest], "an owed behaviour with no issue"


@pytest.mark.parametrize("name", SLICES)
def test_a_build_order_places_every_owed_behaviour_once(name):
    text = _text(name)
    m = re.search(r"^## Build order\b.*?(?=^## |\Z)", text, re.S | re.M)
    if not m:
        pytest.skip("no build order yet: the runner's `plan` proposes one")
    placed = [i for line in re.findall(r"^- Behaviours: (.*)$", m.group(0), re.M) for i in re.findall(r"`([^`]+)`", line)]
    owed = {i for i, tag, _ in BEHAVIOUR.findall(text) if tag in {"MISSING", "GAP", "BROKEN", "PARTIAL"}}
    assert len(placed) == len(set(placed)) and owed == set(placed)


def test_the_three_easy_editing_behaviours_exist():
    ids = {i for i, *_ in BEHAVIOUR.findall(_text("segment-editor"))}
    assert {"source.editor.preview-crud", "source.editor.join-is-easy", "source.editor.make-new-in-the-preview"} <= ids
