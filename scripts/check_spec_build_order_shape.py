#!/usr/bin/env python3
"""Check build order shape in specs: stages, steps, behaviours, tests, dependencies, size.

A spec's build order section has a fixed shape (`pipeline.build-order-shape`):
  ## Build order
  ### Stage N — title
  #### Step N.M — title (#NNNN)
  - Behaviours: `id.one`, `id.two`
  - Tests: path/one.py, path/two.py
  - Depends on: N.M, N.K  (optional, default: previous step in stage)
  - Size: S | M | L

For an APPROVED spec, the guard FAILS when:
- A behaviour whose tag is not [OK] appears in no step or in multiple steps
- A step has no Behaviours or no Tests
- A step is Size L or lists more than 5 behaviours
- Depends-on points at a later step or itself

For a DRAFT spec, the same problems are reported as warnings (exit 0).
"""

from __future__ import annotations

import pathlib
import re
import sys
from _scan_files import scan_rglob

SPECS_DIR = pathlib.Path("docs/contributor_manual/specs")

# Patterns for parsing build order
STAGE_RE = re.compile(r"^###\s+Stage\s+(\d+)\s+—\s+(.+)$")
STEP_RE = re.compile(r"^####\s+Step\s+(\d+\.\d+)\s+—\s+(.+?)(?:\s+\(#(\d+)\))?$")
BEHAVIOURS_RE = re.compile(r"^-\s+Behaviours?:\s+(.+)$")
TESTS_RE = re.compile(r"^-\s+Tests?:\s+(.+)$")
DEPENDS_RE = re.compile(r"^-\s+Depends\s+on:\s+(.+)$")
SIZE_RE = re.compile(r"^-\s+Size:\s+(S|M|L)$")

# Behavior id pattern: backticked lowercase dotted ids
BEHAVIOR_ID_RE = re.compile(r"`([a-z][a-z0-9+_-]*(?:\.[a-z0-9+_-]+)+)`")

# A behaviour line: "- `id` [TAG] ..."
BEHAVIOUR_LINE_RE = re.compile(r"^-\s+" + BEHAVIOR_ID_RE.pattern)

# Tag pattern for behavior status
TAG_RE = re.compile(
    r"\*{0,2}\[(OK|BROKEN|GAP|PARTIAL|MISSING|PROPOSED)(?:/[A-Z]+)?[^\]]*\]\*{0,2}"
)


def _is_scaffold(p: pathlib.Path) -> bool:
    """Scaffolding (_TEMPLATE.md) or under hidden directory."""
    return p.name.startswith("_") or _under_hidden_dir(p, SPECS_DIR)


def _under_hidden_dir(p: pathlib.Path, root: pathlib.Path) -> bool:
    """True when any directory between root and p is hidden (.claude, .git, ...)."""
    try:
        parts = p.relative_to(root).parts[:-1]
    except ValueError:
        return False
    return any(part.startswith(".") for part in parts)


def _spec_files() -> list[pathlib.Path]:
    if not SPECS_DIR.exists():
        return []
    return [p for p in sorted(scan_rglob(SPECS_DIR, "*.md")) if not _is_scaffold(p)]


def _is_approved(text: str) -> bool:
    """Check if spec is APPROVED (vs DRAFT)."""
    # ponytail: simple substring match, no status parsing needed yet
    return "**Status: APPROVED" in text


def _parse_build_order(text: str) -> dict | None:
    """Parse build order section from spec text.

    Returns dict with 'stages' list or None if no build order section.
    Each stage has 'number', 'title', 'steps' list.
    Each step has 'number', 'title', 'issue', 'behaviours', 'tests', 'depends_on', 'size'.
    """
    lines = text.splitlines()

    # Find build order section
    build_order_start = None
    for i, line in enumerate(lines):
        if line.strip() == "## Build order":
            build_order_start = i
            break

    if build_order_start is None:
        return None

    # Parse until next ## section or end
    stages = []
    current_stage = None
    current_step = None

    i = build_order_start + 1
    while i < len(lines):
        line = lines[i]

        # Stop at next ## section
        if (
            line.startswith("## ")
            and not line.startswith("### ")
            and not line.startswith("#### ")
        ):
            break

        # Stage
        stage_match = STAGE_RE.match(line)
        if stage_match:
            if current_step:
                current_stage["steps"].append(current_step)
                current_step = None
            if current_stage:
                stages.append(current_stage)
            current_stage = {
                "number": int(stage_match.group(1)),
                "title": stage_match.group(2).strip(),
                "steps": [],
            }
            i += 1
            continue

        # Step
        step_match = STEP_RE.match(line)
        if step_match:
            if current_step:
                if current_stage:
                    current_stage["steps"].append(current_step)
                else:
                    # Step without stage - create implicit stage 0
                    # ponytail: handle steps without explicit stage
                    if not stages or stages[-1]["number"] != 0:
                        stages.append({"number": 0, "title": "(implicit)", "steps": []})
                        current_stage = stages[-1]
                    current_stage["steps"].append(current_step)

            current_step = {
                "number": step_match.group(1),
                "title": step_match.group(2).strip(),
                "issue": step_match.group(3),
                "behaviours": [],
                "tests": [],
                "depends_on": [],
                "size": None,
            }
            i += 1
            continue

        # Step properties
        if current_step:
            behaviours_match = BEHAVIOURS_RE.match(line)
            if behaviours_match:
                # Extract backticked behaviour ids
                current_step["behaviours"] = BEHAVIOR_ID_RE.findall(
                    behaviours_match.group(1)
                )
                i += 1
                continue

            tests_match = TESTS_RE.match(line)
            if tests_match:
                # Split comma-separated test paths and strip whitespace
                tests_text = tests_match.group(1)
                current_step["tests"] = [
                    t.strip() for t in tests_text.split(",") if t.strip()
                ]
                i += 1
                continue

            depends_match = DEPENDS_RE.match(line)
            if depends_match:
                # Split comma-separated step ids
                deps_text = depends_match.group(1)
                current_step["depends_on"] = [
                    d.strip() for d in deps_text.split(",") if d.strip()
                ]
                i += 1
                continue

            size_match = SIZE_RE.match(line)
            if size_match:
                current_step["size"] = size_match.group(1)
                i += 1
                continue

        i += 1

    # Add final step and stage
    if current_step:
        if current_stage:
            current_stage["steps"].append(current_step)
        else:
            # ponytail: implicit stage 0 for steps without explicit stage
            if not stages or stages[-1]["number"] != 0:
                stages.append({"number": 0, "title": "(implicit)", "steps": []})
            stages[-1]["steps"].append(current_step)
    if current_stage and (not stages or stages[-1] is not current_stage):
        stages.append(current_stage)

    return {"stages": stages} if stages else None


def _get_all_behaviours_in_spec(text: str) -> dict[str, str]:
    """Return dict of behavior id -> tag for all behaviors in spec."""
    lines = text.splitlines()
    behaviours = {}

    for line in lines:
        # A behaviour is a list line that opens with its backticked id and carries a tag;
        # an id mentioned in prose (a file name like `ci.yml`) is not one.
        m = BEHAVIOUR_LINE_RE.match(line)
        if m and (tag_match := TAG_RE.search(line)):
            behaviours[m.group(1)] = tag_match.group(1)

    return behaviours


def _validate_build_order(
    spec_path: pathlib.Path,
    build_order: dict,
    all_behaviours: dict[str, str],
    is_approved: bool,
) -> list[str]:
    """Validate build order structure. Returns list of error messages."""
    errors = []
    # ponytail: simple string for error messages, handles self-test paths
    try:
        rel_path = spec_path.relative_to(SPECS_DIR.parent.parent)
    except ValueError:
        rel_path = spec_path

    # Track which behaviours are in build order steps
    behaviour_occurrences: dict[str, list[str]] = {}
    all_steps: dict[
        str, tuple[int, int]
    ] = {}  # step_id -> (stage_num, position_in_stage)

    # First pass: populate all_steps for all steps
    for stage in build_order["stages"]:
        stage_num = stage["number"]
        for step_idx, step in enumerate(stage["steps"]):
            step_id = step["number"]
            all_steps[step_id] = (stage_num, step_idx)

    # Second pass: validate each step
    for stage in build_order["stages"]:
        stage_num = stage["number"]
        for step_idx, step in enumerate(stage["steps"]):
            step_id = step["number"]

            # Check step has behaviours and tests
            if not step["behaviours"]:
                errors.append(f"{rel_path} step {step_id}: has no Behaviours")
            if not step["tests"]:
                errors.append(f"{rel_path} step {step_id}: has no Tests")

            # Check size constraints
            if step["size"] == "L":
                errors.append(f"{rel_path} step {step_id}: is Size L (max is M)")
            if len(step["behaviours"]) > 5:
                errors.append(
                    f"{rel_path} step {step_id}: has {len(step['behaviours'])} behaviours (max 5)"
                )

            # Track behaviour occurrences
            for behaviour in step["behaviours"]:
                if behaviour not in behaviour_occurrences:
                    behaviour_occurrences[behaviour] = []
                behaviour_occurrences[behaviour].append(step_id)

            # Validate dependencies
            for dep in step["depends_on"]:
                if dep == step_id:
                    errors.append(f"{rel_path} step {step_id}: depends on itself")
                elif dep not in all_steps:
                    errors.append(
                        f"{rel_path} step {step_id}: depends on unknown step {dep}"
                    )
                else:
                    dep_stage, dep_pos = all_steps[dep]
                    curr_stage, curr_pos = all_steps[step_id]
                    # Forward dependency: either later stage or same stage but later position
                    if dep_stage > curr_stage or (
                        dep_stage == curr_stage and dep_pos >= curr_pos
                    ):
                        errors.append(
                            f"{rel_path} step {step_id}: depends on {dep} which comes at or after it"
                        )

    # Check non-[OK] behaviours appear exactly once in build order
    for behaviour_id, tag in all_behaviours.items():
        if tag == "OK":
            continue

        if behaviour_id not in behaviour_occurrences:
            errors.append(
                f"{rel_path}: behaviour `{behaviour_id}` (tagged [{tag}]) appears in no build order step"
            )
        elif len(behaviour_occurrences[behaviour_id]) > 1:
            steps = ", ".join(behaviour_occurrences[behaviour_id])
            errors.append(
                f"{rel_path}: behaviour `{behaviour_id}` appears in multiple steps: {steps}"
            )

    return errors


def _self_test() -> int:
    """Synthesise defects this guard should catch."""
    # Test parsing
    test_spec = """# Test Spec

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

### Stage 1 — second stage

#### Step 1.1 — third step
- Behaviours: `test.four`, `test.five`
- Tests: test/four.py
- Depends on: 0.2
- Size: M

## Behaviors

- `test.one` — [OK] first
- `test.two` — [MISSING] second
- `test.three` — [MISSING] (#999) third
- `test.four` — [BROKEN] fourth
- `test.five` — [MISSING] fifth
- `test.orphan` — [MISSING] not in build order
"""

    build_order = _parse_build_order(test_spec)
    if not build_order:
        print("self-test FAILED: could not parse build order")
        return 1

    # Check parsing
    ok = True
    if len(build_order["stages"]) != 2:
        print(f"self-test FAILED: expected 2 stages, got {len(build_order['stages'])}")
        ok = False

    if len(build_order["stages"][0]["steps"]) != 2:
        print(
            f"self-test FAILED: expected 2 steps in stage 0, got {len(build_order['stages'][0]['steps'])}"
        )
        ok = False

    step1 = build_order["stages"][0]["steps"][0]
    if step1["number"] != "0.1" or len(step1["behaviours"]) != 2:
        print("self-test FAILED: step parsing incorrect")
        ok = False

    # Check orphan detection
    all_behaviours = _get_all_behaviours_in_spec(test_spec)
    errors = _validate_build_order(
        pathlib.Path("test.md"), build_order, all_behaviours, True
    )

    has_orphan_error = any(
        "test.orphan" in e and "appears in no build order step" in e for e in errors
    )
    if not has_orphan_error:
        print("self-test FAILED: did not detect orphan behaviour")
        ok = False

    # Test forward dependency detection
    forward_dep_spec = """# Test Spec

**Status: APPROVED**

## Build order

#### Step 0.1 — first
- Behaviours: `test.one`
- Tests: test/one.py
- Depends on: 0.2
- Size: S

#### Step 0.2 — second
- Behaviours: `test.two`
- Tests: test/two.py
- Size: S

## Behaviors

- `test.one` — [MISSING] one
- `test.two` — [MISSING] two
"""

    forward_bo = _parse_build_order(forward_dep_spec)
    forward_behaviours = _get_all_behaviours_in_spec(forward_dep_spec)
    forward_errors = _validate_build_order(
        pathlib.Path("test.md"), forward_bo, forward_behaviours, True
    )

    has_forward_error = any(
        "0.1" in e and "depends on 0.2" in e for e in forward_errors
    )
    if not has_forward_error:
        print("self-test FAILED: did not detect forward dependency")
        ok = False

    if ok:
        print("self-test ok")
    return 0 if ok else 1


def main() -> int:
    specs = _spec_files()
    if not specs:
        print(
            f"FAIL check_spec_build_order_shape: no specs found under {SPECS_DIR} (blind, not green)"
        )
        return 2

    total_errors = []
    total_warnings = []
    specs_with_build_order = 0

    for spec in specs:
        text = spec.read_text(encoding="utf-8")
        build_order = _parse_build_order(text)

        if not build_order:
            continue  # No build order section - skip silently

        specs_with_build_order += 1
        is_approved = _is_approved(text)
        all_behaviours = _get_all_behaviours_in_spec(text)

        errors = _validate_build_order(spec, build_order, all_behaviours, is_approved)

        if is_approved:
            total_errors.extend(errors)
        else:
            total_warnings.extend(errors)

    # Report results
    if total_errors:
        print("FAIL check_spec_build_order_shape:")
        for error in total_errors:
            print(f"  - {error}")
        return 1

    # Report warnings for draft specs
    if total_warnings:
        print(
            f"OK check_spec_build_order_shape: {specs_with_build_order} spec(s) with build order sections"
        )
        print("Warnings (DRAFT specs only):")
        for warning in total_warnings:
            print(f"  - {warning}")
    else:
        print(
            f"OK check_spec_build_order_shape: {specs_with_build_order} spec(s) with build order sections, all valid"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test() if "--self-test" in sys.argv else main())
