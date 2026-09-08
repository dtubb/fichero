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

from fichero_server.models import Model, Provider, ProviderType
from fichero_server.api.routes.system.chat import get_app_database


@pytest.fixture(autouse=True)
def use_test_app_db(app_db):
    from fichero_server.api.main import app

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
    """The regression The report described hitting: a text-only model offered for a vision node."""
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


_LOCAL_RUNTIME_IDS = {"omlx", "spacy", "kraken", "whisper"}


def test_workflow_bar_lists_the_on_device_runtimes_out_of_the_box(client, app_db):
    """The Run Workflow bar reads /api/chat/providers. With NO configured
    providers the four on-device runtimes must still be listed (#4671) — the
    same shared always-present set /api/providers merges in — so a step's
    model menu can offer spaCy/Kraken/Whisper/oMLX. Suitability marking is the
    UI's job; the backend never silently filters them out.
    """
    payload = client.get("/api/chat/providers").json()
    by_id = {item["id"]: item for item in payload["items"]}

    assert _LOCAL_RUNTIME_IDS <= set(by_id)
    for rid in _LOCAL_RUNTIME_IDS:
        entry = by_id[rid]
        assert entry["available"] is True  # local: no key needed
        # A usable model id is offered (catalog default), so the menu isn't empty.
        assert entry["models"], f"{rid} listed with no model to pick"


def _local_entry(provider_type: str, model_id: str, capabilities: list[str], installed: bool):
    from fichero_server.llm.local_inference import LocalModelCatalogEntry

    return LocalModelCatalogEntry(
        provider_type=provider_type,
        model_id=model_id,
        display_name=model_id,
        capabilities=capabilities,
        installed=installed,
    )


def test_on_device_runtime_lists_its_installed_models(client, app_db, monkeypatch):
    """The workflow bar and the toolbar chip must see the SAME models Settings
    does. Settings' MLX row reads the local catalog; this endpoint read only
    app_db rows, which an always-present runtime never has — so both surfaces
    saw a lone catalog default (`local-model`, not a model) while Settings
    listed every download. Installed catalog entries ride here too, with the
    capabilities the catalog knows.
    """
    from fichero_server.api.routes.ai import local_inference

    monkeypatch.setattr(
        local_inference,
        "_local_catalog_entries",
        lambda: [
            _local_entry("omlx", "Chandra-OCR", ["text", "vision"], installed=True),
            _local_entry("omlx", "Qwen3-4B-Instruct", ["text"], installed=True),
            # Downloadable but NOT downloaded: cannot run, so not offered.
            _local_entry("omlx", "Qwen2.5-VL-3B", ["text", "vision"], installed=False),
            # Another runtime's download must not leak into MLX's list.
            _local_entry("whisper", "turbo", ["audio"], installed=True),
        ],
    )

    entry = next(i for i in client.get("/api/chat/providers").json()["items"] if i["id"] == "omlx")

    assert entry["models"] == ["Chandra-OCR", "Qwen3-4B-Instruct"]
    details = {d["model_id"]: d for d in entry["model_details"]}
    assert details["Chandra-OCR"]["supports_vision"] is True
    assert details["Qwen3-4B-Instruct"]["supports_vision"] is False
    assert details["Qwen3-4B-Instruct"]["capabilities"] == ["text"]

    whisper = next(i for i in client.get("/api/chat/providers").json()["items"] if i["id"] == "whisper")
    assert whisper["models"] == ["turbo"]


def test_on_device_runtime_with_nothing_installed_keeps_the_catalog_default(
    client, app_db, monkeypatch
):
    """Nothing downloaded yet: the row still offers the catalog default so the
    menu is never empty (the #4671 guarantee is unchanged)."""
    from fichero_server.api.routes.ai import local_inference

    monkeypatch.setattr(local_inference, "_local_catalog_entries", lambda: [])

    entry = next(i for i in client.get("/api/chat/providers").json()["items"] if i["id"] == "omlx")

    assert entry["models"], "an on-device runtime with no downloads still needs a pickable id"


def test_configured_rows_win_over_the_local_catalog(client, app_db, monkeypatch):
    """A user who explicitly configured MLX models keeps exactly those — the
    catalog fills the gap only where app_db has nothing to say."""
    from fichero_server.api.routes.ai import local_inference

    provider = _provider(app_db, "omlx")
    _model(app_db, provider, "my-pinned-model", ["text"])
    monkeypatch.setattr(
        local_inference,
        "_local_catalog_entries",
        lambda: [_local_entry("omlx", "Chandra-OCR", ["text", "vision"], installed=True)],
    )

    entry = next(i for i in client.get("/api/chat/providers").json()["items"] if i["id"] == "omlx")

    assert entry["models"] == ["my-pinned-model"]


def test_models_list_shape_is_unchanged(client, app_db):
    """`models` stays a plain id list so existing clients keep working."""
    provider = _provider(app_db)
    _model(app_db, provider, "apple-vision", ["vision"])

    entry = next(
        i for i in client.get("/api/chat/providers").json()["items"] if i["id"] == "apple"
    )

    assert entry["models"] == [d["model_id"] for d in entry["model_details"]]
    assert all(isinstance(m, str) for m in entry["models"])
