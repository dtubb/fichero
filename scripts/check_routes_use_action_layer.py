#!/usr/bin/env python3
"""Pins the audited-action-layer rule (#4831): every mutating route under
`api/routes/kg/` and `api/routes/entity/` reaches the backend through
`registry.invoke(` — the one audited, undoable, actor-attributed write choke
point (`docs/contributor_manual/specs/harness/audited-action-layer.md`,
`audit.every-mutating-route-uses-the-registry`).

READ-ONLY: a source scan (AST-based). It never edits Python.

Scope: every `.py` file under `fichero-server/src/fichero_server/api/routes/kg/`
and `.../api/routes/entity/` (non-recursive walk is enough today; `rglob` in
case a subpackage is added later). A "flat re-export shim" file — one that
declares no router-method-decorated function of its own, just re-exports
another module's router — needs no special-case skip: it structurally
contributes zero decorated functions, so it never produces a finding. There is
no per-file allowlist-by-name; every file is scanned uniformly.

Rule: a top-level OR NESTED function (a route handler nested inside a class or
another function still counts — FastAPI route handlers are typically
module-level, but the scan does not assume that) decorated by a call whose
attribute is `.post`/`.put`/`.patch`/`.delete` on ANY identifier (`router.post(`,
`kg_entities_router.put(`, `bio_router.delete(` — the router variable's name is
never assumed) must contain a call shaped `registry.invoke(` somewhere in its
OWN body (a plain AST walk of that function's subtree — nested helper
indirection is NOT traced: if a route calls a private helper that itself calls
`registry.invoke`, this scan does not see it, and flags the route). This is a
deliberate simplicity choice, not an oversight — the fix is to bring the
`registry.invoke(` call into the route's own body (as `add_entity_aliases`
does today), not to teach the scanner to trace indirection.

Allowlist: `scripts/routes_action_layer_allowlist.json`, entries `{file,
function, class, reason, issue?}` keyed `relative_file::function_name` —
shrink-only, same contract as every other allowlist in this repo:
  - `"class": "violation"` — a real gap; cites #4831 (or its own issue) +
    reason. Counted as DEBT.
  - `"class": "by-design"` — a genuinely read-only POST (e.g. a SPARQL query
    endpoint) or another checkable reason the route legitimately has no
    action to invoke. Requires a REASON a reader can verify — never an
    automatic "looks read-only" heuristic; there is no code path in this
    script that classifies anything as by-design on its own. Not counted as
    debt.
A stale entry (no longer a real finding) or one missing `class`/`reason` is
itself a failure. No automated write path — hand-edit only.

Run:
    python scripts/check_routes_use_action_layer.py
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys

ROOTS = [
    pathlib.Path("fichero-server/src/fichero_server/api/routes/kg"),
    pathlib.Path("fichero-server/src/fichero_server/api/routes/entity"),
]
ALLOWLIST_PATH = pathlib.Path("scripts/routes_action_layer_allowlist.json")

_HTTP_METHODS = {"post", "put", "patch", "delete"}


def _is_route_decorator(node: ast.expr) -> bool:
    """True when `node` is a decorator call like `<anything>.post(...)` /
    `.put(...)` / `.patch(...)` / `.delete(...)` — the router variable's own
    name is never assumed (a file may declare several routers, e.g.
    `kg_entities_router`, `bio_router`)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return isinstance(func, ast.Attribute) and func.attr in _HTTP_METHODS


def _is_registry_invoke_call(node: ast.AST) -> bool:
    """True for a `registry.invoke(...)` call node specifically — not any
    `.invoke(` on any object, to avoid a false negative from an unrelated
    `.invoke()` method elsewhere in a route body."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "invoke"
        and isinstance(func.value, ast.Name)
        and func.value.id == "registry"
    )


def _calls_registry_invoke(fn: ast.AST) -> bool:
    """Whether `registry.invoke(` appears anywhere in `fn`'s own body — a
    plain subtree walk. Deliberately does NOT trace into a helper function
    called from the body (no indirection tracing — see module docstring)."""
    for node in ast.walk(fn):
        if node is fn:
            continue
        if _is_registry_invoke_call(node):
            return True
    return False


def find_route_functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function (top-level, nested in a class, or nested in another
    function — a route handler need not be module-level) decorated with an
    HTTP-verb router call."""
    out: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(_is_route_decorator(dec) for dec in node.decorator_list):
            out.append(node)
    return out


def scan_file(path: pathlib.Path) -> tuple[int, list[dict]]:
    """(route_functions_found, findings) for one Python file."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        print(f"FAIL check_routes_use_action_layer: {path} does not parse: {exc}",
              file=sys.stderr)
        sys.exit(2)

    route_fns = find_route_functions(tree)
    findings: list[dict] = []
    for fn in route_fns:
        if _calls_registry_invoke(fn):
            continue
        findings.append({
            "file": str(path),
            "function": fn.name,
            "line": fn.lineno,
            "reason": f"decorated route `{fn.name}` has no `registry.invoke(` call in its own body",
        })
    return len(route_fns), findings


def scan_tree() -> tuple[int, list[dict]]:
    total_routes = 0
    all_findings: list[dict] = []
    for root in ROOTS:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            n, findings = scan_file(path)
            total_routes += n
            all_findings.extend(findings)
    return total_routes, all_findings


def _load_allowlist() -> list[dict]:
    if not ALLOWLIST_PATH.exists():
        return []
    try:
        return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL check_routes_use_action_layer: {ALLOWLIST_PATH} is malformed JSON: {exc}",
              file=sys.stderr)
        sys.exit(2)


def check() -> int:
    total_routes, findings = scan_tree()
    print(f"Scanned {total_routes} HTTP-mutating route function(s) under {', '.join(str(r) for r in ROOTS)}.")
    if total_routes == 0:
        print("FAIL check_routes_use_action_layer: found ZERO decorated routes — "
              "the scan itself is broken (the tree moved, or the detector regressed), "
              "not a clean result.", file=sys.stderr)
        return 2

    allowlist = _load_allowlist()
    allowed_keys: set[tuple[str, str]] = set()
    violation_keys: set[tuple[str, str]] = set()
    by_design_keys: set[tuple[str, str]] = set()
    failures: list[str] = []
    for entry in allowlist:
        key = (entry.get("file"), entry.get("function"))
        reason = (entry.get("reason") or "").strip()
        cls = entry.get("class")
        if cls not in ("violation", "by-design"):
            failures.append(
                f"{ALLOWLIST_PATH}: entry for {key} has no valid `class` "
                f"('violation' or 'by-design'), got {cls!r}."
            )
            continue
        if not reason:
            failures.append(f"{ALLOWLIST_PATH}: entry for {key} has no `reason`.")
            continue
        if cls == "violation":
            if not entry.get("issue"):
                failures.append(f"{ALLOWLIST_PATH}: violation entry for {key} has no `issue`.")
                continue
            violation_keys.add(key)
        else:
            by_design_keys.add(key)
        allowed_keys.add(key)

    current_keys = {(f["file"], f["function"]) for f in findings}
    stale = allowed_keys - current_keys
    for key in sorted(stale):
        kind = "by-design" if key in by_design_keys else "violation"
        failures.append(
            f"{ALLOWLIST_PATH}: allowlisted {kind} {key} no longer occurs — remove it (shrink-only)."
        )

    unallowlisted = [f for f in findings if (f["file"], f["function"]) not in allowed_keys]

    if unallowlisted:
        print(f"\n{len(unallowlisted)} NEW finding(s) (not allowlisted):")
        for f in unallowlisted:
            print(f"  {f['file']}:{f['line']} {f['function']} — {f['reason']}")
    if failures:
        print(f"\n{len(failures)} allowlist problem(s):")
        for msg in failures:
            print(f"  - {msg}")

    debt = len([f for f in findings if (f["file"], f["function"]) in violation_keys])
    by_design = len([f for f in findings if (f["file"], f["function"]) in by_design_keys])

    if unallowlisted or failures:
        print(
            f"\nFAIL check_routes_use_action_layer: {len(unallowlisted)} new finding(s), "
            f"{len(failures)} allowlist problem(s). "
            f"{debt} violation(s) [DEBT], {by_design} by-design (not counted as debt)."
        )
        return 1

    print(
        f"OK check_routes_use_action_layer: {len(findings)} finding(s) — "
        f"{debt} violation(s) [DEBT], {by_design} by-design, all allowlisted with a reason."
    )
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python scripts/check_routes_use_action_layer.py", file=sys.stderr)
        return 2
    return check()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
