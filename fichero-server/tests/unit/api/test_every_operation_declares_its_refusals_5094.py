"""`engine.error-detail-reaches-the-caller`, engine half (#5094): every operation declares its refusals.

WHY: 377 of 416 operations declared only 200/422 while raising 766 4xx refusals, so the generated Swift client could
not decode the sentence a refusal sends (`{"detail": "<a sentence>"}`). 422 is FastAPI's own and stays as it is.
"""
from __future__ import annotations

import pytest

from fichero_server.api.main import app

REFUSALS = ("400", "403", "404", "409")
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _operations():
    for path, item in app.openapi()["paths"].items():
        for method, op in item.items():
            if method in HTTP_METHODS:
                yield f"{method.upper()} {path}", op


def test_one_shared_error_body_class():
    from fichero_server.api.errors import ErrorDetail
    from fichero_server.api.routes.document.format_import import ErrorDetail as imported

    assert imported is ErrorDetail


def test_the_default_is_the_shared_body():
    """Most operations carry ErrorDetail; only a route that names its own model differs."""
    ops = list(_operations())
    shared = sum(
        1 for _, op in ops
        if any(m.get("schema", {}).get("$ref", "").endswith("/ErrorDetail") for m in op["responses"]["404"]["content"].values())
    )
    assert shared > len(ops) * 0.9


@pytest.mark.parametrize("status", REFUSALS)
def test_every_operation_declares_a_body_for_the_refusal(status):
    bad = []
    for name, op in _operations():
        content = (op["responses"].get(status) or {}).get("content", {})
        # a body schema under any media type: the shared ErrorDetail by default, or the route's own deliberate model
        if not any(m.get("schema") for m in content.values()):
            bad.append(name)
    assert not bad, f"{len(bad)} operations do not declare a body for {status}, e.g. {bad[:3]}"
