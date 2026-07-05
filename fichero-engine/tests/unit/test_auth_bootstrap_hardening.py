from __future__ import annotations

import pytest

from fichero import accounts
from fichero.models import Conversation


def _ensure_owner(app_db) -> None:
    if app_db.get_user_by_username("owner") is None:
        app_db.create_user(
            username="owner",
            display_name="Owner",
            password_hash=accounts.hash_password("password"),
            is_owner=True,
        )


@pytest.mark.parametrize(
    "path",
    [
        "/api/workflows",
        "/api/documents",
        "/api/chat/conversations",
        "/api/entities",
        "/api/claims",
    ],
)
def test_multiuser_bootstrap_owner_can_read_library_routes(client, app_db, monkeypatch, path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    _ensure_owner(app_db)

    response = client.get(path)

    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"


def test_multiuser_bootstrap_owner_can_invoke_registry_writes_across_domains(
    client, db, app_db, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    _ensure_owner(app_db)

    db.save(Conversation(id="conv-bootstrap", title="Bootstrap chat", messages=[]))
    payloads = [
        (
            "workflow.create",
            {
                "name": "Bootstrap workflow",
                "description": "owner invariant coverage",
                "nodes": [],
                "edges": [],
            },
        ),
        ("document.create", {"name": "Bootstrap doc"}),
        ("conversation.duplicate", {"conversation_id": "conv-bootstrap"}),
        ("entity.create", {"canonical_name": "Bootstrap entity"}),
        ("claim.create", {"text": "Bootstrap claim"}),
    ]

    for action_name, params in payloads:
        response = client.post(
            "/api/actions/invoke",
            json={"name": action_name, "params": params},
        )
        assert (
            response.status_code == 200
        ), f"{action_name} returned {response.status_code}: {response.text}"

