"""Refuse a dev venv that cannot run the engine's jobs (#5493). Dev launcher only; never shipped.

start_fichero_server.sh runs this with the Python it picked, before it starts anything. It reads the
distribution names in requirements.txt (the generated union of what the bundle ships), adds the
dev-only runtimes the canonical dev venv also carries, and asks the interpreter's own installed
metadata for each. Any missing: it names the venv, the missing distributions and the two fixes, and
exits 1. A stale per-worktree venv used to start an engine that then failed every Kraken, spaCy and
language-search job while health said nothing was missing.

Usage: python dev_venv_preflight.py <requirements.txt> [extra-dist ...]
Standard library only: it must run in a venv that is missing things.
"""
from __future__ import annotations

import importlib.metadata
import re
import sys
from pathlib import Path

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def distribution_name(line: str) -> str | None:
    """The distribution a requirements line installs, or None for a comment, blank or option line."""
    line = line.split(" #", 1)[0].strip()
    if not line or line.startswith(("#", "-")):
        return None
    if "#egg=" in line:  # a bare URL naming its package
        return line.split("#egg=", 1)[1].split("&", 1)[0].strip() or None
    if line.split(":", 1)[0] in {"http", "https", "file"} or line.startswith("git+"):
        # A bare wheel URL: the distribution is the wheel filename's first field.
        return line.rsplit("/", 1)[-1].split("-", 1)[0] or None
    match = _NAME.match(line)  # `name @ url`, `name[extra]>=1; marker` -> name
    return match.group(0) if match else None


def required_distributions(requirements: Path, extra: list[str]) -> list[str]:
    names = [n for n in map(distribution_name, requirements.read_text().splitlines()) if n]
    return list(dict.fromkeys([*names, *extra]))


def missing_distributions(names: list[str]) -> list[str]:
    missing = []
    for name in names:
        try:
            importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(name)
    return missing


def main(argv: list[str]) -> int:
    requirements, extra = Path(argv[0]), argv[1:]
    missing = missing_distributions(required_distributions(requirements, extra))
    if not missing:
        return 0
    # The dev-only runtimes are not in requirements.txt, so `-r` alone does not bring them back.
    dev_only = [name for name in missing if name in extra]
    also = f"\n      uv pip install --python {sys.executable} {' '.join(dev_only)}" if dev_only else ""
    print(
        f"Refusing to start the engine: the Python it picked ({sys.executable}) cannot run its jobs.\n"
        f"Missing: {', '.join(missing)}\n"
        "Fix it one of two ways:\n"
        "  - use the canonical dev venv:\n"
        "      FICHERO_PYTHON_BIN=~/code/fichero/.venv/bin/python fichero-server/scripts/start_fichero_server.sh ...\n"
        "  - or install what is missing into this venv:\n"
        f"      uv pip install --python {sys.executable} -r {requirements}{also}\n"
        "(CI only: FICHERO_SKIP_VENV_CHECK=1 skips this check.)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
