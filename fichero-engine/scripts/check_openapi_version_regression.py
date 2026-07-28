#!/usr/bin/env python3
"""Abort an OpenAPI sync that would move ``info.version`` BACKWARDS (#4199).

`sync_openapi_schema.sh` picks its interpreter from a fallback chain. When it
resolves to a partially-installed env, the exported spec carries that env's
placeholder version (e.g. `0.1.0.dev1`) instead of the real one, and the sync
rewrites `info.version` across all four committed `openapi.json` copies. That
is one line inside a large generated diff — invisible in review — and it
surfaces much later as a Release-build failure when the generated client
disagrees with the engine.

A legitimate release only ever moves the version FORWARD, so refusing a
backwards move costs nothing and catches exactly the failure case.

Usage:
    check_openapi_version_regression.py --previous OLD.json --current NEW.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_NUMERIC = re.compile(r"^\d+$")


def read_version(path: Path) -> str | None:
    """Return ``info.version``, or None when unreadable.

    An unreadable/absent previous copy is NOT a regression — a first-ever
    export has nothing to compare against.
    """
    try:
        return json.loads(path.read_text()).get("info", {}).get("version")
    except (OSError, ValueError):
        return None


def _release_tuple(version: str) -> tuple[int, ...]:
    """Leading dotted-numeric components, e.g. '2026.7.20b1' -> (2026, 7, 20)."""
    parts: list[int] = []
    for chunk in version.split("."):
        if _NUMERIC.match(chunk):
            parts.append(int(chunk))
            continue
        # Trailing chunk like '20b1' — keep its numeric prefix, then stop.
        lead = re.match(r"^(\d+)", chunk)
        if lead:
            parts.append(int(lead.group(1)))
        break
    return tuple(parts)


def is_regression(previous: str | None, current: str | None) -> bool:
    """True when `current` is strictly older than `previous`."""
    if not previous or not current or previous == current:
        return False
    try:
        # packaging understands pre/dev/post ordering; it is not guaranteed to
        # be importable under whichever interpreter the sync resolved, so the
        # release-tuple comparison below stands in when it is missing.
        from packaging.version import InvalidVersion, Version

        try:
            return Version(current) < Version(previous)
        except InvalidVersion:
            pass
    except ImportError:
        pass
    return _release_tuple(current) < _release_tuple(previous)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    args = parser.parse_args()

    previous = read_version(args.previous)
    current = read_version(args.current)

    if is_regression(previous, current):
        print(
            f"✖ OpenAPI version regression: {previous} -> {current}\n"
            "  The exported spec is OLDER than the committed one, which means the\n"
            "  sync used the wrong interpreter. Re-run with an explicit venv:\n"
            "    FICHERO_PYTHON_BIN=/path/to/.venv/bin/python "
            "./fichero-engine/scripts/sync_openapi_schema.sh",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
