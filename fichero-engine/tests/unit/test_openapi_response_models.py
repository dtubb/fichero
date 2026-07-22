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
    assert _response_schema("get", "/api/local-inference/capabilities")["$ref"].endswith(
        "LocalInferenceCapabilitiesResponse"
    )
    assert _response_schema("get", "/api/local-models")["$ref"].endswith("LocalModelListResponse")
    assert _response_schema("get", "/api/local-models/disk-usage")["$ref"].endswith("DiskUsageResponse")
    assert _response_schema("post", "/api/local-models/download/{model_type}/{model_id}")["$ref"].endswith(
        "DownloadStartedResponse"
    )
    assert _response_schema("delete", "/api/local-models/{model_type}/{model_id}")["$ref"].endswith(
        "DeleteModelResponse"
    )


def test_consistency_audit_batch_routes_have_explicit_response_models() -> None:
    assert _response_schema("get", "/api/health")["$ref"].endswith("HealthResponse")
    assert _response_schema("get", "/api/stats")["$ref"].endswith("LibraryStatsResponse")
    assert _response_schema("get", "/api/search/stats")["$ref"].endswith("EmbeddingStatsResponse")
    assert _response_schema("post", "/api/workflows/reinstall-defaults")["$ref"].endswith(
        "ReinstallDefaultWorkflowsResponse"
    )
    assert _response_schema("get", "/api/providers/apple/availability")["$ref"].endswith(
        "AppleIntelligenceProbeResponse"
    )
    assert _response_schema("get", "/api/providers/apple-intelligence/probe")["$ref"].endswith(
        "AppleIntelligenceProbeResponse"
    )
    assert _response_schema("get", "/api/providers/catalog/{provider_type}")["$ref"].endswith(
        "ProviderCatalogResponse"
    )
    assert _response_schema("get", "/api/providers/{provider_id}")["$ref"].endswith("ProviderResponse")
    assert _response_schema("patch", "/api/providers/{provider_id}")["$ref"].endswith("ProviderResponse")
    assert _response_schema("delete", "/api/providers/{provider_id}")["$ref"].endswith("DeletedResponse")


def _binary_media_types(method: str, path: str) -> dict:
    """The 200 response `content` block for a route (all declared media types)."""
    spec = app.openapi()
    return spec["paths"][path][method]["responses"]["200"]["content"]


def test_image_preview_route_declares_binary_response() -> None:
    """`/preview` streams PNG/JPEG bytes — the OpenAPI 200 must model them as
    binary so the generated Swift client can decode the body instead of forcing
    the callsite onto raw URLSession (#3028)."""
    content = _binary_media_types("get", "/api/images/{document_id}/preview")
    for media in ("image/png", "image/jpeg"):
        assert content[media]["schema"] == {"type": "string", "format": "binary"}, media


def test_thread_diagram_png_route_declares_binary_response() -> None:
    """`/threads/{thread_id}/diagram.png` returns real PNG bytes; its 200 must be
    declared binary rather than defaulting to application/json (#3028)."""
    content = _binary_media_types(
        "get", "/api/workflow-execution/threads/{thread_id}/diagram.png"
    )
    assert content["image/png"]["schema"] == {"type": "string", "format": "binary"}


def test_hermeneutics_list_routes_have_typed_item_envelopes() -> None:
    cases = {
        "/api/hermeneutics/frameworks": ("FrameworkListResponse", "InterpretiveFramework"),
        "/api/hermeneutics/interpretations": ("InterpretationListResponse", "Interpretation"),
        "/api/hermeneutics/patterns": ("PatternListResponse", "PatternInstance"),
        "/api/hermeneutics/circle-state": ("CircleStateListResponse", "HermeneuticCircleState"),
    }
    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    for path, (envelope, item) in cases.items():
        assert _response_schema("get", path)["$ref"].endswith(envelope)
        assert schemas[envelope]["properties"]["items"]["items"]["$ref"].endswith(item)
