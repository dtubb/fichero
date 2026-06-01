from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts" / "check_ui_wiring.py"
)
_SPEC = importlib.util.spec_from_file_location("check_ui_wiring", _SCRIPT)
assert _SPEC and _SPEC.loader
check_ui_wiring = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_ui_wiring)  # type: ignore[attr-defined]


def test_operation_token_wires_path_without_raw_url():
    openapi = {
        "paths": {
            "/api/providers/{provider_id}": {
                "get": {"operationId": "get_provider_api_providers_provider_id_get"}
            }
        }
    }
    specs = check_ui_wiring.endpoint_specs(openapi)
    src = "let response = try await client.api.getProviderApiProvidersProviderIdGet(.init(...))"
    assert check_ui_wiring._is_path_wired(
        specs[0]["path"], specs[0]["operations"], src
    )


def test_typo_method_name_does_not_count_as_wired():
    openapi = {
        "paths": {
            "/api/providers/{provider_id}": {
                "get": {"operationId": "get_provider_api_providers_provider_id_get"}
            }
        }
    }
    specs = check_ui_wiring.endpoint_specs(openapi)
    src = "client.api.getProvdierApiProvidersProviderIdGet(.init(...))"
    assert not check_ui_wiring._is_path_wired(
        specs[0]["path"], specs[0]["operations"], src
    )


def test_unwired_uses_operation_tokens_and_path_regex(monkeypatch, tmp_path):
    openapi = {
        "paths": {
            "/api/health": {"get": {"operationId": "health_check_api_health_get"}},
            "/api/providers": {"get": {"operationId": "list_providers_api_providers_get"}},
        }
    }
    # First endpoint wired by path literal, second wired by operation method token.
    src = """
    let raw = "/api/health"
    client.api.listProvidersApiProvidersGet(.init())
    """
    monkeypatch.setattr(check_ui_wiring, "surface_source", lambda _: src)
    miss = check_ui_wiring.unwired({}, openapi)
    assert miss == []
