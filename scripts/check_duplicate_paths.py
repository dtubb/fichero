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
import re
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


_SHIM_RE = re.compile(r'sys\.modules\[__name__\]\s*=\s*sys\.modules\[["\']([\w.]+)["\']\]')


def _resolve_real_rel_path(root: Path, rel_path: str) -> str:
    """Resolve a route module's file to wherever its handler bodies actually live.

    #2569 turned several flat route modules into subpackages. Two shapes:
    1) The old flat name stays as an identity-preserving shim
       (`sys.modules[__name__] = sys.modules[...]`) pointing at a nested module.
    2) The old flat name became a package directly (e.g. `search.py` ->
       `search/core.py`), so the flat file no longer exists at all.
    Both must resolve to the file that really defines the route functions, or
    the mounted-prefix lookup below silently misses and drops the prefix.
    """
    flat = root / rel_path
    if flat.is_file():
        try:
            match = _SHIM_RE.search(flat.read_text(encoding="utf-8"))
        except OSError:
            match = None
        if match:
            suffix = match.group(1).removeprefix("fichero.api.routes.")
            return "api/routes/" + suffix.replace(".", "/") + ".py"
        return rel_path
    package_core = root / rel_path.removesuffix(".py") / "core.py"
    if package_core.is_file():
        return str(package_core.relative_to(root))
    return rel_path


def _mounted_route_prefixes(root: Path) -> dict[str, str]:
    """Return module prefixes declared by the application's route specs."""
    main = root / "api" / "main.py"
    if not main.exists():
        return {}
    try:
        tree = ast.parse(main.read_text(encoding="utf-8"), filename=str(main))
    except SyntaxError:
        return {}

    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if not isinstance(value, ast.List):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "_CORE_ROUTE_SPECS"
            for target in targets
        ):
            continue
        for spec in value.elts:
            if not isinstance(spec, ast.Tuple) or len(spec.elts) < 2:
                continue
            router, prefix = spec.elts[:2]
            if (
                not isinstance(router, ast.Attribute)
                or not isinstance(router.value, ast.Name)
                or router.attr != "router"
                or not isinstance(prefix, ast.Constant)
                or not isinstance(prefix.value, str)
            ):
                continue
            rel_path = _resolve_real_rel_path(root, f"api/routes/{router.value.id}.py")
            prefixes[rel_path] = prefix.value
    return prefixes


def _function_occurrences(
    tree: ast.AST, rel_file: str, mounted_prefix: str = ""
) -> list[Occurrence]:
    found: list[Occurrence] = []
    prefixes = _extract_router_prefixes(tree)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        symbol = node.name

        for dec in node.decorator_list:
            concern = _route_decorator_concern(dec, prefixes)
            if concern:
                method_path = concern.removeprefix("route:")
                method, path = method_path.split(" ", maxsplit=1)
                found.append(
                    Occurrence(
                        concern=f"route:{method} {mounted_prefix}{path}",
                        symbol=symbol,
                        file=rel_file,
                        line=node.lineno,
                    )
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
    mounted_prefixes = _mounted_route_prefixes(root)
    for path in _py_files(root):
        rel = str(path.relative_to(root))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for occ in _function_occurrences(tree, rel, mounted_prefixes.get(rel, "")):
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
