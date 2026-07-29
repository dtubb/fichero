#!/usr/bin/env python3
"""Import-everything / render-everything completeness guardrail (#2270).

Rule (reform master plan §N / §H, lines 144-145):

    > Every importable type imports AND every imported type renders in ≥1
    > representation.

The type-system boundary where this is exactly enforceable: the engine assigns
each imported document a `DocType` / `FileType` (`fichero-server/.../models/__init__.py`).
The Swift app decodes those at one canonical point — the `convertFromGenerated*`
switches in `Services/DocumentService.swift` — which map every generated
(== engine) case to a local renderable `DocType` / `FileType`. If the engine can
produce a type that decoder does not handle, the document cannot be classified
and cannot render. So "every imported type renders" reduces to:

    every Python enum case is HANDLED by the decoder switch.

This checks the decoder, not the raw Swift enum case-set, because the decoder
intentionally FOLDS importable types onto a shared representation — e.g.
`case .docx: return .word` ("docx is a Word variant"). docx has no standalone
Swift enum case but IS rendered (as word), so it is covered, not a gap. The
Swift compiler already makes the decoder switch exhaustive over the generated
enum; this guardrail catches the same drift at CI (Python-side), before a build.

The baseline is CLEAN (KNOWN_VIOLATIONS empty): the decoder handles every
importable type today. The script fails when a NEW engine FileType/DocType is
added without a decoder mapping.

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
PY_MODELS = ROOT / "fichero-server" / "src" / "fichero_server" / "models" / "__init__.py"
DECODER = ROOT / "fichero" / "fichero" / "Services" / "DocumentService.swift"
RULE_DOC = "docs/contributor/architecture/fichero/reform_masterplan_2026-06.md"

# Engine enum  ->  the Swift decoder switch that classifies it into a renderer.
ENUM_DECODERS = {
    "DocType": "convertFromGeneratedDocType",
    "FileType": "convertFromGeneratedFileType",
}

# Clean: the decoder handles every importable type (docx folds onto word).
KNOWN_VIOLATIONS: dict[str, str] = {}


def _python_enum_cases(source: str, enum: str) -> set[str]:
    m = re.search(rf"class {enum}\(str, Enum\):(.*?)(?:\nclass |\Z)", source, re.S)
    if not m:
        return set()
    return set(re.findall(r"^\s+([a-z_][a-z0-9_]*)\s*=\s*\"", m.group(1), re.M))


def _swift_handled_cases(source: str, func: str) -> set[str]:
    """The generated-enum case labels handled by a `convertFromGenerated*` switch.

    Extracts the function body (balanced braces from its `{`) and returns every
    `case .x:` label — i.e. the importable types the decoder maps to a renderer.
    """
    start = re.search(rf"func {func}\b[^{{]*\{{", source)
    if not start:
        return set()
    i = start.end() - 1  # at the opening brace
    depth = 0
    for j in range(i, len(source)):
        if source[j] == "{":
            depth += 1
        elif source[j] == "}":
            depth -= 1
            if depth == 0:
                body = source[i : j + 1]
                break
    else:
        body = source[i:]
    return set(re.findall(r"\bcase\s+\.([A-Za-z_][A-Za-z0-9_]*)\s*:", body))


def violations(
    *, py_models: Path = PY_MODELS, decoder: Path = DECODER
) -> dict[str, str]:
    py_src = py_models.read_text(errors="ignore")
    swift_src = decoder.read_text(errors="ignore")
    bad: dict[str, str] = {}
    for enum, func in ENUM_DECODERS.items():
        py = _python_enum_cases(py_src, enum)
        handled = _swift_handled_cases(swift_src, func)
        for case in sorted(py - handled):
            bad[f"{enum}.{case}"] = (
                f"importable {enum}.{case} is not handled by {func}() → cannot render"
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
        swift_src = DECODER.read_text(errors="ignore")
        for enum, func in ENUM_DECODERS.items():
            py = _python_enum_cases(py_src, enum)
            handled = _swift_handled_cases(swift_src, func)
            print(f"{enum}: importable={sorted(py)}")
            print(f"{' ' * len(enum)}  {func}() handles={sorted(handled)}")
            print(f"{' ' * len(enum)}  unhandled (unrenderable)={sorted(py - handled)}")
        return 0

    new = sorted(set(bad) - known)
    stale = sorted(known - set(bad))

    print("Import/render completeness guardrail (#2270):")
    print(f"  checked {', '.join(ENUM_DECODERS)} against their decoder switches")
    print(f"  {len(bad)} importable type(s) the decoder cannot render; {len(known)} known.")

    if new:
        print(f"\n  ✗ {len(new)} NEW importable type(s) that cannot render:")
        for key in new:
            print(f"      {key}  ←  {bad[key]}")
        print(
            "\nFix: map the importable type to a renderer in the convertFromGenerated* "
            f"switch in DocumentService.swift. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entr(ies) now render — drop them:")
        for key in stale:
            print(f"      {key}")

    print("\n✓ Every importable type is handled by the decoder (renders in ≥1 representation).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
