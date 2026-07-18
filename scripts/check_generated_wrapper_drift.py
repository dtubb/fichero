#!/usr/bin/env python3
"""Generated-OpenAPI wrapper drift guardrail (#2660).

The hand-written service wrappers (`fichero/fichero/Services/*Generated.swift` —
hand-written despite the suffix, editable per constitution rule #3) reference
generated types by a hardcoded Swift identifier, e.g.:

    Components.Schemas.FicheroKnowledgeKnowledgeModelsEntityType

There is NO compile-time link between the wrapper and the generated enum, so when
the backend renames a Pydantic schema (module-path change → OpenAPI title change →
`namingStrategy: idiomatic` produces a different Swift name) the wrapper silently
references a type that no longer exists. This broke the Release build on
2026-06-26: a wrapper referenced `FicheroKnowledgeModelsEntityType` after the
schema became `fichero__knowledge__knowledge_models__EntityType`
(→ `FicheroKnowledgeKnowledgeModelsEntityType`). The drift was caught only at the
Release build, not at CI.

This guardrail closes that gap with pure static analysis (no Swift build):

  1. Parse the canonical OpenAPI contract (openapi.json) and compute the
     swift-openapi-generator *idiomatic* Swift name for every component schema.
  2. Extract every `Components.Schemas.<Name>` reference from the hand-written
     `*Generated.swift` wrappers.
  3. A reference whose `<Name>` is not a derivable schema name is drift.

The baseline is CLEAN (KNOWN_VIOLATIONS empty): the wrappers currently compile,
so every referenced name must resolve. The script fails the moment a wrapper
references a name no current schema produces.

Usage:
    scripts/check_generated_wrapper_drift.py
    scripts/check_generated_wrapper_drift.py --list
    scripts/check_generated_wrapper_drift.py --help
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WRAPPERS_DIR = ROOT / "fichero" / "fichero" / "Services"
OPENAPI_JSON = (
    ROOT / "fichero" / "fichero-api-client" / "Sources" / "FicheroAPIClient" / "openapi.json"
)
RULE_DOC = "docs/contributor/architecture/fichero/reform_masterplan_2026-06.md"

_REF_RE = re.compile(r"Components\.Schemas\.([A-Za-z0-9_]+)")
# Word splitter: acronym run, CamelCase word, lowercase/number run, digit run.
_WORD_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+|[0-9]+")

# Drift baseline. Empty: the wrappers compile today, so every referenced name
# must resolve to a current schema. A populated entry here would mean shipping a
# known-broken reference — don't. Keys are `relpath::TypeName`.
KNOWN_VIOLATIONS: dict[str, str] = {}


def idiomatic(name: str) -> str:
    """Reproduce swift-openapi-generator `namingStrategy: idiomatic`.

    Splits on non-alphanumeric separators (``_``, ``.``, ``-``) and on
    CamelCase / acronym boundaries, then UpperCamelCase-joins. Verified against
    the #2660 regression: ``fichero__knowledge__knowledge_models__EntityType``
    → ``FicheroKnowledgeKnowledgeModelsEntityType``.
    """
    words: list[str] = []
    for chunk in re.split(r"[^A-Za-z0-9]+", name):
        if chunk:
            words.extend(_WORD_RE.findall(chunk))
    return "".join(w[:1].upper() + w[1:] for w in words)


def expected_names(openapi_json: Path = OPENAPI_JSON) -> set[str]:
    spec = json.loads(openapi_json.read_text())
    schemas = spec.get("components", {}).get("schemas", {})
    return {idiomatic(key) for key in schemas}


def scan_references(wrappers_dir: Path = WRAPPERS_DIR) -> dict[str, str]:
    """Map `relpath::TypeName` -> the raw referenced name."""
    found: dict[str, str] = {}
    for path in sorted(wrappers_dir.glob("*Generated.swift")):
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        try:
            rel = path.relative_to(ROOT).as_posix()
        except ValueError:
            rel = path.name
        for name in _REF_RE.findall(source):
            found[f"{rel}::{name}"] = name
    return found


def violations(
    *, wrappers_dir: Path = WRAPPERS_DIR, openapi_json: Path = OPENAPI_JSON
) -> dict[str, str]:
    valid = expected_names(openapi_json)
    refs = scan_references(wrappers_dir)
    return {key: name for key, name in refs.items() if name not in valid}


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    if not OPENAPI_JSON.exists():
        print(f"✗ OpenAPI contract not found: {OPENAPI_JSON}")
        return 1

    refs = scan_references()
    bad = violations()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in argv:
        valid = expected_names()
        print(f"Wrapper schema references ({len(refs)}), {len(valid)} schemas in contract:\n")
        for key, name in sorted(refs.items()):
            tag = "DRIFT" if key in bad else "ok"
            print(f"  [{tag}] {key}")
        return 0

    new = sorted(set(bad) - known)
    stale = sorted(known - set(bad))

    print("Generated-wrapper drift guardrail (#2660):")
    print(f"  {len(refs)} Components.Schemas.* reference(s) in *Generated.swift")
    print(f"  {len(bad)} unresolved; {len(known)} known.")

    if new:
        print(f"\n  ✗ {len(new)} reference(s) to a type no current schema produces:")
        for key in new:
            print(f"      {key}  ←  Components.Schemas.{bad[key]}")
        print(
            "\nFix: the backend schema was renamed (module-path → OpenAPI title → "
            "idiomatic Swift name changed). Update the wrapper to the new "
            f"Components.Schemas.* name, then regenerate the client. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entr(ies) now resolve — drop them:")
        for key in stale:
            print(f"      {key}")

    print("\n✓ Every wrapper schema reference resolves to a current OpenAPI schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
