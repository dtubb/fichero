#!/usr/bin/env python3
"""Guardrail for Swift OpenAPI typed fields hidden in additionalProperties.

Swift service wrappers must set fields declared in the committed OpenAPI schema
through generated typed initializers. Putting those same keys into
``additionalProperties`` can round-trip on the wire while being ignored by the
backend Pydantic model.

This checker is deliberately conservative:
- scans Swift service files only
- reads declared component schema properties from the committed OpenAPI JSON
- reports only literal dictionary keys that exactly match declared schema fields
  for the referenced ``Components.Schemas.*`` model
- ignores known dynamic map payloads such as metadata, filters, config, inputs,
  params, and source_metadata

Usage:
    scripts/check_openapi_typed_fields.py
    scripts/check_openapi_typed_fields.py --list
    scripts/check_openapi_typed_fields.py --help
"""
from __future__ import annotations

import json
import re
import sys

from _check_floor import require_scan_floor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OPENAPI_SCHEMA = ROOT / "fichero-server" / "tests" / "contracts" / "openapi.json"
SWIFT_SERVICES = ROOT / "fichero" / "fichero" / "Services"

DYNAMIC_MAP_TERMS = {
    "additional",
    "attributes",
    "config",
    "dynamic",
    "extra",
    "filters",
    "inputs",
    "metadata",
    "params",
    "pinned_inputs",
    "source_metadata",
    "tool_config",
}

SCHEMA_CTOR_RE = re.compile(
    r"(?:Components\.Schemas\.(?P<direct>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)|"
    r"(?P<shorthand>\.init))\s*\("
)
TYPE_ANNOTATION_RE = re.compile(
    r":\s*Components\.Schemas\.(?P<schema>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\??"
)
STRING_KEY_RE = re.compile(r'"(?P<key>[^"\\]*(?:\\.[^"\\]*)*)"\s*:')
ARG_VALUE_RE = re.compile(
    r"additionalProperties\s*:\s*(?P<value>[A-Za-z_][A-Za-z0-9_]*|\[|OpenAPIObjectContainer\s*\()"
)


@dataclass(frozen=True)
class Offender:
    rel_path: str
    line: int
    schema: str
    key: str

    @property
    def identifier(self) -> str:
        return f"{self.rel_path}:{self.line}:{self.schema}:{self.key}"


def _strip_swift_comments(source: str) -> str:
    def blank_block(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    without_blocks = re.sub(r"/\*.*?\*/", blank_block, source, flags=re.DOTALL)
    return "\n".join(re.sub(r"(?<!:)//.*", "", line) for line in without_blocks.splitlines())


def _line_number(source: str, index: int) -> int:
    return source.count("\n", 0, index) + 1


def _find_matching_paren(source: str, open_index: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(open_index, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _find_statement_start(source: str, index: int) -> int:
    starts = [source.rfind(token, 0, index) for token in ("\n\n", "\n    let ", "\n    var ", "\n        let ", "\n        var ")]
    start = max(starts)
    return 0 if start < 0 else start + 1


def _schema_basename(schema: str) -> str:
    return schema.split(".")[-1]


def _schema_lookup_name(schema: str) -> str:
    return schema.split(".")[0]


def _is_dynamic_schema(schema: str) -> bool:
    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|[0-9]+", schema)
    terms = {part.lower() for part in parts}
    terms.add(_schema_basename(schema).lower())
    if "." in schema and _schema_basename(schema).lower().endswith("payload"):
        return True
    return bool(terms & DYNAMIC_MAP_TERMS)


def _literal_keys(source: str) -> set[str]:
    return {match.group("key").encode("utf-8").decode("unicode_escape") for match in STRING_KEY_RE.finditer(source)}


def _nearby_variable_keys(source: str, constructor_start: int, variable: str) -> set[str]:
    window_start = max(0, source.rfind("\n", 0, constructor_start - 1200))
    window = source[window_start:constructor_start]
    assignment = re.search(
        rf"(?:let|var)\s+{re.escape(variable)}\b[^=]*=\s*(?P<body>.*)\Z",
        window,
        flags=re.DOTALL,
    )
    if not assignment:
        return set()
    return _literal_keys(assignment.group("body"))


def _schema_for_constructor(source: str, match: re.Match[str]) -> str | None:
    direct = match.group("direct")
    if direct:
        return direct
    statement_start = _find_statement_start(source, match.start())
    context = source[statement_start : match.start()]
    annotations = list(TYPE_ANNOTATION_RE.finditer(context))
    if not annotations:
        return None
    return annotations[-1].group("schema")


def load_schema_properties(path: Path = OPENAPI_SCHEMA) -> dict[str, set[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    schemas: dict[str, Any] = data.get("components", {}).get("schemas", {})
    properties: dict[str, set[str]] = {}
    for name, schema in schemas.items():
        props = schema.get("properties") if isinstance(schema, dict) else None
        if isinstance(props, dict) and props:
            properties[name] = set(props)
    return properties


def scan_source(source: str, rel_path: str, schema_properties: dict[str, set[str]]) -> list[Offender]:
    clean = _strip_swift_comments(source)
    offenders: list[Offender] = []

    for match in SCHEMA_CTOR_RE.finditer(clean):
        open_index = clean.find("(", match.start())
        close_index = _find_matching_paren(clean, open_index)
        if close_index is None:
            continue

        block = clean[open_index : close_index + 1]
        if "additionalProperties" not in block:
            continue

        schema = _schema_for_constructor(clean, match)
        if schema is None or _is_dynamic_schema(schema):
            continue

        declared = schema_properties.get(_schema_lookup_name(schema))
        if not declared:
            continue

        keys = _literal_keys(block)
        arg_match = ARG_VALUE_RE.search(block)
        if arg_match and re.match(r"[A-Za-z_]", arg_match.group("value")):
            keys |= _nearby_variable_keys(clean, match.start(), arg_match.group("value"))

        for key in sorted(keys & declared):
            offenders.append(
                Offender(
                    rel_path=rel_path,
                    line=_line_number(clean, match.start()),
                    schema=schema,
                    key=key,
                )
            )

    return sorted(offenders, key=lambda item: (item.rel_path, item.line, item.schema, item.key))


def swift_service_files(root: Path = SWIFT_SERVICES) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*.swift"))


def scan(
    root: Path | None = None,
    schema_path: Path | None = None,
    services_root: Path | None = None,
) -> list[Offender]:
    root = ROOT if root is None else root
    schema_path = OPENAPI_SCHEMA if schema_path is None else schema_path
    services_root = SWIFT_SERVICES if services_root is None else services_root
    schema_properties = load_schema_properties(schema_path)
    offenders: list[Offender] = []
    for path in swift_service_files(services_root):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel_path = path.relative_to(root).as_posix()
        offenders.extend(scan_source(source, rel_path, schema_properties))
    return offenders


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    offenders = scan()
    if "--list" in sys.argv[1:]:
        print(f"OpenAPI typed-field guardrail offenders ({len(offenders)} location(s)):\n")
        for offender in offenders:
            print(f"  {offender.identifier}")
        return 0

    # #4487 scan floor: on files ENUMERATED (offenders at zero is the goal).
    require_scan_floor(
        len(swift_service_files()), 40, "Swift service files (~90 on 2026-08-02)"
    )
    print("OpenAPI typed-field guardrail: scanned Swift service files")
    print(f"  {len(offenders)} offender location(s).")
    if not offenders:
        print("\nOK: no declared OpenAPI schema fields found in additionalProperties payloads.")
        return 0

    print("\nDeclared OpenAPI fields must use generated typed initializers, not additionalProperties:")
    for offender in offenders:
        print(
            f"  {offender.rel_path}:{offender.line} "
            f"{offender.schema}.additionalProperties contains declared field {offender.key!r}"
        )
    print("\nFix: pass these keys through the generated schema fields instead.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
