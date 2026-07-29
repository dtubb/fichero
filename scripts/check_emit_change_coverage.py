#!/usr/bin/env python3
"""Ratchet guardrail for observable backend writes that must broadcast changes.

A violation is any top-level POST/PUT/PATCH/DELETE handler in a route module whose
store-observed domain does not call emit_change().

It also flags non-route saves of observable models when the save is not followed
nearby by emit_change() or an explicit allow comment.

The current gaps are seeded in KNOWN_GAPS so this script passes on the current tree
and fails only when a new mutating route appears without emit coverage.

Usage:
    scripts/check_emit_change_coverage.py
    scripts/check_emit_change_coverage.py --list
    scripts/check_emit_change_coverage.py --help
"""
from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "fichero" / "fichero" / "Models"
ROUTES_DIR = ROOT / "fichero-server" / "src" / "fichero" / "api" / "routes"
API_DIR = ROOT / "fichero-server" / "src" / "fichero" / "api"

METHODS = {"post", "put", "patch", "delete"}
ALLOW_COMMENT_RE = re.compile(
    r"emit-change:\s*allow|emit_change:\s*allow|no\s+emit_change|observable-save:\s*allow",
    re.I,
)

# Central observable-domain model map. Route coverage derives simple
# singular/plural route filenames from this map, and the non-route persistence
# scan uses the model names to keep findings high-signal.
OBSERVABLE_DOMAIN_MODELS: dict[str, set[str]] = {
    "annotation": {"Annotation"},
    "artifact": {"Artifact"},
    "citation": {"DocumentCitation"},
    "claim": {"KnowledgeClaim", "KnowledgeClaimLink"},
    "document": {"Document"},
    "entity": {"KnowledgeEntity"},
    "interpretation": {"Interpretation"},
    "note": {"Note"},
    "reference": {"Reference", "ReferenceProvenance"},
}

ROUTE_DOMAIN_OVERRIDES: dict[str, str] = {
    "annotations": "annotation",
    "notes": "note",
    "research_notes": "note",
    "actions": "action",
    "research_crud": "research",
    "projects": "research",
    "entities": "entity",
    "claims": "claim",
    "claim_curation": "claim",
    "claim_links": "claim",
    "documents": "document",
    "workflows": "workflow",
    "hermeneutics": "interpretation",
}

# Domains that the ratchet checks even when no Swift *Store.swift observes them
# yet. Backend-first slices land their mutating routes before their frontend
# store (e.g. hermeneutics routes shipped ahead of the interpretation store,
# #2009). Without this, such a module would slip through the
# `domain not in observed_domains` gate — the exact blind spot that let
# hermeneutics.py emit nothing while the scanner reported "0 gaps".
BACKEND_FIRST_DOMAINS: set[str] = {"interpretation"}

# Two store shapes observe a change domain:
#   legacy multi-domain:  changeDomains: Set<String> { ["a", "b"] }
#   substrate single:     var changeDomain: String { "a" }   (#1995 migration)
# Match BOTH — otherwise the 8 stores migrated onto ObservableDomainStore drop
# out of observed_domains and the scanner silently stops checking their route
# modules (false "0 gaps" over a narrower set).
CHANGE_DOMAINS_RE = re.compile(
    r"changeDomains:\s*Set<String>\s*(?:=\s*)?(?:\{\s*)?\[(.*?)\]",
    re.S,
)
CHANGE_DOMAIN_RE = re.compile(r'changeDomain:\s*String\s*\{\s*"([^"]+)"\s*\}')
STRING_RE = re.compile(r'\"([^\"]+)\"')

# Deferred gaps to fix later.
KNOWN_GAPS: set[str] = {
    "fichero-server/src/fichero_server/api/routes/documents.py::import_file",
    "fichero-server/src/fichero_server/api/routes/documents.py::purge_document",
    "fichero-server/src/fichero_server/api/routes/workflows.py::create_node",
}

# PERMANENTLY EXEMPT: POST handlers in a store-observed domain that mutate NO
# persistent state, so they have nothing to broadcast. These are NOT gaps — they
# are excluded from the gap set entirely (not "deferred"). Keep this list tight;
# only add a route here after confirming it performs no DB write.
EXEMPT: set[str] = {
    # Compute-only: estimates a cost, returns it; writes nothing.
    "fichero-server/src/fichero_server/api/routes/workflows.py::estimate_workflow_cost",
    # Read-only: returns a tool's prompt text for preview; writes nothing.
    "fichero-server/src/fichero_server/api/routes/workflows.py::get_tool_prompt",
    # Compute-only: generates AI interpretation suggestions; persists nothing.
    "fichero-server/src/fichero_server/api/routes/hermeneutics.py::suggest_interpretations",
    # Ephemeral crop returns a transient region preview and never saves an annotation.
    "fichero-server/src/fichero_server/api/routes/annotations.py::crop_ephemeral",
}


# Terminal workflow nodes that finalize a run's state and MUST broadcast it to
# the library change-stream (#2518). These live OUTSIDE api/routes/*.py — under
# workflows/ and the nested workflow_execution/ package — so neither the route
# scan (top-level routes/*.py only) nor the non-route save scan (skips the
# routes/ subtree) ever sees them. That blind spot is exactly why completed
# status + finalized KG never pushed live: the run wrote the rows but emitted
# only to the per-run PROGRESS stream. Each entry pins a file to the emit callee
# that must appear in it; the check FAILS if the emit is removed.
REQUIRED_TERMINAL_EMITS: tuple[tuple[str, frozenset[str]], ...] = (
    # complete_run_documents marks docs completed and broadcasts document.updated
    # (centralised here so BOTH the main runner and the batch path are covered).
    (
        "fichero-server/src/fichero_server/workflows/completion.py",
        frozenset({"emit_change"}),
    ),
    # kg_persist_finalize rebuilds the graph/embeddings then broadcasts
    # entity.updated / claim.updated / document.updated for the finalized scope.
    (
        "fichero-server/src/fichero_server/workflows/tools/kg_persist_finalize.py",
        frozenset({"emit_workflow_kg_changes"}),
    ),
)


def scan_required_terminal_emits(
    *,
    root: Path | None = None,
    required: tuple[tuple[str, frozenset[str]], ...] | None = None,
) -> list[str]:
    """Return violations: required terminal-node files missing their emit (#2518).

    A violation string names the file and the emit callee(s) it must contain.
    Empty list == all terminal nodes broadcast. Pure-AST, no imports executed.
    """
    base_root = root or ROOT
    spec = required if required is not None else REQUIRED_TERMINAL_EMITS
    violations: list[str] = []
    for rel_path, required_callees in spec:
        path = base_root / rel_path
        if not path.exists():
            violations.append(f"{rel_path} (file missing)")
            continue
        try:
            module = ast.parse(_read_text(path))
        except SyntaxError:
            violations.append(f"{rel_path} (unparseable)")
            continue
        found = {
            _call_name(node)
            for node in ast.walk(module)
            if isinstance(node, ast.Call)
        }
        if not (required_callees & found):
            violations.append(
                f"{rel_path} (missing required emit: "
                f"{' or '.join(sorted(required_callees))})"
            )
    return violations


@dataclass(frozen=True)
class Row:
    file: str
    handler: str
    method: str
    domain: str
    emit_change: bool

    @property
    def key(self) -> str:
        return f"{self.file}::{self.handler}"

    @property
    def gap(self) -> bool:
        return not self.emit_change


@dataclass(frozen=True)
class SaveRow:
    file: str
    function: str
    line: int
    model: str
    domain: str
    emit_change: bool
    allowed: bool

    @property
    def key(self) -> str:
        return f"{self.file}:{self.line}::{self.function}"

    @property
    def gap(self) -> bool:
        return not self.emit_change and not self.allowed


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _singular_plural(domain: str) -> set[str]:
    names = {domain}
    if domain.endswith("y"):
        names.add(f"{domain[:-1]}ies")
    elif domain.endswith(("s", "x", "z", "ch", "sh")):
        names.add(f"{domain}es")
    else:
        names.add(f"{domain}s")
    return names


def _route_domain_map() -> dict[str, str]:
    route_map = dict(ROUTE_DOMAIN_OVERRIDES)
    for domain in OBSERVABLE_DOMAIN_MODELS:
        for stem in _singular_plural(domain):
            route_map.setdefault(stem, domain)
    return route_map


def _model_domain_map() -> dict[str, str]:
    return {
        model: domain
        for domain, models in OBSERVABLE_DOMAIN_MODELS.items()
        for model in models
    }


def _observed_domains(*, root: Path | None = None, models_dir: Path | None = None) -> set[str]:
    base_root = root or ROOT
    store_dir = models_dir or base_root / "fichero" / "fichero" / "Models"
    observed: set[str] = set()
    for path in sorted(store_dir.glob("*Store.swift")):
        text = _read_text(path)
        legacy = CHANGE_DOMAINS_RE.search(text)
        if legacy:
            observed.update(STRING_RE.findall(legacy.group(1)))
        observed.update(CHANGE_DOMAIN_RE.findall(text))
    return observed


def _mutating_method(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return None
    if not isinstance(func.value, ast.Name) or func.value.id != "router":
        return None
    if func.attr not in METHODS:
        return None
    return func.attr


def _has_emit_change(function_node: ast.AST) -> bool:
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name) and callee.id == "emit_change":
            return True
        if isinstance(callee, ast.Attribute) and callee.attr == "emit_change":
            return True
        if (
            isinstance(callee, ast.Attribute)
            and callee.attr == "invoke"
            and isinstance(callee.value, ast.Name)
            and callee.value.id == "registry"
        ):
            return True
        if (
            isinstance(callee, ast.Name)
            and callee.id == "_run_document_write"
            and node.args
            and isinstance(node.args[0], ast.Attribute)
            and node.args[0].attr == "invoke"
            and isinstance(node.args[0].value, ast.Name)
            and node.args[0].value.id == "registry"
        ):
            return True
    return False


def _call_name(call: ast.Call) -> str | None:
    callee = call.func
    if isinstance(callee, ast.Name):
        return callee.id
    if isinstance(callee, ast.Attribute):
        return callee.attr
    return None


def _constructed_model(node: ast.AST, model_domains: dict[str, str]) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    callee = node.func
    if isinstance(callee, ast.Name) and callee.id in model_domains:
        return callee.id
    if isinstance(callee, ast.Attribute) and callee.attr in {
        "model_validate",
        "model_construct",
    }:
        owner = callee.value
        if isinstance(owner, ast.Name) and owner.id in model_domains:
            return owner.id
    return None


def _save_call_model(call: ast.Call, inferred_models: dict[str, str]) -> str | None:
    if _call_name(call) != "save" or not call.args:
        return None
    arg = call.args[0]
    direct = _constructed_model(arg, _model_domain_map())
    if direct:
        return direct
    if isinstance(arg, ast.Name):
        return inferred_models.get(arg.id)
    return None


def _nearest_named_parent(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST | None:
    current: ast.AST | None = node
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
        current = parents.get(current)
    return None


def _function_name(function_node: ast.AST | None) -> str:
    if isinstance(function_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return function_node.name
    return "<module>"


def _has_nearby_emit_change(function_node: ast.AST | None, save_line: int, *, window: int = 12) -> bool:
    if function_node is None:
        return False
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node) != "emit_change":
            continue
        line = getattr(node, "lineno", -1)
        if save_line <= line <= save_line + window:
            return True
    return False


def _has_allow_comment(lines: list[str], line_no: int, *, window: int = 2) -> bool:
    start = max(1, line_no - window)
    end = min(len(lines), line_no + window)
    return any(ALLOW_COMMENT_RE.search(lines[index - 1]) for index in range(start, end + 1))


def _assigned_targets(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for elt in target.elts:
            names.extend(_assigned_targets(elt))
        return names
    return []


class _ObservableSaveVisitor(ast.NodeVisitor):
    def __init__(self, *, rel_path: str, lines: list[str]) -> None:
        self.rel_path = rel_path
        self.lines = lines
        self.model_domains = _model_domain_map()
        self.parents: dict[ast.AST, ast.AST] = {}
        self._scope_stack: list[dict[str, str]] = [{}]
        self.rows: list[SaveRow] = []

    def visit(self, node: ast.AST) -> None:  # noqa: D102
        for child in ast.iter_child_nodes(node):
            self.parents[child] = node
        super().visit(node)

    @property
    def inferred_models(self) -> dict[str, str]:
        return self._scope_stack[-1]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._scope_stack.append({})
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._scope_stack.append({})
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        model = _constructed_model(node.value, self.model_domains)
        if model:
            for target in node.targets:
                for name in _assigned_targets(target):
                    self.inferred_models[name] = model
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        model = _constructed_model(node.value, self.model_domains) if node.value else None
        if model:
            for name in _assigned_targets(node.target):
                self.inferred_models[name] = model
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        model = _save_call_model(node, self.inferred_models)
        if model:
            line = getattr(node, "lineno", 0)
            function_node = _nearest_named_parent(node, self.parents)
            self.rows.append(
                SaveRow(
                    file=self.rel_path,
                    function=_function_name(function_node),
                    line=line,
                    model=model,
                    domain=self.model_domains[model],
                    emit_change=_has_nearby_emit_change(function_node, line),
                    allowed=_has_allow_comment(self.lines, line),
                )
            )
        self.generic_visit(node)


def scan(
    *,
    root: Path | None = None,
    models_dir: Path | None = None,
    routes_dir: Path | None = None,
) -> list[Row]:
    base_root = root or ROOT
    route_root = routes_dir or base_root / "fichero-server" / "src" / "fichero" / "api" / "routes"
    observed_domains = _observed_domains(root=base_root, models_dir=models_dir)
    rows: list[Row] = []

    for path in sorted(route_root.glob("*.py")):
        if path.name == "__init__.py":
            continue
        domain = _route_domain_map().get(path.stem)
        if not domain:
            continue
        if domain not in observed_domains and domain not in BACKEND_FIRST_DOMAINS:
            continue
        source = _read_text(path)
        try:
            module = ast.parse(source)
        except SyntaxError:
            continue

        try:
            rel_path = path.relative_to(base_root).as_posix()
        except ValueError:
            rel_path = path.as_posix()
        for statement in module.body:
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            methods = {_mutating_method(decorator) for decorator in statement.decorator_list}
            methods.discard(None)
            if not methods:
                continue
            rows.append(
                Row(
                    file=rel_path,
                    handler=statement.name,
                    method=next(iter(sorted(methods))),
                    domain=domain,
                    emit_change=_has_emit_change(statement),
                )
            )

    return rows


def scan_non_route_saves(
    *,
    root: Path | None = None,
    api_dir: Path | None = None,
    routes_dir: Path | None = None,
) -> list[SaveRow]:
    base_root = root or ROOT
    # Keep the default scan on API-adjacent helpers. Whole-engine scanning also
    # catches batch import/workflow writers whose route/action owners broadcast
    # at coarser boundaries and produces too much noise for this guardrail.
    api_root = api_dir or base_root / "fichero-server" / "src" / "fichero" / "api"
    route_root = routes_dir or base_root / "fichero-server" / "src" / "fichero" / "api" / "routes"
    rows: list[SaveRow] = []

    for path in sorted(api_root.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            path.relative_to(route_root)
            continue
        except ValueError:
            pass
        source = _read_text(path)
        try:
            module = ast.parse(source)
        except SyntaxError:
            continue
        try:
            rel_path = path.relative_to(base_root).as_posix()
        except ValueError:
            rel_path = path.as_posix()
        visitor = _ObservableSaveVisitor(rel_path=rel_path, lines=source.splitlines())
        visitor.visit(module)
        rows.extend(visitor.rows)

    return rows


def _print_rows(rows: list[Row]) -> None:
    for row in rows:
        status = "known" if row.key in KNOWN_GAPS else "NEW" if row.gap else "ok"
        print(
            f"  [{status}] {row.key} | method={row.method.upper():5} domain={row.domain:8} "
            f"emit_change={'Y' if row.emit_change else 'N'}"
        )


def _print_save_rows(rows: list[SaveRow]) -> None:
    for row in rows:
        status = "allowed" if row.allowed else "ok" if row.emit_change else "NEW"
        print(
            f"  [{status}] {row.key} | domain={row.domain:14} model={row.model:18} "
            f"emit_change={'Y' if row.emit_change else 'N'}"
        )


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    rows = scan()
    save_rows = scan_non_route_saves()
    gaps = {row.key: row for row in rows if row.gap and row.key not in EXEMPT}
    save_gaps = {row.key: row for row in save_rows if row.gap}
    known = set(KNOWN_GAPS)

    if "--list" in sys.argv[1:]:
        print(f"Emit-change coverage ({len(rows)} mutating routes):\n")
        _print_rows(rows)
        print(f"\nNon-route observable saves ({len(save_rows)} save call(s)):\n")
        _print_save_rows(save_rows)
        return 0

    new = sorted(set(gaps) - known)
    stale = sorted(known - set(gaps))
    covered = len(rows) - len(gaps)
    save_covered = len(save_rows) - len(save_gaps)
    terminal_violations = scan_required_terminal_emits()

    print("emit-change coverage:")
    print(f"  {len(rows)} mutating route(s) checked")
    print(f"  emit-change coverage: {len(known)} known gaps, {covered} routes covered")
    print(f"  {len(save_rows)} non-route observable save(s) checked")
    print(f"  non-route save coverage: {save_covered} covered/allowed")
    print(
        f"  {len(REQUIRED_TERMINAL_EMITS)} terminal workflow node(s) checked "
        f"({len(REQUIRED_TERMINAL_EMITS) - len(terminal_violations)} broadcasting)"
    )

    if terminal_violations:
        print(f"\n  {len(terminal_violations)} terminal-node emit gap(s) (#2518):")
        for entry in terminal_violations:
            print(f"      {entry}")
        print(
            "\nFix: a terminal workflow node that finalizes run state MUST call "
            "emit_change / emit_workflow_kg_changes so the UI refreshes live."
        )
        return 1

    if stale:
        print(f"\n  {len(stale)} KNOWN_GAPS entries are now clean; remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} new gaps:")
        for key in new:
            row = gaps[key]
            print(f"      {key}  (method={row.method.upper()}, domain={row.domain})")
        return 1

    if save_gaps:
        print(f"\n  {len(save_gaps)} non-route observable save gaps:")
        for key in sorted(save_gaps):
            row = save_gaps[key]
            print(f"      {key}  (model={row.model}, domain={row.domain})")
        print(
            "\nFix: emit_change() within the next few lines after the save, or add a "
            "nearby '# emit-change: allow ...' comment explaining why no UI refresh is needed."
        )
        return 1

    if stale:
        print("\n(KNOWN_GAPS has stale entries; clean them up when convenient.)")

    print("\n✓ No emit_change coverage regressions beyond the seeded baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
