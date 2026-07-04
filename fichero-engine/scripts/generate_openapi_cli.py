#!/usr/bin/env python3
"""Generate CLI commands from the committed OpenAPI contract.

Emits a Typer registration module with one default command per OpenAPI
operation. The generated source embeds literal backend paths so
scripts/check_ui_wiring.py can count CLI coverage deterministically.
"""

from __future__ import annotations

import json
import keyword
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPENAPI = ROOT / "fichero-engine" / "tests" / "contracts" / "openapi.json"
OUTPUT = ROOT / "fichero-engine" / "src" / "fichero" / "cli" / "openapi_surface_generated.py"

RESOURCE_NAME_OVERRIDES = {
    "activity": "activity-api",
    "claims": "claim",
    "documents": "docs",
    "health": "health-api",
    "libraries": "library",
    "mindpalace": "mind-palace",
    "search": "search-api",
}
RESOURCE_APP_KEY_OVERRIDES = {
    "libraries": "library",
    "mind-palace": "mind-palace",
    "mindpalace": "mind-palace",
}
RESOURCE_HELP_OVERRIDES = {
    "activity": "Generated OpenAPI commands for activity endpoints.",
    "health": "Generated OpenAPI commands for health endpoints.",
    "search": "Generated OpenAPI commands for search endpoints.",
}
EXISTING_APP_RESOURCES = {"artifacts", "kg", "library", "notes", "providers", "settings"}
HTTP_METHODS = ("get", "post", "put", "patch", "delete")
INTENTIONALLY_UNWIRED_PATHS = {
    "/api/activity/stream",
    "/api/health",
    "/api/storage/debug/{doc_id}",
    "/api/tasks/tasks/health",
    "/api/workflow-execution/stream/{thread_id}",
}


@dataclass(frozen=True)
class QueryParam:
    name: str
    required: bool
    schema_type: str


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
    request_fields: tuple["RequestField", ...]


@dataclass(frozen=True)
class RequestField:
    name: str
    required: bool
    schema: dict


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


def _default_name(op: Operation) -> str:
    static_parts = [
        _slug(part)
        for part in op.path.strip("/").split("/")
        if part and not part.startswith("{")
    ]
    tail = static_parts[1:] if len(static_parts) > 1 else []
    if not tail:
        return {
            "GET": "list",
            "POST": "create",
            "PUT": "update",
            "PATCH": "patch",
            "DELETE": "delete",
        }[op.method]
    joined = "-".join(tail)
    if re.fullmatch(r"[a-z0-9-]+", joined):
        if op.path.endswith("}") and len(op.path_params) == 1 and len(tail) == 1:
            return {
                "GET": "get",
                "POST": "post",
                "PUT": "update",
                "PATCH": "patch",
                "DELETE": "delete",
            }[op.method]
        return joined
    return _slug(f"{op.method.lower()}-{op.operation_id}")


def _command_name(op: Operation, seen: set[str]) -> str:
    resource_tokens = _camel_resource_tokens(op.resource)
    summary_tokens = [t for t in _slug(op.summary).split("-") if t]
    filtered = [t for t in summary_tokens if t not in resource_tokens]
    candidate = "-".join(filtered) if filtered else _default_name(op)
    candidate = candidate or _default_name(op)
    if candidate not in seen:
        seen.add(candidate)
        return candidate

    suffixes = []
    static_parts = [
        _slug(part)
        for part in op.path.strip("/").split("/")
        if part and not part.startswith("{")
    ]
    if len(static_parts) > 1:
        suffixes.append("-".join(static_parts[1:]))
    suffixes.append(op.method.lower())
    suffixes.append(_slug(op.operation_id))
    for suffix in suffixes:
        merged = f"{candidate}-{suffix}" if suffix and suffix != candidate else candidate
        merged = re.sub(r"-{2,}", "-", merged).strip("-")
        if merged and merged not in seen:
            seen.add(merged)
            return merged

    i = 2
    while True:
        merged = f"{candidate}-{i}"
        if merged not in seen:
            seen.add(merged)
            return merged
        i += 1


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


def _annotation(schema_type: str, required: bool) -> str:
    base = {
        "integer": "int",
        "number": "float",
        "boolean": "bool",
    }.get(schema_type, "str")
    return base if required else f"Optional[{base}]"


def _option_expr(var_name: str, param: QueryParam) -> str:
    flag = f"--{param.name.replace('_', '-')}"
    help_text = f"Query parameter: {param.name}."
    if param.schema_type == "boolean":
        if param.required:
            return f'typer.Option(..., "{flag}/--no-{param.name.replace("_", "-")}", help="{help_text}")'
        return f'typer.Option(None, "{flag}/--no-{param.name.replace("_", "-")}", help="{help_text}")'
    default = "..." if param.required else "None"
    return f'typer.Option({default}, "{flag}", help="{help_text}")'


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


def _build_operations() -> list[Operation]:
    schema = json.loads(OPENAPI.read_text())
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
            query_params = []
            for param in sorted(details.get("parameters", []), key=lambda item: item.get("name", "")):
                if param.get("in") == "query":
                    query_params.append(
                        QueryParam(
                            name=param["name"],
                            required=bool(param.get("required")),
                            schema_type=param.get("schema", {}).get("type", "string"),
                        )
                    )
            path_params = tuple(
                part[1:-1]
                for part in path.split("/")
                if part.startswith("{") and part.endswith("}")
            )
            request_kind, request_required = _request_kind(details)
            operations.append(
                Operation(
                    resource=resource,
                    method=method.upper(),
                    path=path,
                    summary=details.get("summary") or details.get("operationId") or f"{method.upper()} {path}",
                    operation_id=details.get("operationId") or _slug(f"{method}-{path}"),
                    path_params=path_params,
                    query_params=tuple(query_params),
                    request_kind=request_kind,
                    request_required=request_required,
                    request_fields=_request_fields(details, components),
                )
            )
    return operations


def _request_field_annotation(field: RequestField) -> str:
    schema_type = field.schema.get("type")
    if schema_type in {"integer", "number", "boolean"}:
        return _annotation(schema_type, field.required)
    return "str" if field.required else "Optional[str]"


def _request_field_option_expr(field: RequestField) -> str:
    flag = f"--{field.name.replace('_', '-')}"
    help_text = f"Request field: {field.name}."
    schema_type = field.schema.get("type")
    if schema_type == "boolean":
        if field.required:
            return f'typer.Option(..., "{flag}/--no-{field.name.replace("_", "-")}", help="{help_text}")'
        return f'typer.Option(None, "{flag}/--no-{field.name.replace("_", "-")}", help="{help_text}")'
    default = "..." if field.required else "None"
    return f'typer.Option({default}, "{flag}", help="{help_text}")'


def _emit_function(op: Operation, command_name: str) -> list[str]:
    used_identifiers = {"ctx", "body", "body_file", "field", "upload", "payload"}
    param_map: list[tuple[str, str]] = []
    lines = ["    @target_app.command(" + json.dumps(command_name) + ")", f"    def {_identifier(f'{op.resource}_{command_name}_{op.method.lower()}', set())}("]
    lines.append("        ctx: typer.Context,")
    for path_param in op.path_params:
        var_name = _identifier(path_param, used_identifiers)
        param_map.append((path_param, var_name))
        lines.append(
            f'        {var_name}: str = typer.Argument(..., help="Path parameter: {path_param}."),'
        )
    for query_param in op.query_params:
        var_name = _identifier(query_param.name, used_identifiers)
        param_map.append((query_param.name, var_name))
        lines.append(
            f"        {var_name}: {_annotation(query_param.schema_type, query_param.required)} = "
            + _option_expr(var_name, query_param)
            + ","
        )
    if op.method == "DELETE":
        lines.append(
            '        yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),'
        )
    if op.request_kind == "json":
        if op.request_fields:
            for request_field in op.request_fields:
                var_name = _identifier(request_field.name, used_identifiers)
                param_map.append((request_field.name, var_name))
                lines.append(
                    f"        {var_name}: {_request_field_annotation(request_field)} = "
                    + _request_field_option_expr(request_field)
                    + ","
                )
        else:
            lines.append(
                '        body: Optional[str] = typer.Option(None, "--body", help="Inline JSON request body."),'
            )
            lines.append(
                '        body_file: Optional[Path] = typer.Option('
                'None, "--body-file", exists=True, dir_okay=False, readable=True, help="Path to a JSON request body file."),'
            )
    elif op.request_kind == "multipart":
        lines.append(
            '        field: Optional[list[str]] = typer.Option('
            'None, "--field", help="Repeatable multipart field as key=value."),'
        )
        lines.append(
            '        upload: Optional[list[str]] = typer.Option('
            'None, "--upload", help="Repeatable multipart upload as field=/path/to/file."),'
        )
    lines.append("    ) -> None:")
    lines.append(f'        """{op.summary} ({op.method} {op.path})."""')
    path_expr = json.dumps(op.path)
    for source_name, var_name in param_map[: len(op.path_params)]:
        path_expr = path_expr.replace("{" + source_name + "}", "{" + var_name + "}")
    if op.method == "DELETE":
        lines.append("        if not yes:")
        lines.append(
            f'            typer.confirm("Delete {op.resource.replace("_", " ")}?", abort=True)'
        )
    lines.append("        def op_call(client: FicheroClient) -> Any:")
    if op.path_params:
        lines.append(f"            endpoint_path = f{path_expr}")
    else:
        lines.append(f"            endpoint_path = {json.dumps(op.path)}")
    if op.query_params:
        query_lines = []
        for query_param in op.query_params:
            var_name = next(v for source, v in param_map if source == query_param.name)
            query_lines.append(f'                "{query_param.name}": {var_name},')
        lines.append("            params = {")
        lines.extend(query_lines)
        lines.append("            }")
    else:
        lines.append("            params = None")
    if op.request_kind == "json":
        if op.request_fields:
            lines.append("            payload = _build_json_payload({")
            for request_field in op.request_fields:
                var_name = next(v for source, v in param_map if source == request_field.name)
                lines.append(f'                "{request_field.name}": {var_name},')
            lines.append("            }, {")
            for request_field in op.request_fields:
                schema_literal = dict(request_field.schema)
                schema_literal["x-cli-required"] = request_field.required
                lines.append(f'                "{request_field.name}": {schema_literal!r},')
            lines.append(f"            }}, required={str(op.request_required)})")
        else:
            lines.append(
                f"            payload = _load_json_payload(body, body_file, required={str(op.request_required)})"
            )
        lines.append(
            f'            return client.request("{op.method}", endpoint_path, params=params, json=payload)'
        )
    elif op.request_kind == "multipart":
        lines.append("            files = _build_multipart_payload(field, upload)")
        if op.request_required:
            lines.append("            if files is None:")
            lines.append(
                '                raise typer.BadParameter("Provide at least one --field or --upload value.")'
            )
        lines.append(
            f'            return client.request("{op.method}", endpoint_path, params=params, files=files)'
        )
    else:
        lines.append(
            f'            return client.request("{op.method}", endpoint_path, params=params)'
        )
    lines.append("        invoke(ctx, op_call)")
    return lines


def _generate_module(operations: list[Operation]) -> str:
    per_resource: dict[str, list[tuple[str, Operation]]] = {}
    seen_per_resource: dict[str, set[str]] = {}
    for op in operations:
        command_name = _command_name(op, seen_per_resource.setdefault(op.resource, set()))
        per_resource.setdefault(op.resource, []).append((command_name, op))

    lines = [
        '"""Auto-generated OpenAPI CLI commands.',
        "",
        "Generated by fichero-engine/scripts/generate_openapi_cli.py.",
        'Do not edit manually."""',
        "",
        "# ruff: noqa: E501, PLR0913",
        "from __future__ import annotations",
        "",
        "import json",
        "from pathlib import Path",
        "from typing import Any, Callable, Optional",
        "",
        "import typer",
        "",
        "from fichero.cli import FicheroClient",
        "",
        "",
        "def _coerce_json_field(value: Any, schema: dict[str, Any]) -> Any:",
        '    """Coerce CLI option values into the request-body field shape."""',
        "    if value is None:",
        "        return None",
        '    schema_type = schema.get("type")',
        '    if schema_type in {"array", "object"} or "$ref" in schema or "allOf" in schema or "anyOf" in schema or "oneOf" in schema:',
        "        if not isinstance(value, str):",
        "            return value",
        "        try:",
        "            return json.loads(value)",
        "        except json.JSONDecodeError as exc:",
        '            raise typer.BadParameter(f\"Invalid JSON value: {exc}\") from exc',
        "    return value",
        "",
        "",
        "def _build_json_payload(",
        "    values: dict[str, Any],",
        "    field_schemas: dict[str, dict[str, Any]],",
        "    *,",
        "    required: bool,",
        ") -> Any:",
        '    """Build a JSON object payload from generated request-field flags."""',
        "    payload: dict[str, Any] = {}",
        "    missing: list[str] = []",
        "    for name, value in values.items():",
        "        if value is None:",
        "            if field_schemas.get(name, {}).get(\"x-cli-required\"):",
        "                missing.append(name)",
        "            continue",
        "        payload[name] = _coerce_json_field(value, field_schemas.get(name, {}))",
        "    if missing:",
        '        raise typer.BadParameter(\"Missing required fields: \" + \", \".join(sorted(missing)))',
        "    if payload:",
        "        return payload",
        "    if required:",
        '        raise typer.BadParameter(\"This endpoint requires request fields.\")',
        "    return None",
        "",
        "",
        "def _load_json_payload(",
        "    body: Optional[str],",
        "    body_file: Optional[Path],",
        "    *,",
        "    required: bool,",
        ") -> Any:",
        '    """Return a JSON payload from inline text or a file."""',
        "    if body and body_file:",
        '        raise typer.BadParameter("Pass either --body or --body-file, not both.")',
        "    raw: str | None = None",
        "    if body_file is not None:",
        "        raw = body_file.read_text(encoding=\"utf-8\")",
        "    elif body is not None:",
        "        raw = body",
        "    if raw is None:",
        "        if required:",
        '            raise typer.BadParameter("This endpoint requires --body or --body-file.")',
        "        return None",
        "    try:",
        "        return json.loads(raw)",
        "    except json.JSONDecodeError as exc:",
        '        raise typer.BadParameter(f\"Invalid JSON payload: {exc}\") from exc',
        "",
        "",
        "def _build_multipart_payload(",
        "    field: Optional[list[str]],",
        "    upload: Optional[list[str]],",
        ") -> list[tuple[str, object]] | None:",
        '    """Build httpx-compatible multipart tuples from repeatable CLI flags."""',
        "    parts: list[tuple[str, object]] = []",
        "    for item in field or []:",
        "        if \"=\" not in item:",
        '            raise typer.BadParameter(\"--field values must be key=value.\")',
        "        key, value = item.split(\"=\", 1)",
        "        parts.append((key, (None, value)))",
        "    for item in upload or []:",
        "        if \"=\" not in item:",
        '            raise typer.BadParameter(\"--upload values must be field=/path/to/file.\")',
        "        key, value = item.split(\"=\", 1)",
        "        file_path = Path(value).expanduser()",
        "        if not file_path.exists() or not file_path.is_file():",
        '            raise typer.BadParameter(f\"Upload file not found: {file_path}\")',
        "        parts.append((key, (file_path.name, file_path.read_bytes())))",
        "    return parts or None",
        "",
        "",
        "def register_generated_openapi_commands(",
        "    root_app: typer.Typer,",
        "    invoke: Callable[[typer.Context, Callable[[FicheroClient], Any]], None],",
        "    existing_apps: dict[str, typer.Typer] | None = None,",
        ") -> None:",
        '    """Register generated commands onto the root CLI app."""',
        "    existing_apps = existing_apps or {}",
    ]

    for resource in sorted(per_resource):
        app_key = RESOURCE_APP_KEY_OVERRIDES.get(resource, resource)
        root_name = RESOURCE_NAME_OVERRIDES.get(resource, resource)
        help_text = RESOURCE_HELP_OVERRIDES.get(
            resource, f"Generated OpenAPI commands for {resource} endpoints."
        )
        lines.extend(
            [
                "",
                f"    target_app = existing_apps.get({app_key!r})",
                "    if target_app is None:",
                f"        target_app = typer.Typer(help={help_text!r}, no_args_is_help=True)",
                f"        root_app.add_typer(target_app, name={root_name!r})",
                f"        existing_apps[{app_key!r}] = target_app",
            ]
        )
        for command_name, op in per_resource[resource]:
            lines.append("")
            lines.extend(_emit_function(op, command_name))

    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    operations = _build_operations()
    module_text = _generate_module(operations)
    OUTPUT.write_text(module_text, encoding="utf-8")
    print(f"✓ Generated CLI surface for {len(operations)} OpenAPI operations -> {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
