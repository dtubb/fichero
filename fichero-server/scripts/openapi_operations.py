"""The operations of the committed OpenAPI contract, read once for every generated surface.

`generate_openapi_cli.py` (the CLI) and `generate_openapi_mcp.py` (the MCP tools) both start
here: the same parse, the same exclusion list and the same naming helpers, so the two surfaces
cannot disagree about which routes exist (#5453).
"""

from __future__ import annotations

import json
import keyword
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPENAPI = ROOT / "fichero-server" / "tests" / "contracts" / "openapi.json"

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
#: Routes no generated surface wires: streams a request cannot hold open, and debug/health probes.
INTENTIONALLY_UNWIRED_PATHS = {
    "/api/activity/stream",
    "/api/health",
    "/api/storage/debug/{doc_id}",
    "/api/tasks/health",
    "/api/workflow-execution/stream/{thread_id}",
}
#: The toolset of an operation the contract gives no tag.
UNTAGGED = "engine"


@dataclass(frozen=True)
class QueryParam:
    name: str
    required: bool
    schema_type: str
    description: str = ""


@dataclass(frozen=True)
class RequestField:
    name: str
    required: bool
    schema: dict


@dataclass(frozen=True)
class Operation:
    resource: str
    method: str
    path: str
    summary: str
    operation_id: str
    path_params: tuple[str, ...]
    query_params: tuple[QueryParam, ...]
    request_kind: str | None
    request_required: bool
    request_fields: tuple[RequestField, ...]
    tag: str = UNTAGGED
    description: str = ""
    function_name: str = ""
    path_param_descriptions: tuple[str, ...] = ()
    #: The route writes nothing though it is not a GET: `x-fichero-reads: true` in the contract (#5584).
    reads: bool = False


def _is_event_stream(op: Operation) -> bool:
    """A server-sent-event endpoint. The contract does not mark their content type, but every one
    is a GET on a ``…/stream`` path (``/api/changes/stream``, ``/api/workflow-execution/stream/{id}``)."""
    return op.method == "GET" and re.search(r"/stream(/|$)", op.path) is not None


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value or "op"


def _camel_resource_tokens(resource: str) -> set[str]:
    raw = re.split(r"[-_]+", resource.lower())
    out = set(raw)
    for token in raw:
        if token.endswith("s") and len(token) > 3:
            out.add(token[:-1])
        if token.endswith("ies") and len(token) > 4:
            out.add(token[:-3] + "y")
    return {t for t in out if t}


def field_doc(field: RequestField) -> str:
    """A body field's help in words: its schema description (else title, else name), its choices
    and its default. The CLI's ``--help`` and the MCP tool's parameter docs both say this (#5501)."""
    schema = field.schema
    text = " ".join(str(schema.get("description") or schema.get("title") or field.name).split())
    text = text if text.endswith((".", "?", "!", ")")) else text + "."
    if schema.get("enum"):
        text += " One of: " + ", ".join(str(v) for v in schema["enum"]) + "."
    if "default" in schema and schema["default"] is not None:
        text += f" Default: {json.dumps(schema['default'])}."
    return text


def scalar_list_items(schema: dict) -> str | None:
    """The item type of a list of plain values (``string``, ``integer``, ``number``), else None.
    Such a field takes a comma-separated or repeated flag on the CLI, not only JSON (#5501)."""
    if schema.get("type") != "array":
        return None
    kind = (schema.get("items") or {}).get("type")
    return kind if kind in {"string", "integer", "number"} else None


def _identifier(name: str, used: set[str]) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_") or "value"
    if value and value[0].isdigit():
        value = f"p_{value}"
    if keyword.iskeyword(value):
        value = f"{value}_value"
    base = value
    index = 2
    while value in used:
        value = f"{base}_{index}"
        index += 1
    used.add(value)
    return value


def _request_kind(details: dict) -> tuple[str | None, bool]:
    request_body = details.get("requestBody") or {}
    content = request_body.get("content") or {}
    if "application/json" in content:
        return "json", bool(request_body.get("required"))
    if "multipart/form-data" in content:
        return "multipart", bool(request_body.get("required"))
    return None, bool(request_body.get("required"))


def _resolve_schema(schema: dict, components: dict[str, dict]) -> dict:
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        return _resolve_schema(components.get(ref_name, {}), components)
    if "allOf" in schema:
        merged: dict = {"type": "object", "properties": {}, "required": []}
        for item in schema.get("allOf", []):
            resolved = _resolve_schema(item, components)
            merged["properties"].update(resolved.get("properties", {}))
            merged["required"].extend(resolved.get("required", []))
        return {**schema, **merged}
    return schema


def _request_fields(details: dict, components: dict[str, dict]) -> tuple[RequestField, ...]:
    request_body = details.get("requestBody") or {}
    content = request_body.get("content") or {}
    schema = content.get("application/json", {}).get("schema") or {}
    resolved = _resolve_schema(schema, components)
    if resolved.get("type") != "object":
        return ()
    required = set(resolved.get("required", []))
    return tuple(
        RequestField(
            name=name,
            required=name in required,
            schema=_resolve_schema(field_schema, components),
        )
        for name, field_schema in sorted((resolved.get("properties") or {}).items())
    )


def _function_name(path: str, method: str, operation_id: str) -> str:
    """The route handler's own name: FastAPI's operationId minus the path and method it appends."""
    suffix = re.sub(r"\W", "_", path) + "_" + method
    return operation_id[: -len(suffix)] if operation_id.endswith(suffix) else operation_id


def _param_description(param: dict) -> str:
    schema = param.get("schema") or {}
    return " ".join(str(param.get("description") or schema.get("description") or schema.get("title") or "").split())


def _build_operations(openapi: dict | None = None) -> list[Operation]:
    schema = json.loads(OPENAPI.read_text()) if openapi is None else openapi
    components = schema.get("components", {}).get("schemas", {})
    operations: list[Operation] = []
    for path, methods in sorted(schema.get("paths", {}).items()):
        if path in INTENTIONALLY_UNWIRED_PATHS:
            continue
        clean_path = path.replace("/api", "", 1) if path.startswith("/api") else path
        segments = [segment for segment in clean_path.strip("/").split("/") if segment]
        resource = segments[0] if segments else "root"
        for method, details in sorted(methods.items()):
            if method not in HTTP_METHODS:
                continue
            parameters = details.get("parameters") or []
            query_params = []
            for param in sorted(parameters, key=lambda item: item.get("name", "")):
                if param.get("in") == "query":
                    query_params.append(
                        QueryParam(
                            name=param["name"],
                            required=bool(param.get("required")),
                            schema_type=param.get("schema", {}).get("type", "string"),
                            description=_param_description(param),
                        )
                    )
            # Every `{name}` in the path, a whole segment or not (`{document_id}.bib`): each is a positional
            # argument of its command (`openapi.cli.path-ids-positional`, #5584).
            path_params = tuple(re.findall(r"{([^{}/]+)}", path))
            declared = {p.get("name"): p for p in parameters if p.get("in") == "path"}
            request_kind, request_required = _request_kind(details)
            operation_id = details.get("operationId") or _slug(f"{method}-{path}")
            operations.append(
                Operation(
                    resource=resource,
                    method=method.upper(),
                    path=path,
                    summary=details.get("summary") or details.get("operationId") or f"{method.upper()} {path}",
                    operation_id=operation_id,
                    path_params=path_params,
                    query_params=tuple(query_params),
                    request_kind=request_kind,
                    request_required=request_required,
                    request_fields=_request_fields(details, components),
                    tag=(details.get("tags") or [UNTAGGED])[0],
                    description=(details.get("description") or "").strip(),
                    function_name=_function_name(path, method, operation_id),
                    path_param_descriptions=tuple(
                        _param_description(declared.get(name, {})) for name in path_params
                    ),
                    reads=method.upper() == "GET" or bool(details.get("x-fichero-reads")),
                )
            )
    return operations
