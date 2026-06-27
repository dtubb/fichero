#!/usr/bin/env python3
"""Import-everything / render-everything completeness guardrail (#2270).

Rule (reform master plan §N / §H, lines 144-145):

    > Every importable type imports AND every imported type renders in ≥1
    > representation.

The type-system boundary where this is exactly enforceable: the engine assigns
each imported document a `DocType` / `FileType` (`fichero-engine/.../models.py`),
and the Swift app decodes those into its own `DocType` / `FileType` enums
(`Models/Document.swift`, explicitly "matching Python …") to pick a renderer. If
the engine can produce a type the Swift enum has no case for, that document
**cannot be classified and cannot render** — a `Codable` decode of the unknown
raw value fails. So "every imported type renders" reduces to:

    every Python enum case has a matching Swift enum case  (Python ⊆ Swift).

(The reverse — Swift cases with no Python producer, e.g. `json`/`csv`/`rtf` — is
fine: the client may render more than the importer emits.)

`KNOWN_VIOLATIONS` seeds the CURRENT drift so the script passes today and fails
only when a NEW importable type is added without a Swift representation.

Usage:
    scripts/check_import_render_completeness.py
    scripts/check_import_render_completeness.py --list
    scripts/check_import_render_completeness.py --help
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_MODELS = ROOT / "fichero-engine" / "src" / "fichero" / "models.py"
SWIFT_MODELS = ROOT / "fichero" / "fichero" / "Models" / "Document.swift"
RULE_DOC = "docs/architecture/swiftui/reform_masterplan_2026-06.md"

# Enums that classify imported documents into a renderable type. Each must be
# Python ⊆ Swift: an importable type with no Swift case cannot render.
ENUMS = ("DocType", "FileType")

# Current drift baseline — `<Enum>.<case>` present in Python, missing in Swift.
KNOWN_VIOLATIONS: dict[str, str] = {
    "FileType.docx": (
        "engine emits FileType.docx; Swift FileType has only `word` (no `docx`) "
        "— add a Swift case or fold docx→word in the decoder"
    ),
}


def _python_enum_cases(source: str, enum: str) -> set[str]:
    m = re.search(rf"class {enum}\(str, Enum\):(.*?)(?:\nclass |\Z)", source, re.S)
    if not m:
        return set()
    return set(re.findall(r"^\s+([a-z_][a-z0-9_]*)\s*=\s*\"", m.group(1), re.M))


def _swift_enum_cases(source: str, enum: str) -> set[str]:
    m = re.search(rf"enum {enum}:[^{{]*\{{(.*?)\n\}}", source, re.S)
    if not m:
        # Fall back: stop at the first `var ` (computed property) after the cases.
        m = re.search(rf"enum {enum}:[^{{]*\{{(.*?)\n\s+var ", source, re.S)
    if not m:
        return set()
    return set(re.findall(r"^\s+case\s+([A-Za-z_][A-Za-z0-9_]*)", m.group(1), re.M))


def violations(
    *, py_models: Path = PY_MODELS, swift_models: Path = SWIFT_MODELS
) -> dict[str, str]:
    py_src = py_models.read_text(errors="ignore")
    swift_src = swift_models.read_text(errors="ignore")
    bad: dict[str, str] = {}
    for enum in ENUMS:
        py = _python_enum_cases(py_src, enum)
        sw = _swift_enum_cases(swift_src, enum)
        for case in sorted(py - sw):
            bad[f"{enum}.{case}"] = (
                f"importable {enum}.{case} has no matching Swift case → cannot render"
            )
    return bad


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    bad = violations()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in argv:
        py_src = PY_MODELS.read_text(errors="ignore")
        swift_src = SWIFT_MODELS.read_text(errors="ignore")
        for enum in ENUMS:
            py = _python_enum_cases(py_src, enum)
            sw = _swift_enum_cases(swift_src, enum)
            print(f"{enum}: python={sorted(py)}")
            print(f"{' ' * len(enum)}  swift ={sorted(sw)}")
            print(f"{' ' * len(enum)}  python-only (unrenderable)={sorted(py - sw)}")
            print(f"{' ' * len(enum)}  swift-only (extra renderers)={sorted(sw - py)}")
        return 0

    new = sorted(set(bad) - known)
    stale = sorted(known - set(bad))

    print("Import/render completeness guardrail (#2270):")
    print(f"  checked enums {', '.join(ENUMS)} (Python ⊆ Swift)")
    print(f"  {len(bad)} importable type(s) with no Swift representation; {len(known)} known.")

    if new:
        print(f"\n  ✗ {len(new)} NEW importable type(s) that cannot render:")
        for key in new:
            print(f"      {key}  ←  {bad[key]}")
        print(
            "\nFix: add the matching case to the Swift enum in Models/Document.swift "
            f"(or map it in the decoder). Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entr(ies) now render — drop them:")
        for key in stale:
            print(f"      {key}")

    print("\n✓ Every importable type has a Swift representation (beyond the seeded baseline).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
