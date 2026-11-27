"""The blind-hands learning curve (#6967, `hands.bench.learning-curve-at-five-points`). Offline: no engine, no model."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location("blind_hands_curve", REPO_ROOT / "scripts" / "blind_hands" / "curve.py")
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)

LINES = [f"line-{i}" for i in range(500)]


def test_subsets_are_nested_and_drawn_by_the_seed():
    s = c.nested_subsets(LINES, seed=7)
    assert [len(s[p]) for p in c.POINTS] == [0, 50, 100, 200, 400]
    for small, big in zip(c.POINTS, c.POINTS[1:]):
        assert s[big][:small] == s[small]
    assert c.nested_subsets(LINES, seed=7) == s
    assert c.nested_subsets(LINES, seed=8)[400] != s[400]


def test_two_configurations_learn_from_the_same_lines():
    seen = {"a": [], "b": []}
    for name in seen:
        c.curve(LINES, 3, lambda lines, name=name: seen[name].append(list(lines)) or {})
    assert seen["a"] == seen["b"]


def test_a_short_pool_gives_not_measured_never_a_number():
    r = c.curve(LINES[:120], 1, lambda lines: {"page_error": 0.5})
    assert r["points"][0] == {"page_error": 0.5}
    assert r["points"][100] == {"page_error": 0.5}
    assert r["points"][200] == "not measured: 120 lines in the pool"
    assert r["points"][400] == "not measured: 120 lines in the pool"


def test_a_fake_readers_known_errors_give_the_known_curve():
    known = {0: 0.40, 50: 0.30, 100: 0.20, 200: 0.10, 400: 0.05}

    def fake(lines):
        return {"page_error": known[len(lines)], "given_lines_error": known[len(lines)] / 2}

    r = c.curve(LINES, 11, fake)
    assert r["seed"] == 11
    assert {p: v["page_error"] for p, v in r["points"].items()} == known
    assert r["points"][400]["given_lines_error"] == 0.025
