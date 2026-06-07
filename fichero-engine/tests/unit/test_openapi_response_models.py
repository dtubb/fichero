from fichero.api.main import app


def _response_schema(method: str, path: str) -> dict:
    spec = app.openapi()
    return spec["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]


def test_actions_routes_have_explicit_response_models() -> None:
    assert _response_schema("get", "/api/actions/categories")["$ref"].endswith("ActionCategoriesResponse")
    assert _response_schema("delete", "/api/actions/{action_id}")["$ref"].endswith("ActionSuccessResponse")
    assert _response_schema("post", "/api/actions/{action_id}/use")["$ref"].endswith("ActionSuccessResponse")
    assert _response_schema("get", "/api/actions/{action_id}/export")["$ref"].endswith("ActionJsonResponse")


def test_local_models_routes_have_explicit_response_models() -> None:
    assert _response_schema("get", "/api/local-models")["$ref"].endswith("LocalModelListResponse")
    assert _response_schema("get", "/api/local-models/disk-usage")["$ref"].endswith("DiskUsageResponse")
    assert _response_schema("post", "/api/local-models/download/{model_type}/{model_id}")["$ref"].endswith(
        "DownloadStartedResponse"
    )
    assert _response_schema("delete", "/api/local-models/{model_type}/{model_id}")["$ref"].endswith(
        "DeleteModelResponse"
    )
