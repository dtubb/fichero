#!/usr/bin/env python3
"""Guardrail for dynamic writes to persisted Pydantic models.

This checker catches the silent failure mode where a route/update handler writes
dynamic attributes to a Pydantic model that later gets serialized with
``model_dump()``. If the attribute is not declared on the model, the write can
appear to succeed at runtime and then disappear on the next dump/save cycle.

The scanner is deliberately conservative:
- focuses on backend route modules
- uses AST, not grep, to follow ``model_dump(...)`` payloads into ``setattr`` or
  direct attribute writes
- only treats request models as risky when they are declared with
  ``ConfigDict(extra="allow")``
- only treats target attribute writes as risky when the target model is a
  Pydantic model with a declared field set
- allows explicit suppressions via ``# pydantic-persistence-guardrail: allow``
  comments or a keyed allowlist baseline

Usage:
    scripts/check_pydantic_persistence_writes.py
    scripts/check_pydantic_persistence_writes.py --list
    scripts/check_pydantic_persistence_writes.py --help
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
ENGINE_SRC = ROOT / "fichero-server" / "src" / "fichero_server"
ROUTES_DIR = ENGINE_SRC / "api" / "routes"

ALLOWLIST: dict[str, str] = {}
ALLOW_COMMENT = "pydantic-persistence-guardrail: allow"


@dataclass(frozen=True)
class ModelInfo:
    fields: frozenset[str]
    extra_allow: bool


@dataclass(frozen=True)
class Offender:
    rel_path: str
    line: int
    rule: str
    detail: str

    @property
    def key(self) -> str:
        return f"{self.rel_path}:{self.line}:{self.rule}"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _relative_key(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_python_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*.py"))


def _is_base_model(base: ast.expr) -> bool:
    return isinstance(base, ast.Name) and base.id == "BaseModel" or (
        isinstance(base, ast.Attribute) and base.attr == "BaseModel"
    )


def _string_literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_extra_allow_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        callee_name = func.id
    elif isinstance(func, ast.Attribute):
        callee_name = func.attr
    else:
        return False
    if callee_name != "ConfigDict":
        return False
    for kw in node.keywords:
        if kw.arg == "extra" and _string_literal(kw.value) == "allow":
            return True
    return False


def _model_fields_from_class(node: ast.ClassDef) -> tuple[frozenset[str], bool]:
    fields: set[str] = set()
    extra_allow = False
    for item in node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "model_config":
                    extra_allow = _is_extra_allow_call(item.value)
                elif not target.id.startswith("_"):
                    fields.add(target.id)
        elif isinstance(item, ast.AnnAssign):
            if isinstance(item.target, ast.Name) and not item.target.id.startswith("_"):
                fields.add(item.target.id)
    if "model_config" in fields:
        fields.remove("model_config")
    return frozenset(fields), extra_allow


def _catalog_from_tree(tree: ast.Module) -> dict[str, ModelInfo]:
    catalog: dict[str, ModelInfo] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(_is_base_model(base) for base in node.bases):
            continue
        fields, extra_allow = _model_fields_from_class(node)
        catalog[node.name] = ModelInfo(fields=fields, extra_allow=extra_allow)
    return catalog


@lru_cache(maxsize=1)
def build_model_catalog(root: str = str(ENGINE_SRC)) -> dict[str, ModelInfo]:
    catalog: dict[str, ModelInfo] = {}
    for path in _iter_python_files(Path(root)):
        try:
            tree = ast.parse(_read_text(path), filename=path.as_posix())
        except (OSError, SyntaxError):
            continue
        catalog.update(_catalog_from_tree(tree))
    return catalog


def _local_catalog(source: str) -> dict[str, ModelInfo]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    return _catalog_from_tree(tree)


def _annotations_from_module(tree: ast.Module) -> dict[str, str]:
    return {
        node.name: _annotation_name(node.returns)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.returns is not None
        and _annotation_name(node.returns) is not None
    }


def _annotation_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _annotation_name(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _annotation_name(node.left) or _annotation_name(node.right)
    return None


def _comment_lines(source: str) -> set[int]:
    lines = source.splitlines()
    flagged: set[int] = set()
    for index, line in enumerate(lines, start=1):
        if ALLOW_COMMENT in line:
            flagged.add(index)
    return flagged


def _has_allow_comment(lines: list[str], line: int) -> bool:
    for candidate in range(max(1, line - 2), min(len(lines), line + 1) + 1):
        text = lines[candidate - 1]
        if ALLOW_COMMENT in text:
            return True
    return False


def _target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _iter_children(node: ast.AST) -> Iterable[ast.AST]:
    for child in ast.iter_child_nodes(node):
        yield child


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_model_dump_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "model_dump"


def _is_items_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "items"


def _resolve_return_type(call: ast.Call, function_returns: dict[str, str]) -> str | None:
    callee = call.func
    if isinstance(callee, ast.Name):
        return function_returns.get(callee.id)
    return None


def _declare_var_type(
    var_types: dict[str, str],
    target: ast.expr,
    inferred: str | None,
) -> None:
    if inferred is None:
        return
    if isinstance(target, ast.Name):
        var_types[target.id] = inferred


def _type_from_expr(
    expr: ast.AST,
    *,
    function_returns: dict[str, str],
    model_catalog: dict[str, ModelInfo],
    local_models: dict[str, ModelInfo],
) -> str | None:
    if isinstance(expr, ast.Call):
        callee = expr.func
        if isinstance(callee, ast.Name) and callee.id in model_catalog:
            return callee.id
        if isinstance(callee, ast.Attribute):
            if callee.attr in {"get", "query"} and expr.args:
                first = expr.args[0]
                inferred = _annotation_name(first)
                if inferred in model_catalog:
                    return inferred
        inferred = _resolve_return_type(expr, function_returns)
        if inferred in model_catalog:
            return inferred
    if isinstance(expr, ast.Name) and expr.id in local_models:
        return expr.id
    return None


def _model_dump_sources(
    function_node: ast.AST,
    *,
    request_models: dict[str, str],
) -> dict[str, str]:
    payload_sources: dict[str, str] = {}
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if _is_model_dump_call(value) and isinstance(value.func.value, ast.Name):
            model_name = value.func.value.id
            if model_name in request_models:
                payload_sources[target.id] = model_name
    return payload_sources


def _loop_bindings(node: ast.For | ast.AsyncFor) -> tuple[str | None, str | None]:
    if isinstance(node.target, ast.Tuple) and len(node.target.elts) >= 2:
        key = _target_name(node.target.elts[0])
        value = _target_name(node.target.elts[1])
        return key, value
    return None, None


def _model_fields(catalog: dict[str, ModelInfo], model_name: str | None) -> frozenset[str]:
    if model_name is None:
        return frozenset()
    info = catalog.get(model_name)
    return info.fields if info else frozenset()


def _function_request_models(
    node: ast.AST,
    annotations: dict[str, str],
    model_catalog: dict[str, ModelInfo],
) -> dict[str, str]:
    request_models: dict[str, str] = {}
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return request_models
    for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
        annotation = _annotation_name(arg.annotation)
        if annotation in model_catalog and model_catalog[annotation].extra_allow:
            request_models[arg.arg] = annotation
    if node.args.vararg:
        annotation = _annotation_name(node.args.vararg.annotation)
        if annotation in model_catalog and model_catalog[annotation].extra_allow:
            request_models[node.args.vararg.arg] = annotation
    if node.args.kwarg:
        annotation = _annotation_name(node.args.kwarg.annotation)
        if annotation in model_catalog and model_catalog[annotation].extra_allow:
            request_models[node.args.kwarg.arg] = annotation
    return request_models


def _scan_function(
    node: ast.AST,
    *,
    rel_path: str,
    source_lines: list[str],
    function_returns: dict[str, str],
    model_catalog: dict[str, ModelInfo],
    local_models: dict[str, ModelInfo],
) -> list[Offender]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []

    request_models = _function_request_models(node, function_returns, model_catalog)
    var_types: dict[str, str] = {}
    payload_sources: dict[str, str] = {}
    offenders: list[Offender] = []

    for child in ast.walk(node):
        if isinstance(child, ast.AnnAssign):
            inferred = _annotation_name(child.annotation)
            if inferred in model_catalog:
                _declare_var_type(var_types, child.target, inferred)
            for target in [child.target]:
                if not isinstance(target, ast.Attribute):
                    continue
                target_name = _target_name(target.value)
                if target_name is None:
                    continue
                model_name = var_types.get(target_name)
                if model_name is None:
                    continue
                declared = _model_fields(model_catalog, model_name)
                if target.attr in declared:
                    continue
                if _has_allow_comment(source_lines, child.lineno):
                    continue
                offenders.append(
                    Offender(
                        rel_path=rel_path,
                        line=child.lineno,
                        rule="direct_undeclared_model_attribute_write",
                        detail=(
                            f"{model_name}.{target.attr} is not a declared field, so "
                            "the assignment can vanish on model_dump()."
                        ),
                    )
                )

        if isinstance(child, ast.Assign):
            inferred = _type_from_expr(
                child.value,
                function_returns=function_returns,
                model_catalog=model_catalog,
                local_models=local_models,
            )
            if len(child.targets) == 1:
                _declare_var_type(var_types, child.targets[0], inferred)
            if _is_model_dump_call(child.value) and isinstance(child.value.func.value, ast.Name):
                source_name = child.value.func.value.id
                if source_name in request_models:
                    for target in child.targets:
                        if isinstance(target, ast.Name):
                            payload_sources[target.id] = request_models[source_name]
            for target in child.targets:
                if not isinstance(target, ast.Attribute):
                    continue
                target_name = _target_name(target.value)
                if target_name is None:
                    continue
                model_name = var_types.get(target_name)
                if model_name is None:
                    continue
                declared = _model_fields(model_catalog, model_name)
                if target.attr in declared:
                    continue
                if _has_allow_comment(source_lines, child.lineno):
                    continue
                offenders.append(
                    Offender(
                        rel_path=rel_path,
                        line=child.lineno,
                        rule="direct_undeclared_model_attribute_write",
                        detail=(
                            f"{model_name}.{target.attr} is not a declared field, so "
                            "the assignment can vanish on model_dump()."
                        ),
                    )
                )
            continue

        if isinstance(child, ast.For):
            key_name, value_name = _loop_bindings(child)
            if not key_name or not value_name:
                continue
            iter_name = None
            iterator = child.iter
            if isinstance(iterator, ast.Call) and isinstance(iterator.func, ast.Attribute) and iterator.func.attr == "items":
                source = iterator.func.value
                if isinstance(source, ast.Name):
                    iter_name = source.id
            if iter_name not in payload_sources:
                continue
            request_model = payload_sources[iter_name]
            for inner in ast.walk(child):
                if not isinstance(inner, ast.Call):
                    continue
                if not isinstance(inner.func, ast.Name) or inner.func.id != "setattr":
                    continue
                if len(inner.args) < 2:
                    continue
                target_name = _target_name(inner.args[0])
                attr_name = _target_name(inner.args[1])
                if target_name is None or attr_name is None:
                    continue
                model_name = var_types.get(target_name)
                if model_name is None:
                    continue
                declared = _model_fields(model_catalog, model_name)
                if attr_name in declared:
                    continue
                if _has_allow_comment(source_lines, inner.lineno):
                    continue
                offenders.append(
                    Offender(
                        rel_path=rel_path,
                        line=inner.lineno,
                        rule="dynamic_setattr_from_extra_allow_model_dump",
                        detail=(
                            f"setattr({target_name}, {attr_name}, ...) writes a dynamic "
                            f"attribute from {request_model}.model_dump() onto {model_name}; "
                            "undeclared fields will not survive model_dump()."
                        ),
                    )
                )

    return offenders


def scan_source(
    source: str,
    rel_path: str,
    *,
    model_catalog: dict[str, ModelInfo] | None = None,
) -> list[Offender]:
    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError:
        return []

    catalog = dict(build_model_catalog())
    if model_catalog:
        catalog.update(model_catalog)
    local_models = _local_catalog(source)
    catalog.update(local_models)
    function_returns = _annotations_from_module(tree)
    source_lines = source.splitlines()

    offenders: list[Offender] = []
    for node in tree.body:
        offenders.extend(
            _scan_function(
                node,
                rel_path=rel_path,
                source_lines=source_lines,
                function_returns=function_returns,
                model_catalog=catalog,
                local_models=local_models,
            )
        )
    return sorted(offenders, key=lambda item: (item.rel_path, item.line, item.rule))


def scan(
    root: Path | None = None,
    routes_dir: Path | None = None,
) -> list[Offender]:
    base_root = root or ROOT
    routes_root = routes_dir or ROUTES_DIR
    offenders: list[Offender] = []
    for path in _iter_python_files(routes_root):
        try:
            source = _read_text(path)
        except OSError:
            continue
        rel_path = _relative_key(path, base_root)
        offenders.extend(scan_source(source, rel_path))
    return offenders


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    offenders = scan()
    allowlisted = set(ALLOWLIST)
    found = {offender.key: offender for offender in offenders}
    new = sorted(set(found) - allowlisted)
    stale = sorted(allowlisted - set(found))

    if "--list" in sys.argv[1:]:
        print(f"Pydantic persistence guardrail offenders ({len(offenders)} location(s)):\n")
        for offender in offenders:
            tag = "known" if offender.key in allowlisted else "NEW"
            print(f"  [{tag}] {offender.key}  <-  {offender.detail}")
        return 0

    print("Pydantic persistence guardrail: scanned backend route update code")
    print(f"  {len(offenders)} offender location(s); {len(allowlisted)} allowlisted.")

    if stale:
        print("\n  Stale allowlist entries are now clean; remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} new persistence-write offender(s):")
        for key in new:
            offender = found[key]
            print(f"      {offender.rel_path}:{offender.line} [{offender.rule}]")
            print(f"          {offender.detail}")
        print(
            "\nFix: keep dynamic writes confined to declared fields, or add an "
            f"explicit allow-comment/baseline entry. Rule pointer: {ALLOW_COMMENT}."
        )
        return 1

    if stale:
        print("\n(ALLOWLIST has stale entries; clean them up when convenient.)")

    print("\nOK: no new dynamic writes to undeclared persisted Pydantic fields.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
