"""Unit tests for scripts/check_spec_build_order_shape.py.

Proves the build order shape (`pipeline.build-order-shape`): stages, steps, behaviours,
tests, dependencies, and size constraints are validated. APPROVED specs fail on violations;
DRAFT specs warn only.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_spec_build_order_shape.py"
)
_SPEC = importlib.util.spec_from_file_location("check_spec_build_order_shape", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

VALID_BUILD_ORDER = """# Test Spec

**Status: APPROVED**

## Build order

### Stage 0 — first stage

#### Step 0.1 — first step
- Behaviours: `test.one`, `test.two`
- Tests: test/one.py, test/two.py
- Size: M

#### Step 0.2 — second step (#123)
- Behaviours: `test.three`
- Tests: test/three.py
- Depends on: 0.1
- Size: S

## Behaviors

- `test.one` — [OK] description
- `test.two` — [MISSING] description
- `test.three` — [MISSING] description
"""

ORPHAN_BEHAVIOUR = """# Test Spec

**Status: APPROVED**

## Build order

#### Step 0.1 — only step
- Behaviours: `test.one`
- Tests: test/one.py
- Size: S

## Behaviors

- `test.one` — [MISSING] in build order
- `test.orphan` — [MISSING] not in build order
"""

FORWARD_DEPENDENCY = """# Test Spec

**Status: APPROVED**

## Build order

#### Step 0.1 — first step
- Behaviours: `test.one`
- Tests: test/one.py
- Depends on: 0.2
- Size: S

#### Step 0.2 — second step
- Behaviours: `test.two`
- Tests: test/two.py
- Size: S

## Behaviors

- `test.one` — [MISSING] one
- `test.two` — [MISSING] two
"""

SELF_DEPENDENCY = """# Test Spec

**Status: APPROVED**

## Build order

#### Step 0.1 — step
- Behaviours: `test.one`
- Tests: test/one.py
- Depends on: 0.1
- Size: S

## Behaviors

- `test.one` — [MISSING] one
"""

SIZE_L = """# Test Spec

**Status: APPROVED**

## Build order

#### Step 0.1 — step
- Behaviours: `test.one`
- Tests: test/one.py
- Size: L

## Behaviors

- `test.one` — [MISSING] one
"""

TOO_MANY_BEHAVIOURS = """# Test Spec

**Status: APPROVED**

## Build order

#### Step 0.1 — step
- Behaviours: `test.one`, `test.two`, `test.three`, `test.four`, `test.five`, `test.six`
- Tests: test/one.py
- Size: M

## Behaviors

- `test.one` — [MISSING] one
- `test.two` — [MISSING] two
- `test.three` — [MISSING] three
- `test.four` — [MISSING] four
- `test.five` — [MISSING] five
- `test.six` — [MISSING] six
"""

MISSING_BEHAVIOURS = """# Test Spec

**Status: APPROVED**

## Build order

#### Step 0.1 — step
- Tests: test/one.py
- Size: S

## Behaviors
"""

MISSING_TESTS = """# Test Spec

**Status: APPROVED**

## Build order

#### Step 0.1 — step
- Behaviours: `test.one`
- Size: S

## Behaviors

- `test.one` — [MISSING] one
"""

DRAFT_WITH_ERRORS = """# Test Spec

**Status: DRAFT**

## Build order

#### Step 0.1 — step
- Behaviours: `test.one`
- Tests: test/one.py
- Depends on: 0.2
- Size: L

#### Step 0.2 — second
- Tests: test/two.py
- Size: S

## Behaviors

- `test.one` — [MISSING] one
- `test.orphan` — [MISSING] not in build order
"""

MULTIPLE_STAGES = """# Test Spec

**Status: APPROVED**

## Build order

### Stage 0 — first

#### Step 0.1 — first
- Behaviours: `test.one`
- Tests: test/one.py
- Size: S

### Stage 1 — second

#### Step 1.1 — second
- Behaviours: `test.two`
- Tests: test/two.py
- Depends on: 0.1
- Size: S

## Behaviors

- `test.one` — [MISSING] one
- `test.two` — [MISSING] two
"""

DUPLICATE_BEHAVIOUR = """# Test Spec

**Status: APPROVED**

## Build order

#### Step 0.1 — first
- Behaviours: `test.one`
- Tests: test/one.py
- Size: S

#### Step 0.2 — second
- Behaviours: `test.one`
- Tests: test/two.py
- Size: S

## Behaviors

- `test.one` — [MISSING] appears twice
"""


def _seed(tmp_path: Path, body: str, rel: str = "test/example.md") -> Path:
    specs_root = tmp_path / "docs" / "contributor_manual" / "specs"
    p = specs_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return specs_root


def _run(tmp_path: Path, body: str, monkeypatch, rel: str = "test/example.md") -> int:
    specs_dir = _seed(tmp_path, body, rel)
    monkeypatch.setattr(_mod, "SPECS_DIR", specs_dir)
    return _mod.main()


def test_valid_build_order_passes(tmp_path, monkeypatch):
    assert _run(tmp_path, VALID_BUILD_ORDER, monkeypatch) == 0


def test_orphan_behaviour_fails_approved_spec(tmp_path, monkeypatch):
    assert _run(tmp_path, ORPHAN_BEHAVIOUR, monkeypatch) == 1


def test_forward_dependency_fails(tmp_path, monkeypatch):
    assert _run(tmp_path, FORWARD_DEPENDENCY, monkeypatch) == 1


def test_self_dependency_fails(tmp_path, monkeypatch):
    assert _run(tmp_path, SELF_DEPENDENCY, monkeypatch) == 1


def test_size_l_fails(tmp_path, monkeypatch):
    assert _run(tmp_path, SIZE_L, monkeypatch) == 1


def test_too_many_behaviours_fails(tmp_path, monkeypatch):
    assert _run(tmp_path, TOO_MANY_BEHAVIOURS, monkeypatch) == 1


def test_missing_behaviours_fails(tmp_path, monkeypatch):
    assert _run(tmp_path, MISSING_BEHAVIOURS, monkeypatch) == 1


def test_missing_tests_fails(tmp_path, monkeypatch):
    assert _run(tmp_path, MISSING_TESTS, monkeypatch) == 1


def test_draft_with_errors_passes_with_warnings(tmp_path, monkeypatch):
    # DRAFT specs warn but don't fail
    assert _run(tmp_path, DRAFT_WITH_ERRORS, monkeypatch) == 0


def test_multiple_stages_pass(tmp_path, monkeypatch):
    assert _run(tmp_path, MULTIPLE_STAGES, monkeypatch) == 0


def test_duplicate_behaviour_fails(tmp_path, monkeypatch):
    assert _run(tmp_path, DUPLICATE_BEHAVIOUR, monkeypatch) == 1


def test_empty_spec_dir_exits_2(tmp_path, monkeypatch):
    empty = tmp_path / "empty_specs"
    empty.mkdir()
    monkeypatch.setattr(_mod, "SPECS_DIR", empty / "does_not_exist")
    assert _mod.main() == 2


def test_parse_build_order_extracts_stages_and_steps():
    """Test the parse function directly."""
    parsed = _mod._parse_build_order(MULTIPLE_STAGES)
    assert parsed is not None
    assert len(parsed["stages"]) == 2
    assert parsed["stages"][0]["number"] == 0
    assert parsed["stages"][0]["title"] == "first"
    assert len(parsed["stages"][0]["steps"]) == 1
    assert parsed["stages"][0]["steps"][0]["number"] == "0.1"
    assert parsed["stages"][0]["steps"][0]["behaviours"] == ["test.one"]
    assert parsed["stages"][0]["steps"][0]["tests"] == ["test/one.py"]
    assert parsed["stages"][0]["steps"][0]["size"] == "S"


def test_parse_build_order_extracts_dependencies():
    """Test that dependencies are parsed correctly."""
    parsed = _mod._parse_build_order(MULTIPLE_STAGES)
    assert parsed is not None
    step_1_1 = parsed["stages"][1]["steps"][0]
    assert step_1_1["depends_on"] == ["0.1"]


def test_parse_build_order_extracts_issue_number():
    """Test that issue numbers are extracted."""
    parsed = _mod._parse_build_order(VALID_BUILD_ORDER)
    assert parsed is not None
    step_0_2 = parsed["stages"][0]["steps"][1]
    assert step_0_2["issue"] == "123"


def test_parse_build_order_returns_none_without_section():
    """Test that specs without build order return None."""
    spec_without_build_order = """# Test Spec

**Status: APPROVED**

## Some other section

Content here.
"""
    parsed = _mod._parse_build_order(spec_without_build_order)
    assert parsed is None


def test_get_all_behaviours_extracts_tags():
    """Test that behaviour tags are extracted correctly."""
    behaviours = _mod._get_all_behaviours_in_spec(VALID_BUILD_ORDER)
    assert "test.one" in behaviours
    assert behaviours["test.one"] == "OK"
    assert "test.two" in behaviours
    assert behaviours["test.two"] == "MISSING"


def test_self_test_passes():
    """The guard's own self-test should pass."""
    assert _mod._self_test() == 0


PAREN_TITLE_AND_PROSE_ID = """# Test Spec

**Status: APPROVED**

- `test.one` [MISSING] — a behaviour; `ci.yml` in prose is a file name, not a behaviour.

## Build order

#### Step 0.1 — the guard (a note in parentheses) (#77)
- Behaviours: `test.one`
- Tests: test/one.py
- Size: S

#### Step 0.2 — next
- Behaviours: `test.one`
- Tests: test/two.py
- Depends on: 0.1
- Size: S
"""


def test_step_title_may_contain_parentheses_and_still_carry_an_issue():
    parsed = _mod._parse_build_order(PAREN_TITLE_AND_PROSE_ID)
    assert parsed is not None
    steps = parsed["stages"][0]["steps"]
    assert [s["number"] for s in steps] == ["0.1", "0.2"]
    assert steps[0]["title"] == "the guard (a note in parentheses)"
    assert steps[0]["issue"] == "77"


def test_only_behaviour_lines_define_behaviours_not_ids_in_prose():
    behaviours = _mod._get_all_behaviours_in_spec(PAREN_TITLE_AND_PROSE_ID)
    assert behaviours == {"test.one": "MISSING"}
