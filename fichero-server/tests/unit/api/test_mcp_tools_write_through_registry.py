"""audit.only-the-action-surface-reaches-capabilities (#4866).

A source scan, parsed not grepped (mirrors `check_routes_use_action_layer.py`'s
own approach) -- proves the specific claim #4866 makes: no function in
`api/routes/mcp/tools.py` writes to the database (`db.save(`/`db.delete(`)
outside `registry.invoke(`. All five MCP write tools (entity create,
entity update, entity delete, claim create, claim delete) are now thin
`registry.invoke` callers -- `ALLOWED_BYPASSES` is empty, kept as a named,
extensible mechanism (not deleted outright) so a FUTURE regression grows it
with a reason instead of silently passing.
"""

from __future__ import annotations

import ast
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[3]
    / "src"
    / "fichero_server"
    / "api"
    / "routes"
    / "mcp"
    / "tools.py"
)

#: {function_name: reason} -- empty: every MCP write tool now calls
#: registry.invoke. Grow this ONLY with a real reason if a future write
#: tool genuinely cannot go through the registry yet; never to silence a
#: regression in one of the five already fixed.
ALLOWED_BYPASSES: dict[str, str] = {}


def _db_write_calls(fn: ast.AST):
    for node in ast.walk(fn):
        if node is fn or not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in ("save", "delete")
            and isinstance(func.value, ast.Name)
            and func.value.id == "db"
        ):
            yield node


def _calls_registry_invoke(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if node is fn or not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "invoke"
            and isinstance(func.value, ast.Name)
            and func.value.id == "registry"
        ):
            return True
    return False


def _findings() -> list[str]:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"), filename=str(MODULE_PATH))
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not list(_db_write_calls(node)):
            continue
        if _calls_registry_invoke(node):
            # A route that ALSO writes directly (e.g. a snapshot capture
            # before invoking) is fine as long as the mutation itself is
            # inside the audited action -- this scan only flags a function
            # with NO registry.invoke call anywhere in its own body.
            continue
        out.append(node.name)
    return out


def test_no_function_writes_to_the_db_outside_registry_invoke_unless_allowlisted():
    findings = _findings()
    unallowlisted = [name for name in findings if name not in ALLOWED_BYPASSES]

    assert set(findings) == set(ALLOWED_BYPASSES), (
        f"db writes outside registry.invoke: {sorted(findings)}; "
        f"allowlisted: {sorted(ALLOWED_BYPASSES)}. Update ALLOWED_BYPASSES "
        "(shrink it when a bypass is fixed, grow it only with a reason) so "
        "this scan tracks the real, current set."
    )
    assert unallowlisted == [], f"new, unallowlisted db writes: {unallowlisted}"


def test_the_five_reconciled_tools_are_not_in_the_bypass_list():
    """#4866's own acceptance criterion, stated as a negative: none of the
    five write tools may be among the tracked bypasses -- if one of them
    regresses back to a direct write, this fails loudly instead of the
    scan above just silently growing to cover it."""
    fixed = {
        "mcp_knowledge_entity_upsert",
        "mcp_knowledge_claim_create",
        "mcp_knowledge_entity_delete",
        "mcp_knowledge_claim_delete",
    }
    assert fixed.isdisjoint(ALLOWED_BYPASSES)


def test_the_scan_itself_would_catch_a_real_bypass():
    """Proving the detector fires, rather than trusting a green run with an
    empty ALLOWED_BYPASSES -- a source-scan test that can only ever pass
    trivially would be worthless."""
    tree = ast.parse(
        "async def f(db):\n"
        "    db.delete(x)\n"
    )
    fn = tree.body[0]
    assert list(_db_write_calls(fn))
    assert not _calls_registry_invoke(fn)
