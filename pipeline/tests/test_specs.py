"""pipeline.build-order-shape (spec harness/deterministic-conductor.md, #6116).

Pipeline-side pin of scripts/check_spec_build_order_shape.py: it parses a spec's
`## Build order` section into stages and steps (behaviours, tests, depends-on,
size) and FAILS an APPROVED spec when a non-[OK] behaviour sits in no step.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
_SPEC = importlib.util.spec_from_file_location("check_spec_build_order_shape", SCRIPTS / "check_spec_build_order_shape.py")
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

PARSE_FIXTURE = """# Fixture spec

> Design-led. **Status: APPROVED**

## Behaviours

- `fixture.parse.one` [OK] — fine.
- `fixture.parse.two` [MISSING] — needs a step.

## Build order

### Stage 0 — the small one

#### Step 0.1 — first (#6117)
- Behaviours: `fixture.parse.one`
- Tests: pipeline/tests/test_a.py, pipeline/tests/test_b.py
- Size: S

#### Step 0.2 — second
- Behaviours: `fixture.parse.two`
- Tests: pipeline/tests/test_c.py
- Depends on: 0.1
- Size: M
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


def test_build_order_parses():
    stages, steps = _mod.parse_build_order(PARSE_FIXTURE)
    assert [(s.number, s.title) for s in stages] == [("0", "the small one")]
    assert [s.step_id for s in steps] == ["0.1", "0.2"]
    first, second = steps
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


def test_build_order_guard_fails_on_orphan_behaviour(tmp_path, monkeypatch):
    specs = tmp_path / "specs"
    p = specs / "fixture.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(ORPHAN_FIXTURE, encoding="utf-8")
    monkeypatch.setattr(_mod, "SPECS_DIR", specs)
    assert _mod.main() == 1