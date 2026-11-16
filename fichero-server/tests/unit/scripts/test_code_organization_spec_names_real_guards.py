"""spec: code-organization — every guard the spec says EXISTS does, and every guard it says is still to write does not.

The spec's enforcement map (`docs/contributor_manual/specs/harness/code-organization.md`) is the contract between the
rules and the gate: an [OK] row names a `scripts/check_*.py` that must be on disk, a "(to write)" guard must not already
be there under that name (else the spec is stale and the row should flip). Stdlib only; reads the spec and the tree.
"""
from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[4]
SPEC = REPO / "docs/contributor_manual/specs/harness/code-organization.md"


def _spec() -> str:
    return SPEC.read_text(encoding="utf-8")


def test_every_existing_guard_the_spec_cites_is_on_disk():
    cited = set(re.findall(r"`?(scripts/check_[a-z_]+\.py)`?", _spec()))
    assert cited, "the spec cites no guard"
    missing = sorted(p for p in cited if not (REPO / p).is_file())
    assert not missing, f"the spec names guards that do not exist: {missing}"


def test_every_guard_the_spec_says_is_to_write_is_not_already_there():
    # the guard name right after "(to write)": a new MODE in an existing guard ("(to write): the mirror check in `check_x`") is not a new file
    to_write = set(re.findall(r"\(to write\):?\s*(?:guard )?`(check_[a-z_]+)`", _spec()))
    to_write |= set(re.findall(r"\[GAP\] `(check_[a-z_]+)", _spec()))
    assert to_write, "the spec names no guard to write"
    present = sorted(g for g in to_write if (REPO / "scripts" / f"{g}.py").is_file())
    assert not present, f"the spec says these are still to write, but they exist (flip the row): {present}"


def test_every_non_ok_behaviour_sits_in_exactly_one_build_order_step():
    text = _spec()
    bullets = re.findall(r"^- `(code-org\.[\w.-]+)` \[(OK|PARTIAL|GAP)\]", text, re.M)
    build = text[text.index("## Build order"):text.index("## Test matrix")]
    steps = re.findall(r"^- Behaviours: (.+)$", build, re.M)
    placed = [b for line in steps for b in re.findall(r"`(code-org\.[\w.-]+)`", line)]
    for bid, tag in bullets:
        if tag != "OK":
            assert placed.count(bid) == 1, f"{bid} [{tag}] is in {placed.count(bid)} steps"
