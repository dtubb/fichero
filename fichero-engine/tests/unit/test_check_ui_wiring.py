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


def test_path_token_wires_endpoint_after_route_module_move():
    openapi = {
        "paths": {
            "/api/workflow-execution/execute": {
                "post": {"operationId": "execute_workflow_api_execution_execute_post"}
            }
        }
    }
    specs = check_ui_wiring.endpoint_specs(openapi)
    src = "try await client.api.executeWorkflowApiWorkflowExecutionExecutePost(.init(...))"
    assert check_ui_wiring._is_path_wired(
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


def test_coverage_matrix_groups_by_domain(monkeypatch):
    openapi = {
        "paths": {
            "/api/auth/login": {"post": {"operationId": "login_api_auth_login_post"}},
            "/api/auth/logout": {"post": {"operationId": "logout_api_auth_logout_post"}},
            "/api/search": {"get": {"operationId": "search_api_search_get"}},
        }
    }
    monkeypatch.setattr(
        check_ui_wiring,
        "unwired",
        lambda surface, _: (
            ["/api/auth/logout"] if surface is check_ui_wiring.SURFACES["swiftui"] else ["/api/search"]
        ),
    )
    monkeypatch.setattr(
        check_ui_wiring,
        "load_allowlist",
        lambda surface, name: {
            "paths": {
                "/api/auth/logout" if name == "swiftui" else "/api/search": "baseline"
            }
        },
    )
    matrix = check_ui_wiring.coverage_matrix(openapi)
    assert matrix["rows"] == [
        {
            "domain": "auth",
            "total": 2,
            "swiftui_wired": 1,
            "swiftui_unwired": 1,
            "swiftui_allowlisted": 1,
            "swiftui_coverage": 0.5,
            "cli_wired": 2,
            "cli_untested": 0,
            "cli_allowlisted": 0,
            "cli_coverage": 1.0,
        },
        {
            "domain": "search",
            "total": 1,
            "swiftui_wired": 1,
            "swiftui_unwired": 0,
            "swiftui_allowlisted": 0,
            "swiftui_coverage": 1.0,
            "cli_wired": 0,
            "cli_untested": 1,
            "cli_allowlisted": 1,
            "cli_coverage": 0.0,
        },
    ]
