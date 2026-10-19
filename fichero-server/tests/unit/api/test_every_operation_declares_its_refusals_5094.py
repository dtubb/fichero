"""`engine.error-detail-reaches-the-caller`, engine half (#5094): refusals share one error body.

The app-wide declaration of 400/403/404/409 on every operation was WITHDRAWN (review 112): it turned each into a typed
case and broke the Swift branches that read those statuses through `.undocumented(...)`. Routes whose clients read the
body declare it themselves, as #5089 did (`test_structured_refusals_declared_5094.py`).
"""
from __future__ import annotations


def test_one_shared_error_body_class():
    from fichero_server.api.errors import ErrorDetail
    from fichero_server.api.routes.document.format_import import ErrorDetail as imported

    assert imported is ErrorDetail
