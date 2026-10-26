"""spec: dev-workflows

Pins the shape of the dev-workflows spec so it cannot rot while its build order is worked: every behaviour
the spec defines is placed in exactly one build-order step, every behaviour has a row in the Behaviour tests
table, and the table names no behaviour the spec does not define.
"""
import re
from pathlib import Path

SPEC = Path(__file__).parents[4] / "docs/contributor_manual/specs/harness/dev-workflows.md"
ID = r"dev-workflows\.[a-z0-9.-]*[a-z0-9]"


def _section(text: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\b.*?(?=^## |\Z)", text, re.S | re.M)
    assert m, f"section {title!r} missing"
    return m.group(0)


def _spec():
    text = SPEC.read_text()
    defined = set(re.findall(rf"^- `({ID})`", _section(text, "Behaviours"), re.M))
    steps = re.findall(rf"^- Behaviours: (.*)$", _section(text, "Build order"), re.M)
    placed = [i for line in steps for i in re.findall(rf"`({ID})`", line)]
    rows = set(re.findall(rf"^\| `?({ID})`? \|", _section(text, "Behaviour tests"), re.M))
    return defined, placed, rows


def test_every_behaviour_is_in_exactly_one_build_order_step():
    defined, placed, _ = _spec()
    assert defined, "no behaviours found"
    assert len(placed) == len(set(placed)), "a behaviour is placed in two steps"
    assert set(placed) == defined


def test_behaviour_tests_table_matches_the_behaviours():
    defined, _, rows = _spec()
    assert rows == defined
