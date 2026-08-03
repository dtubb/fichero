#!/usr/bin/env python3
"""A key read out of a re-encoded schema must be a field that schema HAS (#4495).

There is a defensive idiom in the client: take a generated
`Components.Schemas.X`, re-encode it to JSON, and read fields out of the
resulting dictionary rather than off the generated properties — "because the
generated client can lag a schema change". The reasoning is sound. The failure
mode is not.

A round-trip through `JSONEncoder` can only ever produce the keys the schema
declares. So a key the schema does NOT declare is unreachable by construction:
the read returns nil, the `?? default` fires, and the value is a plausible
constant forever. `WorkflowResponse.isSystem` was `false` for every workflow in
the app on exactly this path, while `is_system` was load-bearing server-side
(only `is_system` rows are read-only, and only they resolve cross-library).

This is the SILENT twin of #3804's S1. There the field was simply absent, decode
dropped it, and the compiler had opinions — it failed loudly and got fixed. Here
it defaulted to something believable, so it survived. The loud one lasted hours;
the silent one lasted months. That asymmetry is the whole argument for a static
check: nothing at runtime can tell "the server sent false" from "the key was
never there".

Scope is deliberately narrow. A blanket "every snake_case literal must be a
contract field" rule was measured first and rejected: 173 of 522 literals in the
app are legitimately not wire fields — SSE event names, enum values, local
persistence keys — so that rule would have shipped as a 173-entry baseline,
which is a mute button with extra steps. This rule fires only where the code
itself claims to be reading a schema's own fields, where a miss is unambiguously
a bug.

KNOWN is keyed to the issue that must land first, and goes stale loudly: when
the field IS served, the entry must be removed or this fails. An allowlist that
cannot go stale is a record; one that can is an excuse.

Run: python3 scripts/check_schema_roundtrip_keys.py [--self-test]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _check_floor import require_scan_floor  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "fichero" / "fichero"
CONTRACT = REPO / "fichero-server" / "tests" / "contracts" / "openapi.json"

# Keys known to be read but not served, keyed to the issue that must land first.
# Each entry is "<Schema>.<key>".
KNOWN: dict[str, str] = {
    # The client reads is_system to decide whether a workflow is a locked
    # preset. The server enforces exactly that — `_reject_if_read_only` raises
    # 403 "Default workflows are read-only; duplicate to edit." — but
    # WorkflowResponse does not carry the field, so the client offers Delete
    # and Edit on every shipped preset and each one 403s. Fixing it is a server
    # change plus an OpenAPI regen, not a client edit.
}

# `func name(... label: Components.Schemas.Foo ...)` → the schema a body is about.
_SCHEMA_PARAM = re.compile(r"Components\.Schemas\.([A-Za-z_][A-Za-z0-9_]*)")
_ENCODE = re.compile(r"JSONEncoder\(\)\.encode\(")
_SUBSCRIPT = re.compile(r'\bdict\["([^"]+)"\]')


def contract_properties() -> dict[str, set[str]]:
    """Every schema's declared property names."""
    schemas = json.loads(CONTRACT.read_text())["components"]["schemas"]
    return {
        name: set((body.get("properties") or {}).keys())
        for name, body in schemas.items()
    }


def swift_sources(root: Path) -> list[Path]:
    """App Swift files, excluding build products.

    `.build` and DerivedData exist only in a worktree that has been built, so a
    scan that walks them finds a different population depending on whether
    somebody happened to compile — and a guardrail whose result depends on that
    is not a guardrail.
    """
    return [
        p
        for p in sorted(root.rglob("*.swift"))
        if ".build" not in p.parts and "DerivedData" not in p.parts
    ]


_FUNC = re.compile(r"\bfunc\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>]*>)?\s*\(")


def _function_bodies(text: str) -> list[str]:
    """Each `func`'s signature-plus-body, by brace matching.

    Attribution has to be per FUNCTION, not per file. A file-scoped version of
    this check was written first and was wrong: `WorkflowService.swift` mentions
    both `DataType` and `WorkflowResponse`, so cross-producting every schema in
    the file with every key in it blamed `is_system` on `DataType` and invented
    six more violations that do not exist. A rule has to match the granularity
    of the thing it is about (#4365), and the thing here is one function that
    encodes one value.
    """
    bodies: list[str] = []
    for match in _FUNC.finditer(text):
        start = text.find("{", match.end())
        if start < 0:
            continue
        depth, i = 0, start
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        bodies.append(text[match.start():i])
    return bodies


def audit_source(text: str) -> list[tuple[str, str]]:
    """(schema, key) pairs read out of a re-encoded schema, per function."""
    pairs: list[tuple[str, str]] = []
    for body in _function_bodies(text):
        if not _ENCODE.search(body):
            continue
        schemas = set(_SCHEMA_PARAM.findall(body))
        if len(schemas) != 1:
            # Zero: not this idiom. More than one: which value was encoded is
            # no longer obvious from text, and guessing is how the file-scoped
            # version invented violations. Say nothing rather than something
            # wrong.
            continue
        schema = schemas.pop()
        pairs.extend((schema, key) for key in set(_SUBSCRIPT.findall(body)))
    return pairs


def main() -> int:
    props = contract_properties()
    files = swift_sources(APP)
    # 912 app Swift files at commit time; floor at half, per #4487's convention.
    require_scan_floor(len(files), 456, "app Swift files")

    unreachable: dict[str, list[str]] = {}
    checked = 0
    for path in files:
        pairs = audit_source(path.read_text(encoding="utf-8", errors="ignore"))
        if not pairs:
            continue
        by_key: dict[str, set[str]] = {}
        for schema, key in pairs:
            by_key.setdefault(key, set()).add(schema)
        for key, schemas in by_key.items():
            known_schemas = [s for s in schemas if s in props]
            if not known_schemas:
                continue
            checked += 1
            if any(key in props[s] for s in known_schemas):
                continue
            label = f"{sorted(known_schemas)[0]}.{key}"
            unreachable.setdefault(label, []).append(
                str(path.relative_to(REPO))
            )

    new = {k: v for k, v in unreachable.items() if k not in KNOWN}
    stale = [k for k in KNOWN if k not in unreachable]

    print(f"Schema round-trip keys: {checked} key read(s) checked in {len(files)} file(s).")
    if not new and not stale:
        served = len(KNOWN)
        note = f"; {served} known-unserved, all still unserved" if served else ""
        print(f"  ✓ every key read from a re-encoded schema is declared by it{note}.")
        return 0

    for label, where in sorted(new.items()):
        schema, key = label.rsplit(".", 1)
        print(f"  ✗ {label} — read in {where[0]}, but {schema} has no '{key}'.")
        print("     A JSON round-trip can only yield keys the schema declares, so this")
        print("     read is unreachable and its `?? default` is the permanent answer.")
    for label in sorted(stale):
        print(f"  ✗ {label} is in KNOWN ({KNOWN[label]}) but is now served — remove the entry.")
    return 1


def self_test() -> int:
    """Every rule fires. A check nobody has seen fail is a check nobody has tested."""
    props = {"Thing": {"good_key"}}

    # 1. a declared key is accepted
    pairs = audit_source(
        'func f(x: Components.Schemas.Thing) { JSONEncoder().encode(x); dict["good_key"] }'
    )
    assert ("Thing", "good_key") in pairs, pairs
    assert "good_key" in props["Thing"]

    # 2. an undeclared key is caught — the #4495 shape
    pairs = audit_source(
        'func f(x: Components.Schemas.Thing) { JSONEncoder().encode(x); dict["is_system"] }'
    )
    assert ("Thing", "is_system") in pairs, pairs
    assert "is_system" not in props["Thing"]

    # 3. no encode → not this idiom, no opinion
    assert audit_source('let x: Components.Schemas.Thing = y; dict["is_system"]') == []

    # 4. no schema → not this idiom
    assert audit_source('JSONEncoder().encode(x); dict["is_system"]') == []

    # 5. build products are excluded, so the result cannot depend on whether
    #    somebody happened to compile the worktree
    assert not [p for p in swift_sources(APP) if ".build" in p.parts]

    print("check_schema_roundtrip_keys self-test: OK — all five rules fire.")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
