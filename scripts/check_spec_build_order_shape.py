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
(a `**Status: APPROVED` line in the header, the first 20 lines) the guard FAILS
(exit 1, one line per problem naming the spec and the step) when:

- a behaviour tagged [MISSING]/[GAP]/[BROKEN]/[PARTIAL] is in no step or in more than one;
- the section has no readable `#### Step N.M` heading at all;
- a step has no Behaviours or no Tests;
- a step is Size L or lists more than five behaviours;
- a Depends-on points at a later step, at itself, or at an unknown step.

A DRAFT spec produces the same problems as warnings (exit 0).

Run:
    python scripts/check_spec_build_order_shape.py
    python scripts/check_spec_build_order_shape.py --self-test
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile

from _scan_files import scan_rglob

SPECS_DIR = pathlib.Path("docs/contributor_manual/specs")

BEHAVIOUR_ID = r"[a-z][a-z0-9+_-]*(?:\.[a-z0-9+_-]+)+"
BEHAVIOUR_START_RE = re.compile(r"^\s*-\s+`(" + BEHAVIOUR_ID + r")`")
TAG_RE = re.compile(r"\[(OK|BROKEN|GAP|PARTIAL|MISSING|PROPOSED)[^\]]*\]")
# Only these tags owe a build-order step; [OK] is shipped, [PROPOSED] is not committed to.
NEEDS_STEP = {"MISSING", "GAP", "BROKEN", "PARTIAL"}
APPROVED_RE = re.compile(r"\*\*Status:\s*APPROVED")
H2_RE = re.compile(r"^##\s")
SECTION_RE = re.compile(r"^##\s+Build order\b")
BEHAVIOURS_SECTION_RE = re.compile(r"^##\s+Behav\w*")
STAGE_RE = re.compile(r"^###\s+Stage\s+(\d+)\s*[—–-]\s*(.*?)\s*$")
STEP_RE = re.compile(r"^####\s+Step\s+(\d+\.\d+)\s*[—–-]\s*(.*?)\s*(?:\(#(\d+)\))?\s*$")
BEHAVIOURS_RE = re.compile(r"^-\s+Behaviours?:\s*(.*)$")
TESTS_RE = re.compile(r"^-\s+Tests?:\s*(.*)$")
DEPENDS_RE = re.compile(r"^-\s+Depends\s+on:\s*(.*)$")
SIZE_RE = re.compile(r"^-\s+Size:\s*(\S+)")
MAX_BEHAVIOURS_PER_STEP = 5


def _section(lines: list[str], start_re: re.Pattern[str]) -> list[str] | None:
    """Lines under the first heading matching start_re, up to the next H2; None if absent."""
    start = next((i for i, ln in enumerate(lines) if start_re.match(ln)), None)
    if start is None:
        return None
    end = next(
        (j for j in range(start + 1, len(lines)) if H2_RE.match(lines[j])), len(lines)
    )
    return lines[start + 1 : end]


def _parse_build_order(text: str) -> dict | None:
    """{'stages': [{'number', 'title', 'steps': [step]}]}; None without a Build order section.

    A step is {'number', 'title', 'issue', 'behaviours', 'tests', 'depends_on', 'size'}.
    A section with no readable step has no stages.
    """
    body = _section(text.splitlines(), SECTION_RE)
    if body is None:
        return None
    stages: list[dict] = []
    step: dict | None = None
    for ln in body:
        if m := STAGE_RE.match(ln):
            stages.append({"number": int(m.group(1)), "title": m.group(2), "steps": []})
        elif m := STEP_RE.match(ln):
            if (
                not stages
            ):  # ponytail: steps before any Stage heading share an implicit stage 0
                stages.append({"number": 0, "title": "", "steps": []})
            step = {
                "number": m.group(1),
                "title": m.group(2),
                "issue": m.group(3),
                "behaviours": [],
                "tests": [],
                "depends_on": [],
                "size": None,
            }
            stages[-1]["steps"].append(step)
        elif step is None:
            continue
        elif m := BEHAVIOURS_RE.match(ln):
            step["behaviours"] = re.findall(r"`(" + BEHAVIOUR_ID + r")`", m.group(1))
        elif m := TESTS_RE.match(ln):
            step["tests"] = [t.strip() for t in m.group(1).split(",") if t.strip()]
        elif m := DEPENDS_RE.match(ln):
            step["depends_on"] = [d.strip() for d in m.group(1).split(",") if d.strip()]
        elif m := SIZE_RE.match(ln):
            step["size"] = m.group(1)
    return {"stages": stages}


def _is_approved(text: str) -> bool:
    """True only when a `**Status: APPROVED` line is in the header (first 20 lines)."""
    # ponytail: the header is the first 20 lines; a longer preamble would hide the status
    return any(APPROVED_RE.search(ln) for ln in text.splitlines()[:20])


def _get_all_behaviours_in_spec(text: str) -> dict[str, str]:
    """{behaviour id: tag} from the spec's Behaviours section only.

    A behaviour is a list line opening with its backticked id; the FIRST tag in its
    block (the line and its indented continuation) decides, so prose quoting "[OK]"
    cannot flip it.  A block with no tag is not a behaviour.
    """
    lines = _section(text.splitlines(), BEHAVIOURS_SECTION_RE) or []
    out: dict[str, str] = {}
    for i, ln in enumerate(lines):
        m = BEHAVIOUR_START_RE.match(ln)
        if not m:
            continue
        block = [ln]
        for nxt in lines[i + 1 :]:
            if not nxt[:1].isspace() or BEHAVIOUR_START_RE.match(nxt):
                break
            block.append(nxt)
        if tag := TAG_RE.search("\n".join(block)):
            out.setdefault(m.group(1), tag.group(1))
    return out


def _check_spec(text: str) -> tuple[bool, list[str]] | None:
    """(approved, problems) for one spec body; None when it has no Build order section."""
    parsed = _parse_build_order(text)
    if parsed is None:
        return None
    approved = _is_approved(text)
    steps = [s for st in parsed["stages"] for s in st["steps"]]
    if not steps:
        return approved, ["Build order has no readable `#### Step N.M — title` heading"]

    problems: list[str] = []
    for bid, tag in _get_all_behaviours_in_spec(text).items():
        if tag not in NEEDS_STEP:
            continue
        owners = [s["number"] for s in steps if bid in s["behaviours"]]
        if not owners:
            problems.append(
                f"behaviour `{bid}` [{tag}] is in no step of the build order"
            )
        elif len(owners) > 1:
            problems.append(
                f"behaviour `{bid}` [{tag}] is in {len(owners)} steps ({', '.join(owners)})"
            )
    order = [s["number"] for s in steps]
    for s in steps:
        n = s["number"]
        if not s["behaviours"]:
            problems.append(f"Step {n} has no Behaviours")
        if not s["tests"]:
            problems.append(f"Step {n} has no Tests")
        if s["size"] == "L":
            problems.append(f"Step {n} is Size L")
        if len(s["behaviours"]) > MAX_BEHAVIOURS_PER_STEP:
            problems.append(
                f"Step {n} lists {len(s['behaviours'])} behaviours (max {MAX_BEHAVIOURS_PER_STEP})"
            )
        for dep in s["depends_on"]:
            if dep == n:
                problems.append(f"Step {n} depends on itself")
            elif dep not in order:
                problems.append(f"Step {n} depends on unknown step {dep}")
            elif order.index(dep) > order.index(n):
                problems.append(f"Step {n} depends on later step {dep}")
    return approved, problems


def _spec_files() -> list[pathlib.Path]:
    if not SPECS_DIR.exists():
        return []
    return [
        p for p in sorted(scan_rglob(SPECS_DIR, "*.md")) if not p.name.startswith("_")
    ]


def main() -> int:
    specs = _spec_files()
    if not specs:
        print(
            f"FAIL check_spec_build_order_shape: no specs found under {SPECS_DIR} (blind, not green)"
        )
        return 2

    failures: list[str] = []
    warnings: list[str] = []
    with_order = 0
    for spec in specs:
        checked = _check_spec(spec.read_text(encoding="utf-8"))
        if checked is None:
            continue
        with_order += 1
        approved, problems = checked
        where = spec.relative_to(SPECS_DIR).as_posix()
        (failures if approved else warnings).extend(f"{where}: {p}" for p in problems)

    if failures:
        print("FAIL check_spec_build_order_shape:")
        for f in failures:
            print(f"  - {f}")
        return 1
    if warnings:
        print("WARN check_spec_build_order_shape (DRAFT specs warn only):")
        for w in warnings:
            print(f"  - {w}")
    print(
        f"OK check_spec_build_order_shape: {with_order} build orders across {len(specs)} specs."
    )
    return 0


# --- self-test ----------------------------------------------------------------

_HEAD = "# Fixture\n\n> **Status: {status}**\n\n"

_ORPHAN = (
    _HEAD
    + """## Behaviours

- `fx.a` [MISSING] — in a step.
- `fx.b` [MISSING] — in no step.
- `fx.p` [PROPOSED] — needs no step.

## Build order

#### Step 0.1 — only one
- Behaviours: `fx.a`
- Tests: tests/a.py
- Size: S
"""
)

_FORWARD = (
    _HEAD
    + """## Behaviours

- `fx.a` [MISSING] — a.
- `fx.b` [MISSING] — b.

## Build order

#### Step 0.1 - first
- Behaviours: `fx.a`
- Tests: tests/a.py
- Depends on: 0.2
- Size: S

#### Step 0.2 - second
- Behaviours: `fx.b`
- Tests: tests/b.py
- Size: S
"""
)

_NO_STEPS = (
    _HEAD
    + "## Behaviours\n\n- `fx.a` [MISSING] — a.\n\n## Build order\n\n### Slice 1 — old shape\n"
)


def _problems(template: str, status: str = "APPROVED") -> list[str]:
    checked = _check_spec(template.replace("{status}", status))
    return [] if checked is None else checked[1]


def _self_test() -> int:
    """Synthesise defects the guard must catch, prove the clean cases pass, run main() on a temp dir."""
    global SPECS_DIR
    ok = True

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if not cond:
            print(f"self-test FAILED: {label}")
            ok = False

    orphan = _problems(_ORPHAN)
    expect(
        "orphan behaviour fx.b not reported",
        any("`fx.b`" in p and "no step" in p for p in orphan),
    )
    expect(
        "[PROPOSED] behaviour wrongly needs a step",
        not any("`fx.p`" in p for p in orphan),
    )
    expect(
        "forward Depends-on not reported",
        any("Step 0.1" in p and "later step 0.2" in p for p in _problems(_FORWARD)),
    )
    expect(
        "APPROVED spec with no readable steps not reported", bool(_problems(_NO_STEPS))
    )

    saved = SPECS_DIR
    with tempfile.TemporaryDirectory() as td:
        SPECS_DIR = pathlib.Path(td)
        f = SPECS_DIR / "fixture.md"
        f.write_text(_ORPHAN.replace("{status}", "APPROVED"), encoding="utf-8")
        expect("APPROVED orphan must exit 1", main() == 1)
        f.write_text(_ORPHAN.replace("{status}", "DRAFT"), encoding="utf-8")
        expect("DRAFT orphan must exit 0", main() == 0)
    SPECS_DIR = saved

    print("self-test " + ("ok" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_self_test() if "--self-test" in sys.argv else main())
