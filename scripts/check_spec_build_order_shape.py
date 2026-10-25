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

A spec without a `## Build order` section is skipped silently. For an APPROVED spec
(header line `**Status: APPROVED`) the guard FAILS (one line per problem, naming the
spec and the step) when:

- a non-[OK] behaviour is in no step, or in more than one;
- a step has no Behaviours or no Tests;
- a step is Size L or lists more than five behaviours;
- a Depends-on points at a later step, at itself, or at a step that does not exist.

For a DRAFT spec the same problems are printed as warnings and the exit code is 0.

Run: python scripts/check_spec_build_order_shape.py
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

# Same behaviour-id and tag grammar as check_spec_broken_has_issue — one definition of
# "a behaviour line" across the spec guards.
BEHAVIOR_ID_RE = r"[a-z][a-z0-9+_-]*(?:\.[a-z0-9+_-]+)+"
BEHAVIOR_START_RE = re.compile(r"^\s*-\s+`(" + BEHAVIOR_ID_RE + r")`")
NON_OK_TAG_RE = re.compile(r"\*{0,2}\[(BROKEN|GAP(?:/BROKEN)?|PARTIAL|MISSING)[^\]]*\]\*{0,2}")
OK_TAG_RE = re.compile(r"\*{0,2}\[OK[^\]]*\]\*{0,2}")
CONTINUATION_RE = re.compile(r"^\s+\S")

# ponytail: substring match anywhere in the file, not just the header line — a spec body
# that says "**Status: APPROVED**" in prose would be read as approved. The status line is
# the only place that phrase is written; a header-anchor (first 20 lines) is the upgrade.
APPROVED_RE = re.compile(r"\*\*Status:\s*APPROVED")
SECTION_RE = re.compile(r"^##\s+Build order\s*$")
STAGE_RE = re.compile(r"^###\s+Stage\s+(\d+)\s*[—–-]\s*(.*?)\s*$")
STEP_RE = re.compile(r"^####\s+Step\s+(\d+\.\d+)\s*[—–-]\s*(.*?)\s*(?:\(#(\d+)\))?\s*$")
BEHAVIORS_RE = re.compile(r"^-\s+Behaviours:\s*(.*)$")
TESTS_RE = re.compile(r"^-\s+Tests:\s*(.*)$")
DEPENDS_RE = re.compile(r"^-\s+Depends on:\s*(.*)$")
SIZE_RE = re.compile(r"^-\s+Size:\s*(\S+)")

MAX_BEHAVIOURS_PER_STEP = 5


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


def parse_build_order(text: str) -> tuple[list[Stage], list[Step]]:
    """(stages, steps) from the `## Build order` section; ([], []) when the spec has none."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if SECTION_RE.match(ln)), None)
    if start is None:
        return [], []
    # The section ends at the next H2 (`## ` never matches `###`/`####`).
    end = next((j for j in range(start + 1, len(lines)) if lines[j].startswith("## ")), len(lines))

    stages: list[Stage] = []
    steps: list[Step] = []
    cur: Step | None = None
    for ln in lines[start + 1 : end]:
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


def _non_ok_behaviours(text: str) -> list[tuple[str, str]]:
    """(behaviour_id, tag) for every tagged behaviour whose tag is not [OK].

    Untagged behaviour lines are skipped — check_spec_behaviors_are_tagged polices those.
    ponytail: a behaviour whose DESCRIPTION quotes a tag (e.g. "was [GAP] in March") is
    read as tagged — same accepted weakness as check_spec_broken_has_issue; tags in prose
    do not occur in the specs today.
    """
    out: list[tuple[str, str]] = []
    lines = text.splitlines()
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
        joined = "\n".join(block)
        if not OK_TAG_RE.search(joined):
            tag = NON_OK_TAG_RE.search(joined)
            if tag:
                out.append((m.group(1), tag.group(0)))
        i = j
    return out


def _check_spec(text: str) -> tuple[bool, list[Step], list[str]]:
    """(approved, steps, problems) for one spec body; empty steps means 'no build order'."""
    _, steps = parse_build_order(text)
    approved = bool(APPROVED_RE.search(text))
    if not steps:
        # ponytail: a section that exists but names zero steps is treated as 'no build
        # order' (skipped). An APPROVED spec with an EMPTY build order would still fail
        # the orphan-behaviour check via its behaviours list — unless it has none.
        return approved, steps, []
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


def _is_scaffold(p: pathlib.Path) -> bool:
    # Scaffolding (`_TEMPLATE.md`). Hidden directories are already pruned by scan_rglob.
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
        if not steps:
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


def _self_test() -> int:
    """Prove the guard fails what it claims to catch: a non-[OK] behaviour left out of
    every step, and a Depends-on pointing forward. Fixtures are written to a temp dir."""
    global SPECS_DIR
    ok = True
    with tempfile.TemporaryDirectory() as td:
        specs_dir = pathlib.Path(td) / "specs"
        specs_dir.mkdir()
        SPECS_DIR = specs_dir
        fixture = specs_dir / "fixture.md"
        fixture.write_text(_ORPHAN_FIXTURE, encoding="utf-8")
        ok = ok and main() == 1
        fixture.write_text(_FORWARD_FIXTURE, encoding="utf-8")
        ok = ok and main() == 1
    print("self-test " + ("ok" if ok else "FAILED: the guard does not fail an orphan behaviour or a forward Depends-on"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_self_test() if "--self-test" in sys.argv else main())
