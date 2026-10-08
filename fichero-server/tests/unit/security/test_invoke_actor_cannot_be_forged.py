"""audit.actor-cannot-be-forged (#4844): `POST /api/actions/invoke` refuses a
body that names its own `actor` or `origin_window`, runs nothing and writes
no audit row; the actor on a real invoke comes from the request, never the
body. Temp library (`client`/`db` fixtures), never a real one."""

from __future__ import annotations

import pytest

from fichero_server.models import ActionAudit
from fichero_server.models.knowledge import KnowledgeEntity

PARAMS = {"canonical_name": "Forged Person", "entity_type": "person"}


@pytest.mark.parametrize(
    "forged", [{"actor": "mallory"}, {"origin_window": "someone-elses-window"}]
)
def test_a_forged_field_is_rejected_and_nothing_runs(client, db, forged):
    response = client.post(
        "/api/actions/invoke",
        json={"name": "entity.create", "params": PARAMS, **forged},
    )

    assert response.status_code == 422
    field = next(iter(forged))
    assert f"{field} must not be set in the request body" in response.text
    assert not [e for e in db.all(KnowledgeEntity) if e.canonical_name == "Forged Person"]
    assert not [a for a in db.all(ActionAudit) if a.action_name == "entity.create"]


def test_the_same_invoke_without_the_field_runs_under_the_request_actor(client, db):
    response = client.post(
        "/api/actions/invoke", json={"name": "entity.create", "params": PARAMS}
    )

    assert response.status_code == 200, response.text
    audit = db.get(ActionAudit, response.json()["audit_id"])
    assert audit is not None
    assert audit.actor and audit.actor != "mallory"
