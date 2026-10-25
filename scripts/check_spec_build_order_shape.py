#!/usr/bin/env python3
"""Every spec's build order must have one fixed shape (pipeline.build-order-shape, #6116).

The shape (specs/_TEMPLATE.md, "Build order"; defined by
docs/contributor_manual/specs/harness/deterministic-conductor.md):

    ## Build order
    ### Stage N — title                      (optional)
    #### Step N.M — title (#NNNN)            (issue number optional until filed)
    - Behaviours: `id.one`, `id.two`
    - Tests: path/a.py, path/b.py
    - Depends on: N.M, ...                   (optional; default: the step before, in-stage)
    - Size: S | M | L

A spec without a `## Build order` section is skipped silently.  For an APPROVED spec
(header line ``**Status: APPROVED**`` in the first 20 lines) the guard FAILS
(exit 1, one line per problem, naming the spec and the step) when:

- a non-[OK] behaviour is in no step or in more than one;
- a step has no Behaviours or no Tests;
- a step is Size L or lists more than five behaviours;
- a Depends-on points at a later step, at itself, or at an unknown step.

A DRAFT spec produces warnings instead of failures (exit 0).

Run:
    python scripts/check_spec_build_order_shape.py
    python scripts/check_spec_build_order_shape.py --self-test
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile
from dataclasses import dataclass, field

from _scan_files import scan_rglob

SPECS_DIR = pathlib.Path("docs/contributor_manual/specs")
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# --- regexes ----------------------------------------------------------------

BEHAVIOR_ID_RE = r"[a-z][a-z0-9+_-]*(?:\.[a-z0-9+_-]+)+"
BEHAVIOR_START_RE = re.compile(r"^\s*-\s+`(" + BEHAVIOR_ID_RE + r")`")
# Single tag regex: captures the tag NAME as group(1).
TAG_RE = re.compile(r"\[(OK|BROKEN|GAP(?:/BROKEN)?|PARTIAL|MISSING|PROPOSED)[^\]]*\]")
CONTINUATION_RE = re.compile(r"^\s+\S")

# ponytail: first-20-line window is a heuristic; a spec would need >20 lines of
# front-matter before the Status line to break it.
APPROVED_RE = re.compile(r"\*\*Status:\s*APPROVED")
# Allow trailing annotation: "## Build order (2026-09-19; ...)"
SECTION_RE = re.compile(r"^##\s+Build order\b.*$")
STAGE_RE = re.compile(r"^###\s+Stage\s+(\d+)\s*[—–-]\s*(.*?)\s*$")
STEP_RE = re.compile(r"^####\s+Step\s+(\d+\.\d+)\s*[—–-]\s*(.*?)\s*(?:\(#(\d+)\))?\s*$")
BEHAVIORS_RE = re.compile(r"^-\s+Behaviours:\s*(.*)$")
TESTS_RE = re.compile(r"^-\s+Tests:\s*(.*)$")
DEPENDS_RE = re.compile(r"^-\s+Depends on:\s*(.*)$")
SIZE_RE = re.compile(r"^-\s+Size:\s*(\S+)")
BEHAVIOURS_SECTION_RE = re.compile(r"^##\s+Behav\w*")
# ponytail: "Slice" only; older specs (source-model, explore) use this shape.
SLICE_RE = re.compile(r"^###\s+Slice\s+\d+")

MAX_BEHAVIOURS_PER_STEP = 5


# --- dataclasses --------------------------------------------------------------

@dataclass
class Stage:
    number: str
    title: str


@dataclass
class Step:
    step_id: str
    title: str
    issue: str | None
    behaviours: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    size: str | None = None


# --- parsing -----------------------------------------------------------------

def parse_build_order(text: str) -> tuple[list[Stage], list[Step]]:
    """(stages, steps) from the ``## Build order`` section; ([], []) when absent."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if SECTION_RE.match(ln)), None)
    if start is None:
        return [], []
    end = next((j for j in range(start + 1, len(lines)) if re.match(r"^##\s", lines[j])), len(lines))

    stages: list[Stage] = []
    steps: list[Step] = []
    cur: Step | None = None
    for ln in lines[start + 1: end]:
        m = STAGE_RE.match(ln)
        if m:
            stages.append(Stage(m.group(1), m.group(2)))
            continue
        m = STEP_RE.match(ln)
        if m:
            cur = Step(step_id=m.group(1), title=m.group(2), issue=m.group(3))
            steps.append(cur)
            continue
        if cur is None:
            continue
        m = BEHAVIORS_RE.match(ln)
        if m:
            cur.behaviours = re.findall(r"`(" + BEHAVIOR_ID_RE + r")`", m.group(1))
            continue
        m = TESTS_RE.match(ln)
        if m:
            cur.tests = [t.strip() for t in m.group(1).split(",") if t.strip()]
            continue
        m = DEPENDS_RE.match(ln)
        if m:
            cur.depends_on = [d.strip() for d in m.group(1).split(",") if d.strip()]
            continue
        m = SIZE_RE.match(ln)
        if m:
            cur.size = m.group(1)
    return stages, steps


def _has_build_order_section(text: str) -> bool:
    return any(SECTION_RE.match(ln) for ln in text.splitlines())


def _is_approved(text: str) -> bool:
    """True only if a ``**Status: APPROVED**`` line appears in the first 20 lines."""
    return any(APPROVED_RE.search(ln) for ln in text.splitlines()[:20])


def _behaviours_section_lines(text: str) -> list[str]:
    """Lines under the spec's ``## Behav*`` heading, up to the next H2."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if BEHAVIOURS_SECTION_RE.match(ln)), None)
    if start is None:
        return []
    end = next((j for j in range(start + 1, len(lines)) if re.match(r"^##\s", lines[j])), len(lines))
    return lines[start + 1: end]


def _non_ok_behaviours(text: str) -> list[tuple[str, str]]:
    """(behaviour_id, tag) for every non-[OK]/non-[PROPOSED] behaviour in the Behaviours section.

    Classification uses the FIRST tag in the behaviour's block (the tag immediately
    after the id) so that a description quoting "[OK]" cannot flip the classification.
    Scan is limited to the ``## Behav*`` section so a Rulings bullet quoting an id
    cannot become a phantom behaviour.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    lines = _behaviours_section_lines(text)
    i = 0
    while i < len(lines):
        m = BEHAVIOR_START_RE.match(lines[i])
        if not m:
            i += 1
            continue
        block = [lines[i]]
        j = i + 1
        while j < len(lines) and CONTINUATION_RE.match(lines[j]) and not BEHAVIOR_START_RE.match(lines[j]):
            block.append(lines[j])
            j += 1
        tag_m = TAG_RE.search("\n".join(block))
        if tag_m and tag_m.group(1) not in ("OK", "PROPOSED") and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append((m.group(1), tag_m.group(0)))
        i = j
    return out


# --- checking -----------------------------------------------------------------

def _check_spec(text: str) -> tuple[bool, list[Step], list[str]]:
    """(approved, steps, problems) for one spec body."""
    _, steps = parse_build_order(text)
    approved = _is_approved(text)
    if not steps:
        if _has_build_order_section(text):
            # Section exists but no step headings parsed (wrong heading level, old shape).
            return approved, steps, ["Build order section has no `#### Step N.M` headings"]
        return approved, steps, []  # no build order section at all — skip

    problems: list[str] = []
    for behaviour_id, tag in _non_ok_behaviours(text):
        owners = [s.step_id for s in steps if behaviour_id in s.behaviours]
        if not owners:
            problems.append(f"behaviour `{behaviour_id}` ({tag}) is in no step of the build order")
        elif len(owners) > 1:
            problems.append(f"behaviour `{behaviour_id}` ({tag}) is in {len(owners)} steps ({', '.join(owners)})")
    order = [s.step_id for s in steps]
    for s in steps:
        if not s.behaviours:
            problems.append(f"Step {s.step_id} has no Behaviours")
        if not s.tests:
            problems.append(f"Step {s.step_id} has no Tests")
        if s.size == "L":
            problems.append(f"Step {s.step_id} is Size L")
        if len(s.behaviours) > MAX_BEHAVIOURS_PER_STEP:
            problems.append(f"Step {s.step_id} lists {len(s.behaviours)} behaviours (max {MAX_BEHAVIOURS_PER_STEP})")
        for dep in s.depends_on:
            if dep == s.step_id:
                problems.append(f"Step {s.step_id} depends on itself")
            elif dep not in order:
                problems.append(f"Step {s.step_id} depends on unknown step {dep}")
            elif order.index(dep) > order.index(s.step_id):
                problems.append(f"Step {s.step_id} depends on later step {dep}")
    return approved, steps, problems


# --- self-test helpers --------------------------------------------------------

def _source_model_distance() -> str:
    """Parse source/source-model.md and report how far its build order is from the new shape."""
    p = REPO_ROOT / "docs" / "contributor_manual" / "specs" / "source" / "source-model.md"
    if not p.exists():
        return "source-model.md not found (skipped)"
    text = p.read_text(encoding="utf-8")
    if not _has_build_order_section(text):
        return "source-model.md: no `## Build order` section"
    _, steps = parse_build_order(text)
    n_slices = sum(1 for ln in text.splitlines() if SLICE_RE.match(ln))
    return (f"source-model.md: {n_slices} Slice headings, {len(steps)} new-shape steps "
            f"(distance = {n_slices - len(steps)} slices to convert; spec is DRAFT, not rewritten by design)")


_ORPHAN_FIXTURE = """# Fixture spec

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

# Regression for issue #1: the description contains "non-[OK]" which previously
# fooled OK_TAG_RE into classifying this behaviour as OK.
_OK_IN_PROSE_FIXTURE = """# Fixture spec

> **Status: APPROVED**

## Behaviours

- `fixture.prose.missing` [MISSING] — a non-[OK] behaviour that must be covered.
- `fixture.prose.ok` [OK] — fine.

## Build order

#### Step 1.1 — only ok
- Behaviours: `fixture.prose.ok`
- Tests: tests/a.py
- Size: S
"""

_FORWARD_FIXTURE = """# Fixture spec

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
- Size: S
"""

# Fixture triggering all five step-level rules at once (issue #5).
_RULES_FIXTURE = """# Fixture spec

> **Status: APPROVED**

## Behaviours

- `fixture.rules.a` [MISSING] — a.
- `fixture.rules.b` [MISSING] — b.
- `fixture.rules.c` [MISSING] — c.
- `fixture.rules.d` [MISSING] — d.
- `fixture.rules.e` [MISSING] — e.
- `fixture.rules.f` [MISSING] — f.
- `fixture.rules.g` [MISSING] — g.
- `fixture.rules.h` [MISSING] — h.

## Build order

#### Step 1.1 — no behaviours
- Tests: tests/x.py
- Size: S

#### Step 1.2 — no tests
- Behaviours: `fixture.rules.a`, `fixture.rules.b`, `fixture.rules.c`, `fixture.rules.d`, `fixture.rules.e`, `fixture.rules.f`
- Depends on: 9.9
- Size: L

#### Step 1.3 — clean-ish
- Behaviours: `fixture.rules.g`, `fixture.rules.h`
- Tests: tests/y.py
- Size: M
"""

# Rulings section quoting a behaviour id should NOT create a phantom (issue #6).
_RULINGS_FIXTURE = """# Fixture spec

> **Status: APPROVED**

## Behaviours

- `fixture.ruling.a` [MISSING] — covered in a step.

## Build order

#### Step 1.1 — the only step
- Behaviours: `fixture.ruling.a`
- Tests: tests/a.py
- Size: S

## Rulings

- `fixture.ruling.a` [OK] — resolved in v2 (quoted for reference).
- `fixture.ruling.b` [MISSING] — quoted in ruling, not in Behaviours section.
"""


def _self_test() -> int:
    """Prove the guard catches its own failure modes + report source-model distance."""
    global SPECS_DIR
    ok = True
    with tempfile.TemporaryDirectory() as td:
        specs_dir = pathlib.Path(td) / "specs"
        specs_dir.mkdir()
        SPECS_DIR = specs_dir
        fixture = specs_dir / "fixture.md"

        # 1. Orphan behaviour → exit 1
        fixture.write_text(_ORPHAN_FIXTURE, encoding="utf-8")
        ok = ok and main() == 1

        # 2. "[OK]" in prose must NOT mask a [MISSING] behaviour (issue #1)
        fixture.write_text(_OK_IN_PROSE_FIXTURE, encoding="utf-8")
        ok = ok and main() == 1

        # 3. Forward dependency → exit 1
        fixture.write_text(_FORWARD_FIXTURE, encoding="utf-8")
        ok = ok and main() == 1

        # 4. Five step-level rules fire (issue #5)
        fixture.write_text(_RULES_FIXTURE, encoding="utf-8")
        ok = ok and main() == 1

        # 5. Rulings-section bullet must NOT create a phantom (issue #6)
        fixture.write_text(_RULINGS_FIXTURE, encoding="utf-8")
        ok = ok and main() == 0

    # 6. source-model distance report (spec acceptance, issue #4a)
    print("self-test distance: " + _source_model_distance())

    print("self-test " + ("ok" if ok else "FAILED"))
    return 0 if ok else 1


# --- entry point ---------------------------------------------------------------

def _is_scaffold(p: pathlib.Path) -> bool:
    return p.name.startswith("_")


def _spec_files() -> list[pathlib.Path]:
    if not SPECS_DIR.exists():
        return []
    return [p for p in sorted(scan_rglob(SPECS_DIR, "*.md")) if not _is_scaffold(p)]


def main() -> int:
    specs = _spec_files()
    if not specs:
        print(f"FAIL check_spec_build_order_shape: no specs found under {SPECS_DIR} (blind, not green)")
        return 2

    failures: list[str] = []
    warnings: list[str] = []
    with_order = 0
    for spec in specs:
        approved, steps, problems = _check_spec(spec.read_text(encoding="utf-8"))
        if not steps and not problems:
            continue  # no build order section — skipped silently
        with_order += 1
        where = str(spec.relative_to(SPECS_DIR.parent.parent)).replace("\\", "/")
        for p in problems:
            (failures if approved else warnings).append(f"{where}: {p}")

    if failures:
        print("FAIL check_spec_build_order_shape:")
        for f in failures:
            print(f"  - {f}")
        return 1
    if warnings:
        print("WARN check_spec_build_order_shape (DRAFT specs warn only):")
        for w in warnings:
            print(f"  - {w}")
    print(f"OK check_spec_build_order_shape: {with_order} build orders across {len(specs)} specs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test() if "--self-test" in sys.argv else main())