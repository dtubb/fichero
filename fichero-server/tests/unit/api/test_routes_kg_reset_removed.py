"""#4982: `POST /kg/reset` is DELETED, not repaired.

The route deleted every KnowledgeEntity/KnowledgeClaim/KnowledgeClaimLink row
in the library — curated or not — with no filter, no audit record, no
confirmation, and only ordinary write permission. It could never actually
run: it called `db.delete(Model, id)` with two arguments against a
one-argument method, and its only test (deleted alongside it, see
`test_routes_kg_rebuild.py`'s module docstring) passed only because it faked
that wrong signature.

Two tests, as briefed:
1. The operation is gone from the OpenAPI schema — nothing can reach it.
2. A broader, narrowly-stated guard: no route handler anywhere under
   `api/routes/` calls `Database.delete(KnowledgeEntity, ...)` or
   `Database.delete(KnowledgeClaim, ...)` directly. This is deliberately
   narrower than "no route bulk-deletes KG rows" (too vague to assert
   cleanly) — it targets the EXACT mechanism #4982 used. Every real,
   audited entity/claim delete already goes through a helper
   (`delete_entity_impl`, etc.) that does NOT call `db.delete(KnowledgeEntity`
   /`db.delete(KnowledgeClaim` directly either, so this holds today with no
   allowlist; a regression that reintroduces a direct bulk `db.delete` call
   on either model, inside or outside the action layer, fails it.
"""

from __future__ import annotations

import ast
import os
import pathlib

import pytest

ROUTES_ROOT = pathlib.Path(__file__).resolve().parents[3] / (
    "src/fichero_server/api/routes"
)
_TARGET_MODELS = {"KnowledgeEntity", "KnowledgeClaim"}


def _is_direct_kg_delete_call(node: ast.AST) -> str | None:
    """Return the model name if `node` is `<anything>.delete(<ModelName>, ...)`."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "delete"):
        return None
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Name) and first.id in _TARGET_MODELS:
        return first.id
    return None


def _direct_kg_delete_findings() -> list[str]:
    findings: list[str] = []
    for path in sorted(ROUTES_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            model = _is_direct_kg_delete_call(node)
            if model:
                findings.append(f"{path.relative_to(ROUTES_ROOT)}:{node.lineno} .delete({model}, ...)")
    return findings


def test_kg_reset_operation_absent_from_openapi():
    os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
    from fichero_server.api.main import app

    spec = app.openapi()
    assert "/api/kg/reset" not in spec["paths"], (
        "POST /api/kg/reset must not exist — #4982 deletes it, not repairs it"
    )


def test_no_route_handler_bulk_deletes_kg_rows_directly():
    """No route under api/routes/ calls `db.delete(KnowledgeEntity, ...)` or
    `db.delete(KnowledgeClaim, ...)` directly — the exact #4982 mechanism.
    Real audited deletes go through a helper (`delete_entity_impl` etc.)
    that never does this either, so this assertion needs no allowlist."""
    findings = _direct_kg_delete_findings()
    assert findings == [], (
        "found a direct db.delete(KnowledgeEntity/KnowledgeClaim, ...) call "
        f"under api/routes/ — the #4982 shape:\n" + "\n".join(findings)
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
