"""Per-model capability in the chat providers payload (#4187).

The app builds its Run Workflow provider/model submenu from
``GET /api/chat/providers``. Before this, the payload carried only
PROVIDER-level ``supports_vision``, so the menu could offer a text-only
model (``apple/apple-intelligence``) for a vision node — which then failed
at run time with "not marked as vision-capable".

The fallback these tests pin is the subtle part: capability enforcement is
tri-state (no saved capabilities means "unknown", not "unsupported"), so a
model with an empty capability list must INHERIT the provider's vision
support rather than be reported as text-only.
"""

import pytest

from fichero.models import Model, Provider, ProviderType
from fichero.api.routes.system.chat import get_app_database


@pytest.fixture(autouse=True)
def use_test_app_db(app_db):
    from fichero.api.main import app

    app.dependency_overrides[get_app_database] = lambda: app_db
    yield
    app.dependency_overrides.pop(get_app_database, None)


def _provider(app_db, ptype: str = "apple") -> Provider:
    provider = Provider(
        name=f"Test {ptype}",
        provider_type=ProviderType(ptype),
        enabled=True,
    )
    app_db.save_provider(provider)
    return provider


def _model(app_db, provider: Provider, model_id: str, capabilities: list[str]) -> Model:
    model = Model(
        provider_id=provider.id,
        name=model_id,
        model_id=model_id,
        capabilities=capabilities,
        enabled=True,
    )
    app_db.save_model(model)
    return model


def _details(client, provider_type: str) -> dict[str, dict]:
    response = client.get("/api/chat/providers")
    assert response.status_code == 200
    payload = response.json()
    entry = next(item for item in payload["items"] if item["id"] == provider_type)
    return {d["model_id"]: d for d in entry["model_details"]}


def test_vision_capability_is_reported_per_model(client, app_db):
    provider = _provider(app_db)
    _model(app_db, provider, "apple-vision", ["vision"])

    detail = _details(client, "apple")["apple-vision"]

    assert detail["supports_vision"] is True
    assert "vision" in detail["capabilities"]


def test_text_only_model_is_not_reported_vision_capable(client, app_db):
    """The regression Daniel hit: a text-only model offered for a vision node."""
    provider = _provider(app_db)
    _model(app_db, provider, "apple-intelligence", ["llm"])

    detail = _details(client, "apple")["apple-intelligence"]

    assert detail["supports_vision"] is False
    assert detail["capabilities"] == ["llm"]


def test_empty_capabilities_inherit_provider_vision_support(client, app_db):
    """Tri-state guard: unknown capabilities must NOT read as unsupported.

    ``_model_has_capability`` returns None for a model with no saved
    capabilities and callers fall back to the provider. If this collapsed to
    ``"vision" in capabilities`` the menu would hide models that run fine.
    """
    provider = _provider(app_db)
    _model(app_db, provider, "some-unlabelled-model", [])

    response = client.get("/api/chat/providers")
    entry = next(i for i in response.json()["items"] if i["id"] == "apple")
    detail = {d["model_id"]: d for d in entry["model_details"]}["some-unlabelled-model"]

    assert detail["capabilities"] == []
    assert detail["supports_vision"] is entry["supports_vision"]


def test_catalog_default_model_has_no_row_and_inherits_provider(client, app_db):
    """Fresh install: no configured models, so the id is synthesized from the
    catalog default and has no DB row to carry capabilities."""
    _provider(app_db)

    response = client.get("/api/chat/providers")
    entry = next(i for i in response.json()["items"] if i["id"] == "apple")

    assert entry["model_details"], "catalog-default model must still be described"
    for detail in entry["model_details"]:
        assert detail["capabilities"] == []
        assert detail["supports_vision"] is entry["supports_vision"]


def test_models_list_shape_is_unchanged(client, app_db):
    """`models` stays a plain id list so existing clients keep working."""
    provider = _provider(app_db)
    _model(app_db, provider, "apple-vision", ["vision"])

    entry = next(
        i for i in client.get("/api/chat/providers").json()["items"] if i["id"] == "apple"
    )

    assert entry["models"] == [d["model_id"] for d in entry["model_details"]]
    assert all(isinstance(m, str) for m in entry["models"])
