"""spec: source-model

Pins the shape of the source-model foundation spec so it cannot rot while its build order is worked: every behaviour the
file defines (under "Behaviors") is placed in exactly one build-order step, every behaviour has a row in the Behaviour tests
table, the table names no behaviour the file does not define, and every test path the file names exists. The other behaviour
ids of the source model live in the slice files, not here.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parents[4]
SPEC = ROOT / "docs/contributor_manual/specs/source/source-model.md"
ID = r"source\.[a-z0-9.-]*[a-z0-9]"


def _section(text: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\b.*?(?=^## |\Z)", text, re.S | re.M)
    assert m, f"section {title!r} missing"
    return m.group(0)


def _spec():
    text = SPEC.read_text()
    defined = set(re.findall(rf"^- `({ID})` — \*\*\[", _section(text, "Behaviors"), re.M))
    order = _section(text, "Build order")
    placed = [i for line in re.findall(r"^- Behaviours: (.*)$", order, re.M) for i in re.findall(rf"`({ID})`", line)]
    table = _section(text, "Behaviour tests")
    rows = set(re.findall(rf"^\| `({ID})` \|", table, re.M))
    paths = set(re.findall(r"(?:fichero-server|fichero)/[\w./-]+\.(?:py|swift)\b", order + table))
    return defined, placed, rows, paths


def test_every_behaviour_is_in_exactly_one_build_order_step():
    defined, placed, _, _ = _spec()
    assert defined, "no behaviours found"
    assert len(placed) == len(set(placed)), "a behaviour is placed in two steps"
    assert set(placed) == defined


def test_behaviour_tests_table_matches_the_behaviours():
    defined, _, rows, _ = _spec()
    assert rows == defined


def test_every_named_test_file_exists():
    *_, paths = _spec()
    assert paths and not [p for p in paths if not (ROOT / p).exists()]
