"""An `engine.silent.*` bullet tagged [OK] names tests that exist (every `tests/...py` path and `::name` in it) and a
fixture that exists or `Fixture: none` (`engine.silent.every-bullet-names-its-proof`).

[GAP]/[PARTIAL] bullets may name a test not yet written: that is the work item, printed by `-s`, never a failure.
"""

from __future__ import annotations

import re
from pathlib import Path

SERVER = Path(__file__).resolve().parents[3]
SPEC = SERVER.parent / "docs/contributor_manual/specs/source/engine-silent-failures.md"
BULLET = re.compile(r"^- `(engine\.silent\.[a-z0-9.-]+)` — \*\*\[(\w+)\]\*\*(.*)$")
TEST = re.compile(r"`(tests/[^`:]+\.py)(?:::(\w+))?`")  # every test the bullet names, not only the first
FIXTURE = re.compile(r"Fixture: `(tests/[^`]+)`")
NO_FIXTURE = re.compile(r"Fixture: none\b")


def _bullets(lines: list[str] | None = None) -> list[tuple[str, str, str]]:
    lines = SPEC.read_text(encoding="utf-8").splitlines() if lines is None else lines
    return [m.groups() for m in map(BULLET.match, lines) if m]


def _problems(bullets: list[tuple[str, str, str]]) -> list[str]:
    out = []
    for slug, tag, text in bullets:
        tests = TEST.findall(text)
        if tag == "OK" and not tests:
            out.append(f"{slug} is [OK] and names no `tests/...py`")
        if tag == "OK" and not (FIXTURE.search(text) or NO_FIXTURE.search(text)):
            out.append(f"{slug} is [OK] and names neither a `Fixture: tests/...` nor `Fixture: none`")
        for path, name in tests if tag == "OK" else []:
            if not (SERVER / path).is_file():
                out.append(f"{slug} is [OK] but its test {path} does not exist")
            elif name and f"def {name}" not in (SERVER / path).read_text(encoding="utf-8"):
                out.append(f"{slug} is [OK] but {path} has no test {name}")
        for path in FIXTURE.findall(text):
            if not (SERVER / path).exists():
                out.append(f"{slug} names a fixture that does not exist: {path}")
    return out


def test_the_spec_has_bullets():
    assert len(_bullets()) >= 20


def test_every_ok_bullet_names_a_test_and_fixture_that_exist():
    assert _problems(_bullets()) == []


def test_the_guard_fails_an_ok_bullet_with_a_missing_test_or_none():
    missing = _bullets(["- `engine.silent.x` — **[OK]** Test: `tests/unit/nope/test_nope.py`."])
    assert any("does not exist" in p for p in _problems(missing))
    none = _bullets(["- `engine.silent.y` — **[OK]** it works."])
    assert "names no" in _problems(none)[0]
    # a second test on the same bullet is checked too, and so is a fixture-less [OK] bullet
    two = _bullets(["- `engine.silent.w` — **[OK]** Test: `tests/unit/seams/test_engine_silent_spec_names_tests.py`; also"
                    " `tests/unit/nope/test_nope.py::test_x`. Fixture: none (in-process)."])
    assert any("test_nope.py does not exist" in p for p in _problems(two))
    nofix = _bullets(["- `engine.silent.v` — **[OK]** Test: `tests/unit/seams/test_engine_silent_spec_names_tests.py`."])
    assert "neither a `Fixture" in _problems(nofix)[0]
    bad_name = _bullets(["- `engine.silent.u` — **[OK]** Test: `tests/unit/seams/test_engine_silent_spec_names_tests.py::test_nope`."
                         " Fixture: none."])
    assert "has no test test_nope" in _problems(bad_name)[0]
    assert _problems(_bullets(["- `engine.silent.z` — **[GAP]** Test: `tests/unit/nope/test_nope.py`."])) == []
