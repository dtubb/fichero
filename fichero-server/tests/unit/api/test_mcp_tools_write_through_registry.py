"""audit.only-the-action-surface-reaches-capabilities (#4866).

A source scan, parsed not grepped (mirrors `check_routes_use_action_layer.py`'s
own approach) -- proves the specific claim #4866 makes: no function in
`api/routes/mcp/tools.py` writes to the database (`db.save(`/`db.delete(`)
outside `registry.invoke(`. The three writes named in #4866 (entity update,
entity create, claim create) are now thin `registry.invoke` callers; the two
NOT named (`mcp_knowledge_entity_delete`, `mcp_knowledge_claim_delete`) still
bypass the registry entirely -- allowlisted here BY NAME with a reason, not
silently passed, so this scan stays honest about what it does and does not
cover.
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

#: {function_name: reason} -- #4866 fixed only the three named in the issue;
#: these two are real, pre-existing bypasses, tracked for a future fix
#: (queued for #4831's next batch), not silently passed by this scan.
ALLOWED_BYPASSES: dict[str, str] = {
    "mcp_knowledge_entity_delete": (
        "hard db.delete() with no registry.invoke, no ActionAudit, not even a "
        "MutationLog -- pre-existing, #4866 named only the three write tools "
        "(entity update/create, claim create), not the delete routes."
    ),
    "mcp_knowledge_claim_delete": (
        "same as mcp_knowledge_entity_delete -- hard db.delete() with no "
        "audit trail at all."
    ),
}


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


def test_no_function_writes_to_the_db_outside_registry_invoke_unless_allowlisted():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"), filename=str(MODULE_PATH))
    findings: list[str] = []
    unallowlisted: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        writes = list(_db_write_calls(node))
        if not writes:
            continue
        if _calls_registry_invoke(node):
            # A route that ALSO writes directly (e.g. a snapshot capture
            # before invoking) is fine as long as the mutation itself is
            # inside the audited action -- this scan only flags a function
            # with NO registry.invoke call anywhere in its own body.
            continue
        findings.append(node.name)
        if node.name not in ALLOWED_BYPASSES:
            unallowlisted.append(node.name)

    assert findings, (
        "found ZERO db-write functions with no registry.invoke -- the scan "
        "itself may be broken (mcp/tools.py changed shape), not a clean result"
    )
    assert set(findings) == set(ALLOWED_BYPASSES), (
        f"db writes outside registry.invoke: {sorted(findings)}; "
        f"allowlisted: {sorted(ALLOWED_BYPASSES)}. Update ALLOWED_BYPASSES "
        "(shrink it when a bypass is fixed, grow it only with a reason) so "
        "this scan tracks the real, current set."
    )
    assert unallowlisted == [], f"new, unallowlisted db writes: {unallowlisted}"


def test_the_three_reconciled_tools_are_not_in_the_bypass_list():
    """#4866's own acceptance criterion, stated as a negative: the three
    named tools must NOT be among the tracked bypasses -- if one of them
    regresses back to a direct write, this fails loudly instead of the
    scan above just silently growing to cover it."""
    fixed = {
        "mcp_knowledge_entity_upsert",
        "mcp_knowledge_claim_create",
    }
    assert fixed.isdisjoint(ALLOWED_BYPASSES)
