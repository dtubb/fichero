"""Contract endpoint walk (#1147).

Walks every GET operation in the live OpenAPI schema against a *seeded*
library and asserts no endpoint returns 500. This is the guard that the
shape-only ``test_api_contracts.py`` could never be: that suite uses a bare
``TestClient(app)`` with no ``X-Fichero-Library-Path`` header, so every
library endpoint short-circuits on the missing header and never serializes a
body. This walk supplies the header + seeded data, so FastAPI actually
validates each response against its declared ``response_model``.

That validation is exactly what catches the #1075 regression class: an
endpoint whose ``response_model`` is an envelope (``*ListResponse``) but whose
body still returns a bare ``list`` — Pydantic can't coerce a list into the
envelope model, so it raises ``ResponseValidationError`` → 500. A bare list
fails this check even when the library is empty, so the walk surfaces the
mismatch regardless of seeded content.
"""

import os

import pytest
from fastapi.testclient import TestClient

# Match conftest's environment contract before importing the app.
os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
os.environ.setdefault("FICHERO_DISABLE_AUTH", "1")

from fichero_server.api.main import app, get_library_database  # noqa: E402
from fichero_server.api.routes.providers import get_app_database  # noqa: E402
from fichero_server.db import db_manager  # noqa: E402

# Seeded IDs reused across path-param substitution so nested list endpoints
# (e.g. /entities/{entity_id}/documents) reach their serialize path instead of
# 404-ing before the response_model is exercised. Sourced from the shared
# seeder (one ground-truth library for engine + CLI + Swift).
SEED_DOC_ID = "test-doc-letter"
SEED_ENTITY_ID = "test-ent-person"
SEED_CLAIM_ID = "test-claim-1"

_PARAM_VALUES = {
    "doc_id": SEED_DOC_ID,
    "document_id": SEED_DOC_ID,
    "entity_id": SEED_ENTITY_ID,
    "claim_id": SEED_CLAIM_ID,
}
_PARAM_FALLBACK = "contract-walk-nonexistent"


def _fill_path(template: str) -> str | None:
    """Substitute {param} placeholders. Returns None if a param is unfillable
    in a way we can't reason about (we still fill with a fallback, so this
    currently always returns a concrete path)."""
    out = template
    while "{" in out:
        start = out.index("{")
        end = out.index("}", start)
        name = out[start + 1 : end]
        value = _PARAM_VALUES.get(name, _PARAM_FALLBACK)
        out = out[:start] + value + out[end + 1 :]
    return out


@pytest.fixture
def walk_client(tmp_path):
    from tests.integration._seedlib import seed

    package_path = tmp_path / "walk.fichero"
    seed(package_path)  # builds the full deterministic library + closes the db

    from fichero_server.db.app import AppDatabase
    import fichero_server.db.app as _app_db_module

    app_db = AppDatabase(path=tmp_path / "walk_app.duckdb")
    saved_singleton = _app_db_module._app_db
    _app_db_module._app_db = app_db

    app.dependency_overrides[get_app_database] = lambda: app_db
    app.dependency_overrides[get_library_database] = lambda: db_manager.get_database(package_path)

    # raise_server_exceptions=False so a 500 comes back as a response we can
    # collect, instead of an exception that aborts the whole walk on the
    # first broken endpoint.
    client = TestClient(
        app,
        headers={"X-Fichero-Library-Path": str(package_path)},
        raise_server_exceptions=False,
    )
    yield client

    app.dependency_overrides.clear()
    _app_db_module._app_db = saved_singleton
    app_db.close()
    db_manager.close_all()


# GET endpoints that perform external/blocking I/O (HuggingFace model lists,
# live integration/provider probes). A bare ``TestClient`` runs the endpoint
# synchronously in-process, so a sync network call with no timeout hangs the
# whole walk. These are out of scope for the #1149 envelope sweep.
_SKIP_PREFIXES = (
    "/api/integrations/",  # /{app_name}/items probes the live app
    "/api/models",  # HuggingFace task/model catalogues
)


def _list_response_ref(op: dict) -> str | None:
    """Return the schema name of a GET op's 200 body if it is an object
    ``$ref`` (the envelope class name), else None."""
    schema = (
        op.get("responses", {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    ref = schema.get("$ref", "")
    if ref:
        return ref.rsplit("/", 1)[-1]
    return None


def _envelope_get_paths() -> list[tuple[str, str]]:
    """GET paths whose 200 body is a ``*ListResponse`` envelope — the #1149
    surface. Returns (path_template, response_model_name)."""
    schema = app.openapi()
    out = []
    for template, methods in schema.get("paths", {}).items():
        if any(template.startswith(p) for p in _SKIP_PREFIXES):
            continue
        op = methods.get("get")
        if not op:
            continue
        model = _list_response_ref(op)
        if model and model.endswith("ListResponse"):
            out.append((template, model))
    return sorted(out)


def test_no_envelope_get_endpoint_returns_500(walk_client):
    failures = []
    for template, model in _envelope_get_paths():
        print(f"  GET {template}  -> {model}", flush=True)
        path = _fill_path(template)
        if path is None:
            continue
        try:
            resp = walk_client.get(path)
        except Exception as exc:  # pragma: no cover - defensive
            failures.append((template, "EXC", repr(exc)[:300]))
            continue
        if resp.status_code == 500:
            body = resp.text[:300]
            failures.append((template, 500, body))

    if failures:
        lines = [f"  {t} -> {code}: {detail}" for t, code, detail in failures]
        pytest.fail(
            f"{len(failures)} GET endpoint(s) returned 500 against a seeded library:\n"
            + "\n".join(lines)
        )


# Bare-array GET endpoints still awaiting envelope conversion. This sweep
# converts every list endpoint to a {items, count} envelope in staged commits
# (KG cluster → documents/workflows → providers/search/chat). The backlog must
# shrink to empty by the final commit; until then the guard asserts only that
# NO NEW bare-array endpoint appears. Remove an entry the moment its endpoint
# is converted so a regression that re-introduces a bare list is caught.
_BARE_ARRAY_BACKLOG = set()


def test_no_new_bare_array_get_endpoint():
    """Consistency guard: list endpoints must return a ``{items, count}``
    envelope, never a bare JSON array. A ``response_model=list[X]`` shows up
    in the OpenAPI schema as a 200 body of ``type: array``. Anything outside
    the known shrinking backlog is a regression — the bare-list/envelope split
    that caused #1075 reappearing."""
    schema = app.openapi()
    offenders = set()
    for template, methods in schema.get("paths", {}).items():
        op = methods.get("get")
        if not op:
            continue
        body = (
            op.get("responses", {})
            .get("200", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        if body.get("type") == "array":
            offenders.add(template)

    new_offenders = offenders - _BARE_ARRAY_BACKLOG
    if new_offenders:
        pytest.fail(
            "New bare-array GET endpoint(s) — list endpoints must return a "
            "{items, count} envelope, not a bare array:\n  "
            + "\n  ".join(sorted(new_offenders))
        )

    # Keep the backlog honest: an entry that's already been converted must be
    # removed, or it silently masks a future regression on that path.
    stale = _BARE_ARRAY_BACKLOG - offenders
    if stale:
        pytest.fail(
            "Stale backlog entries (already envelopes — remove from "
            "_BARE_ARRAY_BACKLOG):\n  " + "\n  ".join(sorted(stale))
        )
