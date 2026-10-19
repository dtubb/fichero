"""Set Up end to end with an explicit owner (overnight plan 2026-10-18): a fresh library, signed in by key, then Set Up and Start.

Order: first-run (200 on a fresh library) -> sign-in by challenge -> the owner's session token as the bearer ->
GET /api/recipes/stages -> PUT /api/recipes/project (the three intake choices) -> GET the start plan -> POST start.
Runs with Multi-user on: with it unset the engine takes only the bootstrap bearer on loopback (GET identity with a
session token is 401), so the walk with the bootstrap bearer, as the app sends it today, is in ec193f84b. It was set
aside because it counts as the ambient owner. Any refusal is a finding: each assertion names the route and detail.
"""

import pytest

from fichero_server.models import DocType, Document, FileType
from fichero_server.workflows.default_workflows import seed_default_workflows
from tests.signed_in import new_key, signature_for, uds_client
from tests.unit.recipes.test_recipe_execution_to_spec import _png
from tests.unit.security.test_sharing_probe_2026_10_01 import harness  # noqa: F401

SECRET = "ef" * 32
INTAKE = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "material": "print"}


@pytest.fixture(autouse=True)
def engine_secret():
    from fichero_server.security import launch_secret

    launch_secret.set_secret(SECRET)
    yield
    launch_secret.set_secret(None)


def _ok(response, route):
    assert response.status_code == 200, f"{route} refused {response.status_code}: {response.text}"
    return response.json()


def test_a_fresh_library_goes_from_first_launch_through_set_up_to_start(harness, monkeypatch, tmp_path):
    # As it will run after slice 10: Multi-user always on, no bootstrap bearer, the owner's session token.
    # With Multi-user unset the engine takes only the bootstrap bearer, not the session token (GET identity 401), so the
    # Set Up walk with an explicit owner needs Multi-user on; the bootstrap-bearer version is in ec193f84b.
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    key, pem = new_key()
    sock = uds_client(harness)
    sent = {"X-Fichero-Launch-Secret": SECRET}
    body = {"public_key_pem": pem, "client": {"kind": "app", "name": "Fichero", "host": "MacBook Pro"}}
    # Nothing made a keyless owner first (no loopback bootstrap request), so first-run answers 200, not 409.
    made = sock.post("/api/auth/first-run", json={**body, "display_name": "Daniel"}, headers=sent)
    client_id = _ok(made, "POST /api/auth/first-run")["client"]["id"]
    issued = _ok(sock.post("/api/auth/challenge", json={"client_id": client_id}), "POST /api/auth/challenge")
    signed = _ok(
        sock.post(
            "/api/auth/sign-in",
            json={"client_id": client_id, "nonce": issued["nonce"], "signature": signature_for(key, client_id, issued)},
        ),
        "POST /api/auth/sign-in",
    )
    app = harness.client()
    app.headers["Authorization"] = f"Bearer {signed['session_token']}"

    from fichero_server.db import db_manager

    library = db_manager.get_database(harness.library)
    seed_default_workflows(library)
    library.save(Document(name="p0.png", doc_type=DocType.file, file_type=FileType.image, path=str(_png(tmp_path / "p0.png"))))

    stages = _ok(app.get("/api/recipes/stages"), "GET /api/recipes/stages")
    assert stages["count"] == len(stages["items"]) and stages["count"] > 0
    _ok(app.put("/api/recipes/project", json={"answers": INTAKE}), "PUT /api/recipes/project")
    saved = _ok(app.get("/api/recipes/project"), "GET /api/recipes/project")
    assert saved["recipe"] is not None, "PUT /api/recipes/project stored no recipe"
    _ok(app.get("/api/recipes/project/start"), "GET /api/recipes/project/start")
    started = _ok(app.post("/api/recipes/project/start", json={}), "POST /api/recipes/project/start")
    assert started.get("runs") or started.get("workflows"), f"POST /api/recipes/project/start ran nothing: {started}"


# Named exception in scripts/check_no_ambient_owner_in_tests.py: the app ships with the bootstrap bearer until slice 10.
def test_the_shipped_embedded_path_with_the_bootstrap_bearer(harness, monkeypatch, tmp_path):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    app = harness.host()  # loopback, the bootstrap bearer, as the app sends it

    # The app's first calls reach the engine before sign-in, and make the keyless owner.
    _ok(app.get("/api/auth/identity"), "GET /api/auth/identity")

    # First launch: first-run answers 409 (an owner exists), so the key goes on that owner; then sign-in.
    key, pem = new_key()
    sock = uds_client(harness)
    sent = {"X-Fichero-Launch-Secret": SECRET}
    body = {"public_key_pem": pem, "client": {"kind": "app", "name": "Fichero", "host": "MacBook Pro"}}
    first = sock.post("/api/auth/first-run", json={**body, "display_name": "Daniel"}, headers=sent)
    assert first.status_code == 409, f"POST /api/auth/first-run: {first.status_code} {first.text}"
    client_id = _ok(sock.post("/api/auth/migrate-owner", json=body, headers=sent), "POST /api/auth/migrate-owner")[
        "client"
    ]["id"]
    issued = _ok(sock.post("/api/auth/challenge", json={"client_id": client_id}), "POST /api/auth/challenge")
    _ok(
        sock.post(
            "/api/auth/sign-in",
            json={"client_id": client_id, "nonce": issued["nonce"], "signature": signature_for(key, client_id, issued)},
        ),
        "POST /api/auth/sign-in",
    )

    # A page to read, as an import would leave.
    from fichero_server.db import db_manager

    library = db_manager.get_database(harness.library)
    seed_default_workflows(library)
    library.save(Document(name="p0.png", doc_type=DocType.file, file_type=FileType.image, path=str(_png(tmp_path / "p0.png"))))

    # Set Up, in the app's order.
    stages = _ok(app.get("/api/recipes/stages"), "GET /api/recipes/stages")
    assert stages["count"] == len(stages["items"]) and stages["count"] > 0
    _ok(app.put("/api/recipes/project", json={"answers": INTAKE}), "PUT /api/recipes/project")
    saved = _ok(app.get("/api/recipes/project"), "GET /api/recipes/project")
    assert saved["recipe"] is not None, "PUT /api/recipes/project stored no recipe, so Start has nothing to run"
    plan = _ok(app.get("/api/recipes/project/start"), "GET /api/recipes/project/start")
    started = _ok(app.post("/api/recipes/project/start", json={}), "POST /api/recipes/project/start")
    assert started.get("runs") or started.get("workflows"), f"POST /api/recipes/project/start ran nothing: {started}"
    assert plan is not None
