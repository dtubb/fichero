#!/usr/bin/env python3
"""Requirements/pyproject sync guardrail.

`fichero-server/pyproject.toml` is the single source of truth for the engine's
runtime dependencies. `fichero-server/requirements.txt` is a GENERATED artifact
that mirrors it so the canonical dev venv can be kept in sync with what the
Briefcase app bundle ships.

This guardrail fails if the two drift: it computes the expected dependency set
as the UNION of

    [project].dependencies
    [tool.briefcase.app.fichero_server].requires        (base bundle deps)
    [tool.briefcase.app.fichero_server.macOS].requires  (macOS-only deps)

and asserts that `requirements.txt` declares exactly that set, with matching
version specifiers, extras, and URL wheels. Comments and blank lines in
requirements.txt are ignored; only the requirement specifiers are compared.

Deliberately NOT part of the compared set (never in pyproject, never expected in
requirements.txt): the heavy AI runtimes the app provisions into separate
managed venvs — kraken, mlx-lm/mlx-vlm, mlx-whisper. They are commented context
in requirements.txt, not requirement lines, so they are invisible here.

Usage:
    scripts/check_requirements_matches_pyproject.py
    scripts/check_requirements_matches_pyproject.py --list
    scripts/check_requirements_matches_pyproject.py --help
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "fichero-server" / "pyproject.toml"
REQUIREMENTS = ROOT / "fichero-server" / "requirements.txt"

# One-liner shown in the failure message.
REGEN_HINT = (
    "Regenerate: edit fichero-server/requirements.txt so its requirement lines "
    "match fichero-server/pyproject.toml (the single source of truth — the union "
    "of [project].dependencies + the two briefcase `requires` blocks). "
    "Then re-run scripts/check_requirements_matches_pyproject.py."
)

# Splits a PEP 508 requirement at the end of the distribution name.
_NAME_END = re.compile(r"[\s\[<>=!~;@]")


def _canonical_name(name: str) -> str:
    """PEP 503 canonical form: lowercase, runs of -_. collapse to a single -."""
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def _parse_requirement(spec: str) -> tuple[str, str] | None:
    """Return (canonical_name, normalized_spec) or None for a blank/comment line.

    The normalized spec keeps extras, version constraints and any URL, with the
    distribution name canonicalized and inner whitespace squeezed, so the two
    sources compare on meaning rather than formatting.
    """
    # Strip a trailing inline comment (`pylance  # provides the lance module`).
    # A leading '#' means the whole line is a comment.
    text = spec.split("#", 1)[0].strip()
    if not text:
        return None
    match = _NAME_END.search(text)
    raw_name = text[: match.start()] if match else text
    remainder = text[len(raw_name):].strip()
    canonical = _canonical_name(raw_name)
    normalized = f"{canonical} {remainder}".strip()
    # Squeeze internal whitespace so `es_core_news_sm @ https://...` compares
    # regardless of spacing around the `@`.
    normalized = re.sub(r"\s+", " ", normalized)
    return canonical, normalized


def _load_pyproject_union() -> tuple[dict[str, str], list[str]]:
    """Union of the three dependency lists; report intra-pyproject conflicts."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data.get("project", {})
    briefcase_app = (
        data.get("tool", {})
        .get("briefcase", {})
        .get("app", {})
        .get("fichero_server", {})
    )
    lists = {
        "[project].dependencies": project.get("dependencies", []),
        "[tool.briefcase.app.fichero_server].requires": briefcase_app.get(
            "requires", []
        ),
        "[tool.briefcase.app.fichero_server.macOS].requires": briefcase_app.get(
            "macOS", {}
        ).get("requires", []),
    }

    union: dict[str, str] = {}
    origin: dict[str, str] = {}
    conflicts: list[str] = []
    for block, entries in lists.items():
        for entry in entries:
            parsed = _parse_requirement(entry)
            if parsed is None:
                continue
            name, normalized = parsed
            if name in union and union[name] != normalized:
                conflicts.append(
                    f"{name}: {origin[name]} says '{union[name]}' but "
                    f"{block} says '{normalized}'"
                )
                continue
            union.setdefault(name, normalized)
            origin.setdefault(name, block)
    return union, conflicts


def _load_requirements() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        parsed = _parse_requirement(line)
        if parsed is None:
            continue
        name, normalized = parsed
        result[name] = normalized
    return result


def main() -> int:
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__)
        return 0

    if not PYPROJECT.exists():
        print(f"ERROR: {PYPROJECT.relative_to(ROOT)} not found")
        return 2
    if not REQUIREMENTS.exists():
        print(f"ERROR: {REQUIREMENTS.relative_to(ROOT)} not found\n{REGEN_HINT}")
        return 1

    expected, conflicts = _load_pyproject_union()
    actual = _load_requirements()

    if "--list" in sys.argv[1:]:
        print(f"pyproject union ({len(expected)} deps):\n")
        for name in sorted(expected):
            print(f"  {expected[name]}")
        return 0

    missing = sorted(name for name in expected if name not in actual)
    extra = sorted(name for name in actual if name not in expected)
    mismatched = sorted(
        name
        for name in expected
        if name in actual and expected[name] != actual[name]
    )

    print("requirements.txt / pyproject sync guardrail:")
    print(f"  pyproject union: {len(expected)} dep(s)")
    print(f"  requirements.txt: {len(actual)} dep(s)")

    if conflicts:
        print(f"\n  {len(conflicts)} intra-pyproject specifier conflict(s):")
        for line in conflicts:
            print(f"      {line}")

    if missing:
        print(f"\n  {len(missing)} in pyproject but MISSING from requirements.txt:")
        for name in missing:
            print(f"      {expected[name]}")

    if extra:
        print(f"\n  {len(extra)} in requirements.txt but NOT in pyproject:")
        for name in extra:
            print(f"      {actual[name]}")

    if mismatched:
        print(f"\n  {len(mismatched)} specifier mismatch(es):")
        for name in mismatched:
            print(f"      pyproject: {expected[name]}")
            print(f"      reqs.txt : {actual[name]}")

    if missing or extra or mismatched or conflicts:
        print(f"\n{REGEN_HINT}")
        return 1

    print("\n✓ requirements.txt matches pyproject's dependency union.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
