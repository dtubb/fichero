"""Unit-test fixtures that authenticate route-test TestClient requests.

The parent conftest disables the shared-secret middleware via
FICHERO_DISABLE_AUTH=1 so legacy route tests can focus on response shape.
The engine now runs with multi-user auth by default, so route requests also
need a valid bearer token. This conftest re-attaches the auth middleware
using the engine's current bootstrap token and injects the matching
Authorization header into every TestClient created by the shared client
fixture.
"""

import pytest

from fichero_server.api.auth import attach_auth_middleware, initialize_token
from fichero_server.api.main import app

_UNIT_TEST_AUTH_TOKEN: str | None = None
_AUTH_MIDDLEWARE_ATTACHED = False

# Attach the enforcing auth middleware to the shared app ONCE, at conftest LOAD —
# before any test module is collected. Historically, a module-level
# `TestClient(app)` could start the shared app's lifespan during collection; if
# the middleware weren't already attached by then, that first `add_middleware`
# would raise "Cannot add middleware after an application has started" and —
# because it raises before the guard flips True — cascade to EVERY later test's
# setup (the 7941-error storm, #4039). Attaching here, before any test module
# imports, closes that window. The autouse fixture below stays as an idempotent
# safety net.
_UNIT_TEST_AUTH_TOKEN = initialize_token()
attach_auth_middleware(app, _UNIT_TEST_AUTH_TOKEN)
_AUTH_MIDDLEWARE_ATTACHED = True


@pytest.fixture(autouse=True)
def _unit_test_single_user_env(monkeypatch):
    """Force single-user mode for unit tests that drive the action registry directly.

    The engine ships with multi-user auth ON by default (``fichero/multiuser.py``),
    so ``authz.assert_can_write`` denies an unresolved actor like ``"ui"`` /
    ``"workflow"`` unless a library role row exists. The action-mechanics tests
    (``test_action_*``, ``test_*_actions``, ``test_canvas_*``) call
    ``registry.invoke(ActionContext(actor="ui", ...))`` directly — no HTTP, no
    authenticated user, no role — so they need the single-user bypass that
    ``FICHERO_MULTIUSER=0`` restores. This is the centralized sweep of the per-file
    fix landed in 6be649fd (#2642).

    Tests that exercise multi-user behaviour (``test_authz_*``, ``test_multiuser``,
    ``test_api_auth*``, ``test_auth_accounts``) explicitly ``monkeypatch.setenv`` the
    flag themselves; because ``monkeypatch`` is per-test and autouse fixtures run
    before the test body, a test's own ``setenv`` always wins over this default.
    """
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    yield


@pytest.fixture(autouse=True)
def _unit_test_auth_header():
    """Re-attach the auth middleware bound to the engine bootstrap token.

    Must NOT depend on the ``client`` fixture: ``client`` pulls in
    ``test_package``, which writes ``<tmp_path>/test.fichero/...`` into the
    per-test ``tmp_path``. Tests that scan ``tmp_path`` (ingest discovery) or
    build their own ``Database(tmp_path / "test.fichero")`` (canonical KG routes)
    then collide with that package. The actual token header is injected into
    every TestClient request by ``_unit_test_auth_all_testclients`` below, so the
    shared ``client`` fixture is still authenticated without being force-created
    for tests that never ask for it.
    """
    global _UNIT_TEST_AUTH_TOKEN, _AUTH_MIDDLEWARE_ATTACHED
    if _UNIT_TEST_AUTH_TOKEN is None:
        _UNIT_TEST_AUTH_TOKEN = initialize_token()
    if not _AUTH_MIDDLEWARE_ATTACHED:
        attach_auth_middleware(app, _UNIT_TEST_AUTH_TOKEN)
        _AUTH_MIDDLEWARE_ATTACHED = True
    yield


@pytest.fixture(autouse=True)
def _unit_test_auth_all_testclients(monkeypatch):
    """Inject the bootstrap token into EVERY ``TestClient`` request, not just the
    shared ``client`` fixture.

    ``_unit_test_auth_header`` re-attaches the enforcing auth middleware to the
    shared ``app`` (module-global, persists for the whole session), but many
    route-test modules build their OWN bare ``TestClient(app)`` (e.g.
    ``test_library_entity_types``, ``test_routes_library``) instead of the
    shared fixture. Those clients carried no Authorization header
    and so 401'd against the re-attached middleware. Inject the token via
    ``setdefault`` so it never clobbers a header a security/negative-auth test set
    deliberately (those tests pass an explicit/empty/wrong header or run their own
    multi-user setup).
    """
    global _UNIT_TEST_AUTH_TOKEN
    if _UNIT_TEST_AUTH_TOKEN is None:
        _UNIT_TEST_AUTH_TOKEN = initialize_token()
    token_header = f"Bearer {_UNIT_TEST_AUTH_TOKEN}"

    from starlette.testclient import TestClient

    original_request = TestClient.request

    def _request_with_default_auth(self, *args, **kwargs):
        self.headers.setdefault("Authorization", token_header)
        return original_request(self, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", _request_with_default_auth)
    yield


@pytest.fixture
def project_says_yes(test_package):
    """The test project has said yes to cloud models (Set Up's `cloud_allowed`). A package sent to Hugging Face or a
    cluster now needs the project's yes AND the request's (`ai.where.batch-sends-ask-the-project`, #5368, review 672);
    tests of those starts say the project's yes here and keep the request's `pages_may_leave` as they had it. Merges into a
    setup the test already wrote."""
    import yaml

    path = test_package / "recipe" / "setup.yaml"
    path.parent.mkdir(exist_ok=True)
    answers = (yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None) or {}
    answers["cloud_allowed"] = True
    path.write_text(yaml.safe_dump(answers), encoding="utf-8")


@pytest.fixture
def cloud_call_project(tmp_path, monkeypatch):
    """A call to a cloud model is made inside a project that said yes to cloud models (the one egress gate, #5368: a call with
    no project open, or under a project that keeps its pages here, is not sent). For tests of the CALL's own behaviour (retries,
    caching, usage, truncation); the gate's refusals are pinned in `test_one_egress_gate_5368.py` and are not weakened. The test
    models carry a listed price, so the spending cap (which refuses an unpriced model) stays on and is met. It prices EVERY model:
    never opt a cap or egress test into it (those pin the refusals and set up their own project and prices)."""
    from fichero_server.llm import usage
    from fichero_server.observability import episodes

    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": {
        "input_cost_per_token": 1e-6, "output_cost_per_token": 1e-5})

    folder = tmp_path / "CloudYes.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\n", encoding="utf-8")
    token = episodes.set_library(str(tmp_path / "CloudYes.fichero"))
    try:
        yield str(tmp_path / "CloudYes.fichero")
    finally:
        episodes._episode_library_path.reset(token)
