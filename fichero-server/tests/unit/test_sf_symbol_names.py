"""Static lint: every SF Symbol name referenced in Swift source must exist.

Layer 3 of the #1017 test-coverage plan. Catches #1015-class bugs — empty
``systemName: ""`` strings and invented names like ``"pickaxe"`` that don't
exist in the SF Symbols catalog — at test time instead of as blank glyphs
or console spam at runtime.

The catalog is read from the OS itself (CoreGlyphs.bundle), so it stays
accurate as macOS ships new symbols. On a machine without the bundle
(non-macOS CI) the test skips rather than failing on a stale snapshot.
"""

from __future__ import annotations

import plistlib
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SWIFT_ROOT = _REPO_ROOT / "fichero" / "fichero"

_COREGLYPHS = Path(
    "/System/Library/CoreServices/CoreGlyphs.bundle/Contents/Resources"
)

# `systemName:` (Image) and `systemImage:` (Label, button initialisers) are
# the only call sites that take an SF Symbol name. A static string literal is
# lintable; a variable (`systemName: icon`) is skipped — it can't be checked
# without running the app.
_SYMBOL_LITERAL = re.compile(r'(?:systemName|systemImage)\s*:\s*"([^"]*)"')

# Generated/derived trees that mirror source but aren't hand-edited.
_EXCLUDED_PARTS = {"build", ".build", "DerivedData", "Pods"}


def _load_catalog() -> set[str] | None:
    """All valid SF Symbol names from the OS catalog, plus legacy aliases."""
    availability = _COREGLYPHS / "name_availability.plist"
    if not availability.is_file():
        return None
    with availability.open("rb") as handle:
        names = set(plistlib.load(handle)["symbols"])
    aliases = _COREGLYPHS / "name_aliases.strings"
    if aliases.is_file():
        with aliases.open("rb") as handle:
            alias_map = plistlib.load(handle)
        names |= set(alias_map.keys()) | set(alias_map.values())
    return names


def _swift_files() -> list[Path]:
    return [
        path
        for path in _SWIFT_ROOT.rglob("*.swift")
        if _EXCLUDED_PARTS.isdisjoint(path.parts)
    ]


def test_sf_symbol_names_are_valid() -> None:
    catalog = _load_catalog()
    if catalog is None:
        pytest.skip("SF Symbols catalog (CoreGlyphs.bundle) not available")

    assert _SWIFT_ROOT.is_dir(), f"Swift source root not found: {_SWIFT_ROOT}"

    bad: list[str] = []
    for path in _swift_files():
        rel = path.relative_to(_REPO_ROOT)
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for name in _SYMBOL_LITERAL.findall(line):
                if not name.strip():
                    bad.append(f"{rel}:{lineno}: empty SF Symbol name")
                elif name not in catalog:
                    bad.append(f"{rel}:{lineno}: unknown SF Symbol {name!r}")

    assert not bad, "Invalid SF Symbol names:\n  " + "\n  ".join(bad)
