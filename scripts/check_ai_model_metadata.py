#!/usr/bin/env python3
"""Guardrail for typed AI/model metadata in backend provider adapters.

Prevents regressions like #2194 where raw dict payloads from
``TextEmbedding.list_supported_models()`` were fed into
``TextEmbedding.add_custom_model()``, which expects typed FastEmbed model
description objects with attributes like ``.sources``.

This guardrail stays narrow on purpose:
- scans only selected backend AI/model infrastructure files
- flags dict-returning ``TextEmbedding.list_supported_models()`` in
  custom-model registration contexts
- flags raw dict subscripting of load-bearing metadata keys that should stay
  typed across adapter boundaries

Usage:
    scripts/check_ai_model_metadata.py
    scripts/check_ai_model_metadata.py --list
    scripts/check_ai_model_metadata.py --help
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET_FILES = (
    "fichero-server/src/fichero_server/db/embeddings.py",
    "fichero-server/src/fichero_server/llm/__init__.py",
    "fichero-server/src/fichero_server/llm/embeddings.py",
    "fichero-server/src/fichero_server/llm/providers.py",
)
METADATA_KEYS = {
    "sources",
    "model_file",
    "dim",
    "size_in_GB",
    "size_in_gb",
}
RULE_DOC = "#2196"

# Empty today. Add only when the usage is intentionally dict-based and cannot be
# expressed with a typed adapter object.
ALLOWLIST: dict[str, str] = {}


@dataclass(frozen=True)
class Offender:
    rel_path: str
    line: int
    rule: str
    detail: str

    @property
    def key(self) -> str:
        return f"{self.rel_path}:{self.line}:{self.rule}"


def _string_literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_text_embedding_attr(node: ast.AST, attr: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == attr
        and isinstance(node.value, ast.Name)
        and node.value.id == "TextEmbedding"
    )


def _function_list_supported_model_offenders(
    node: ast.AST,
    rel_path: str,
) -> list[Offender]:
    add_custom_model_calls: list[ast.Call] = []
    list_supported_calls: list[ast.Call] = []

    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if _is_text_embedding_attr(child.func, "add_custom_model"):
            add_custom_model_calls.append(child)
        if _is_text_embedding_attr(child.func, "list_supported_models"):
            list_supported_calls.append(child)

    if not add_custom_model_calls or not list_supported_calls:
        return []

    return [
        Offender(
            rel_path=rel_path,
            line=call.lineno,
            rule="list_supported_models_in_custom_registration",
            detail=(
                "TextEmbedding.list_supported_models() returns dict payloads; use "
                "TextEmbedding._list_supported_models() or a typed adapter helper "
                "before add_custom_model()."
            ),
        )
        for call in list_supported_calls
    ]


def scan_source(source: str, rel_path: str) -> list[Offender]:
    tree = ast.parse(source, filename=rel_path)
    offenders: list[Offender] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            offenders.extend(_function_list_supported_model_offenders(node, rel_path))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        key = _string_literal(node.slice)
        if key not in METADATA_KEYS:
            continue
        offenders.append(
            Offender(
                rel_path=rel_path,
                line=node.lineno,
                rule="raw_model_metadata_dict_subscript",
                detail=(
                    f'Raw dict metadata access ["{key}"] is forbidden here; keep '
                    "provider/model metadata typed across adapter boundaries."
                ),
            )
        )

    return sorted(offenders, key=lambda item: (item.rel_path, item.line, item.rule))


def scan(
    root: Path | None = None,
    target_files: tuple[str, ...] | None = None,
) -> list[Offender]:
    root = ROOT if root is None else root
    target_files = TARGET_FILES if target_files is None else target_files
    offenders: list[Offender] = []
    for rel_path in target_files:
        path = root / rel_path
        if not path.exists():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        offenders.extend(scan_source(source, rel_path))
    return offenders


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    offenders = scan()
    allowlisted = set(ALLOWLIST)

    if "--list" in sys.argv[1:]:
        print(f"AI model metadata guardrail offenders ({len(offenders)} location(s)):\n")
        for offender in offenders:
            tag = "known" if offender.key in allowlisted else "NEW"
            print(f"  [{tag}] {offender.key}  <-  {offender.detail}")
        return 0

    found = {offender.key: offender for offender in offenders}
    new = sorted(set(found) - allowlisted)
    stale = sorted(allowlisted - set(found))

    print("AI model metadata guardrail: scanned backend AI/model adapter files")
    print(f"  {len(offenders)} offender location(s); {len(allowlisted)} allowlisted.")

    if stale:
        print("\n  Stale allowlist entries are now clean; remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} new AI/model metadata offender(s):")
        for key in new:
            offender = found[key]
            print(f"      {offender.rel_path}:{offender.line} [{offender.rule}]")
            print(f"          {offender.detail}")
        print(
            "\nFix: keep provider/model metadata typed in these adapters. "
            f"Rule pointer: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n(ALLOWLIST has stale entries; clean them up when convenient.)")
    print("\nOK: no new raw AI/model metadata dict usage in targeted backend adapters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
