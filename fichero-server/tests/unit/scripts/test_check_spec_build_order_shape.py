"""Unit tests for scripts/check_spec_build_order_shape.py.

Pins pipeline.build-order-shape (#6116): the parser reads stages, steps, behaviours,
tests, depends-on and size out of a spec's `## Build order` section; an APPROVED spec
fails when a non-[OK] behaviour is in no step (or two), a step has no Behaviours or
no Tests, a step is Size L or lists more than five behaviours, or a Depends-on points
forward or at itself; a DRAFT spec with the same problems only warns (exit 0).
Runs OFFLINE — pure file-text parsing.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_spec_build_order_shape.py"
_SPEC = importlib.util.spec_from_file_location("check_spec_build_order_shape", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

PARSE_FIXTURE = """# Fixture spec

> Design-led. **Status: APPROVED 2026-10-25.**

## Behaviours

- `fixture.parse.one` [OK] — fine, exempt from coverage.
- `fixture.parse.two` [MISSING] (#6116) — needs a step.
- `fixture.parse.three` [GAP] — needs a step too.

## Build order

Intro prose before any stage.

### Stage 0 — the small one

#### Step 0.1 — the first step (#6117)
- Behaviours: `fixture.parse.one`
- Tests: pipeline/tests/test_a.py, pipeline/tests/test_b.py
- Size: S

#### Step 0.2 — the second step
- Behaviours: `fixture.parse.two`
- Tests: pipeline/tests/test_c.py
- Depends on: 0.1
- Size: M

### Stage 1 — more

#### Step 1.1 — the third
- Behaviours: `fixture.parse.three`
- Tests: pipeline/tests/test_d.py
- Size: S
"""

ORPHAN_FIXTURE = """# Fixture spec

> **Status: APPROVED**

## Behaviours

- `fixture.orphan.a` [MISSING] — in a step.
- `fixture.orphan.b` [MISSING] — in no step.

## Build order

#### Step 0.1 — only one
- Behaviours: `fixture.orphan.a`
- Tests: tests/a.py
- Size: S
"""

DOUBLE_FIXTURE = """# Fixture spec

> **Status: APPROVED**

## Behaviours

- `fixture.double.a` [MISSING] — in two steps.

## Build order

#### Step 0.1 — first
- Behaviours: `fixture.double.a`
- Tests: tests/a.py
- Size: S

#### Step 0.2 — second
- Behaviours: `fixture.double.a`
- Tests: tests/b.py
- Size: S
"""

FORWARD_AND_SELF_FIXTURE = """# Fixture spec

> **Status: APPROVED**

## Behaviours

- `fixture.fwd.a` [MISSING] — a.
- `fixture.fwd.b` [MISSING] — b.

## Build order

#### Step 0.1 — first
- Behaviours: `fixture.fwd.a`
- Tests: tests/a.py
- Depends on: 0.2
- Size: S

#### Step 0.2 — second
- Behaviours: `fixture.fwd.b`
- Tests: tests/b.py
- Depends on: 0.2
- Size: S
"""


def test_parse_build_order_reads_stages_steps_and_fields():
    stages, steps = _mod.parse_build_order(PARSE_FIXTURE)
    assert [(s.number, s.title) for s in stages] == [("0", "the small one"), ("1", "more")]
    assert [s.step_id for s in steps] == ["0.1", "0.2", "1.1"]
    first, second, third = steps
    assert first.title == "the first step"
    assert first.issue == "6117"
    assert first.behaviours == ["fixture.parse.one"]
    assert first.tests == ["pipeline/tests/test_a.py", "pipeline/tests/test_b.py"]
    assert first.depends_on == []
    assert first.size == "S"
    assert second.issue is None
    assert second.behaviours == ["fixture.parse.two"]
    assert second.tests == ["pipeline/tests/test_c.py"]
    assert second.depends_on == ["0.1"]
    assert second.size == "M"
    assert third.title == "the third"
    assert third.behaviours == ["fixture.parse.three"]
    assert third.tests == ["pipeline/tests/test_d.py"]
    assert third.size == "S"


def test_clean_approved_fixture_has_no_problems():
    approved, _, problems = _mod._check_spec(PARSE_FIXTURE)
    assert approved is True
    assert problems == []


def test_spec_without_build_order_is_skipped():
    approved, steps, problems = _mod._check_spec("# Plain spec\n\nNo build order here.\n")
    assert steps == []
    assert problems == []


def test_orphan_behaviour_fails():
    _, _, problems = _mod._check_spec(ORPHAN_FIXTURE)
    assert any("`fixture.orphan.b`" in p and "no step" in p for p in problems)


def test_behaviour_in_two_steps_fails():
    _, _, problems = _mod._check_spec(DOUBLE_FIXTURE)
    assert any("`fixture.double.a`" in p and "2 steps" in p for p in problems)


def test_forward_and_self_dependency_fail():
    _, _, problems = _mod._check_spec(FORWARD_AND_SELF_FIXTURE)
    assert any("Step 0.1 depends on later step 0.2" in p for p in problems)
    assert any("Step 0.2 depends on itself" in p for p in problems)


def _run(tmp_path: Path, body: str, monkeypatch) -> int:
    specs_root = tmp_path / "docs" / "contributor_manual" / "specs"
    p = specs_root / "harness" / "fixture.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    monkeypatch.setattr(_mod, "SPECS_DIR", specs_root)
    return _mod.main()


def test_draft_with_problems_warns_not_fails(tmp_path, monkeypatch):
    assert _run(tmp_path, ORPHAN_FIXTURE, monkeypatch) == 1
    draft = ORPHAN_FIXTURE.replace("**Status: APPROVED**", "**Status: DRAFT 2026-10-25.**")
    assert _run(tmp_path, draft, monkeypatch) == 0


def test_empty_spec_dir_exits_2(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "SPECS_DIR", tmp_path / "does_not_exist")
    assert _mod.main() == 2
