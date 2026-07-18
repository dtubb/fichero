"""Focused coverage for the runtime security-scoped access route."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from fichero.api.routes import sandbox_access


def _payload(path: str = "/tmp/library.fichero", bookmark: str = "Ym9va21hcms="):
    return sandbox_access.SecurityScopedAccessRequest(path=path, bookmark=bookmark)


def test_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        sandbox_access.SecurityScopedAccessRequest(path="/tmp/library.fichero", bookmark="x", extra=True)


def test_grant_returns_success_and_reports_existing_access(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sandbox_access, "granted_paths", lambda: frozenset({"/tmp/library.fichero"}))
    monkeypatch.setattr(
        sandbox_access,
        "grant_access",
        lambda path, bookmark: calls.append((path, bookmark)) or True,
    )

    response = sandbox_access.create_security_scoped_access(_payload())

    assert response.model_dump() == {
        "path": "/tmp/library.fichero",
        "granted": True,
        "already_held": True,
    }
    assert calls == [("/tmp/library.fichero", "Ym9va21hcms=")]


def test_grant_failure_is_a_bad_request(monkeypatch):
    def fail(_path: str, _bookmark: str):
        raise sandbox_access.BookmarkGrantError("bookmark refused")

    monkeypatch.setattr(sandbox_access, "grant_access", fail)

    with pytest.raises(HTTPException) as caught:
        sandbox_access.create_security_scoped_access(_payload())

    assert caught.value.status_code == 400
    assert caught.value.detail == "bookmark refused"


def test_grant_success_does_not_claim_unheld_path(monkeypatch):
    monkeypatch.setattr(sandbox_access, "granted_paths", lambda: frozenset())
    monkeypatch.setattr(sandbox_access, "grant_access", lambda _path, _bookmark: True)

    response = sandbox_access.create_security_scoped_access(_payload())

    assert response.granted is True
    assert response.already_held is False
