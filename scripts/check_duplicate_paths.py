#!/usr/bin/env python3
"""Programmatic duplicate-handler/writer gate.

Flags accidental duplicate code paths for the same concern:
1) API route handlers: same METHOD + PATH handled more than once.
2) KG writers: multiple functions writing KnowledgeEntity / KnowledgeClaim
   via constructors or canonical writer helpers.

Intentional duplicates must be explicitly listed in the allowlist.
"""
from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE_SRC = ROOT / "fichero-engine" / "src" / "fichero"
ALLOWLIST = ROOT / "fichero-engine" / "tests" / "contracts" / "duplicate_paths_allowlist.json"

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
KG_ENTITY_TOKENS = {"KnowledgeEntity", "upsert_entity"}
KG_CLAIM_TOKENS = {"KnowledgeClaim", "save_claim"}


@dataclass(frozen=True)
class Occurrence:
    concern: str
    symbol: str
    file: str
    line: int

    @property
    def key(self) -> str:
        return f"{self.file}::{self.symbol}"


def _py_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in {"tests", "__pycache__", "generated", ".venv"} for part in path.parts):
            continue
        out.append(path)
    return out


def _call_name(node: ast.Call) -> str | None:
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def _extract_router_prefixes(tree: ast.AST) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Name) or call.func.id != "APIRouter":
            continue
        prefix = ""
        for kw in call.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                prefix = kw.value.value
                break
        prefixes[node.targets[0].id] = prefix
    return prefixes


def _route_decorator_concern(dec: ast.expr, prefixes: dict[str, str]) -> str | None:
    if not isinstance(dec, ast.Call):
        return None
    fn = dec.func
    if not isinstance(fn, ast.Attribute) or not isinstance(fn.value, ast.Name):
        return None
    router_name = fn.value.id
    method = fn.attr.lower()
    if method not in HTTP_METHODS:
        return None
    if not dec.args:
        return None
    path_arg = dec.args[0]
    if not isinstance(path_arg, ast.Constant) or not isinstance(path_arg.value, str):
        return None
    path = path_arg.value
    prefix = prefixes.get(router_name, "")
    path = f"{prefix}{path}"
    if not path.strip():
        return None
    return f"route:{method.upper()} {path}"


def _function_occurrences(tree: ast.AST, rel_file: str) -> list[Occurrence]:
    found: list[Occurrence] = []
    prefixes = _extract_router_prefixes(tree)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        symbol = node.name

        for dec in node.decorator_list:
            concern = _route_decorator_concern(dec, prefixes)
            if concern:
                found.append(
                    Occurrence(concern=concern, symbol=symbol, file=rel_file, line=node.lineno)
                )

        names = {
            _call_name(call)
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
        }
        names.discard(None)
        if names & KG_ENTITY_TOKENS:
            found.append(
                Occurrence(
                    concern="kg_write:KnowledgeEntity",
                    symbol=symbol,
                    file=rel_file,
                    line=node.lineno,
                )
            )
        if names & KG_CLAIM_TOKENS:
            found.append(
                Occurrence(
                    concern="kg_write:KnowledgeClaim",
                    symbol=symbol,
                    file=rel_file,
                    line=node.lineno,
                )
            )
    return found


def collect(root: Path = ENGINE_SRC) -> dict[str, list[Occurrence]]:
    by_concern: dict[str, list[Occurrence]] = defaultdict(list)
    for path in _py_files(root):
        rel = str(path.relative_to(root))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for occ in _function_occurrences(tree, rel):
            by_concern[occ.concern].append(occ)
    return by_concern


def _load_allowlist() -> dict[str, list[str]]:
    if not ALLOWLIST.exists():
        return {}
    data = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    return data.get("concerns", {})


def find_violations(root: Path = ENGINE_SRC) -> dict[str, list[Occurrence]]:
    concerns = collect(root)
    allowed = _load_allowlist()
    violations: dict[str, list[Occurrence]] = {}
    for concern, occs in concerns.items():
        if len(occs) <= 1:
            continue
        allow = set(allowed.get(concern, []))
        extras = [o for o in occs if o.key not in allow]
        if extras:
            violations[concern] = occs
    return violations


def write_allowlist(root: Path = ENGINE_SRC) -> None:
    concerns = collect(root)
    payload = {
        "_doc": "Intentional duplicate code paths. Keys are concern ids; values are explicit allowed handlers/writers.",
        "concerns": {
            concern: sorted({occ.key for occ in occs})
            for concern, occs in sorted(concerns.items())
            if len(occs) > 1
        },
    }
    ALLOWLIST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {ALLOWLIST} with {len(payload['concerns'])} concern(s).")


def main() -> int:
    if "--write-allowlist" in sys.argv:
        write_allowlist()
        return 0

    violations = find_violations()
    if not violations:
        print("OK: no unallowlisted duplicate handler/writer concerns.")
        return 0

    print("Duplicate concern(s) detected:")
    for concern, occs in sorted(violations.items()):
        print(f"  - {concern}")
        for occ in occs:
            print(f"      {occ.file}:{occ.line}::{occ.symbol}")
    print("\nFix by collapsing to one canonical path, or explicitly allowlisting intentional duplicates.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
