#!/usr/bin/env python3
"""Generate CLI commands from the committed OpenAPI contract.

Emits a Typer registration module with one default command per OpenAPI
operation. The generated source embeds literal backend paths so
scripts/check_endpoint_coverage_matrix.py and scripts/check_openapi_client_parity.py
can count CLI coverage deterministically. The contract's parse, exclusion list and
naming helpers live in openapi_operations.py, shared with generate_openapi_mcp.py.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from openapi_operations import (  # noqa: E402,F401  (re-exported: tests read them off this module)
    HTTP_METHODS,
    INTENTIONALLY_UNWIRED_PATHS,
    OPENAPI,
    ROOT,
    Operation,
    QueryParam,
    RequestField,
    _build_operations,
    _camel_resource_tokens,
    _identifier,
    _is_event_stream,
    _slug,
    field_doc,
    scalar_list_items,
)

OUTPUT = ROOT / "fichero-cli" / "src" / "fichero_cli" / "openapi_surface_generated.py"

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
    """The route handler's name less the words its group already says, as the MCP tool is named
    (`start_evaluation` -> `evaluation start`, `save_project_setup` -> `recipes save-project-setup`).
    A summary is a sentence; cutting the group's words out of it left names like
    `tie-the-project-to-a-on-the-engine-s-disk` (#5501)."""
    resource_tokens = _camel_resource_tokens(op.resource)
    tokens = [t for t in _slug(op.function_name or op.operation_id).split("-") if t]
    rest = [t for t in tokens if t not in resource_tokens] or tokens
    return _unique_name("-".join(rest) or _default_name(op), op, seen)


def _summary_name(op: Operation, seen: set[str]) -> str:
    """The name the generator gave before #5501: the summary less the group's words. Kept as a
    hidden alias, so a command written down under it still runs."""
    resource_tokens = _camel_resource_tokens(op.resource)
    summary_tokens = [t for t in _slug(op.summary).split("-") if t]
    filtered = [t for t in summary_tokens if t not in resource_tokens]
    candidate = "-".join(filtered) if filtered else _default_name(op)
    return _unique_name(candidate or _default_name(op), op, seen)


def _unique_name(candidate: str, op: Operation, seen: set[str]) -> str:
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


def _annotation(schema_type: str, required: bool) -> str:
    base = {
        "integer": "int",
        "number": "float",
        "boolean": "bool",
    }.get(schema_type, "str")
    return base if required else f"Optional[{base}]"


#: What a list flag's help adds: the three ways to give it (#5501).
LIST_HELP = " A list: repeat the flag, or give the values comma-separated, or as JSON."


def _flag_option(flag_name: str, required: bool, is_bool: bool, help_text: str) -> str:
    flag = f"--{flag_name.replace('_', '-')}"
    default = "..." if required else "None"
    if is_bool:
        flag = f"{flag}/--no-{flag_name.replace('_', '-')}"
    return f"typer.Option({default}, {flag!r}, help={help_text!r})"


def _query_annotation(param: QueryParam) -> str:
    if param.schema_type == "array":
        return "list[str]" if param.required else "Optional[list[str]]"
    return _annotation(param.schema_type, param.required)


def _option_expr(var_name: str, param: QueryParam) -> str:
    help_text = " ".join(param.description.split()) or f"Query parameter: {param.name}"
    help_text = help_text if help_text.endswith((".", "?", "!", ")")) else help_text + "."
    if param.schema_type == "array":
        help_text += LIST_HELP
    return _flag_option(param.name, param.required, param.schema_type == "boolean", help_text)


def _request_field_annotation(field: RequestField) -> str:
    schema_type = field.schema.get("type")
    if schema_type in {"integer", "number", "boolean"}:
        return _annotation(schema_type, field.required)
    if scalar_list_items(field.schema):
        return "list[str]" if field.required else "Optional[list[str]]"
    return "str" if field.required else "Optional[str]"


def _request_field_help(field: RequestField) -> str:
    """The field's schema description, then how to give it: a list three ways, anything
    structured as JSON (#5501). It used to say only `Request field: <name>.`"""
    text = field_doc(field)
    schema = field.schema
    if scalar_list_items(schema):
        return text + LIST_HELP
    if schema.get("type") in {"array", "object"} or any(k in schema for k in ("$ref", "allOf", "anyOf", "oneOf")):
        return text + " JSON."
    return text


def _request_field_option_expr(field: RequestField) -> str:
    return _flag_option(
        field.name, field.required, field.schema.get("type") == "boolean", _request_field_help(field)
    )


def _emit_function(op: Operation, command_name: str, aliases: list[str] = ()) -> list[str]:
    used_identifiers = {"ctx", "body", "body_file", "field", "upload", "payload"}
    param_map: list[tuple[str, str]] = []
    lines = [f"    @target_app.command({json.dumps(alias)}, hidden=True)" for alias in aliases]
    lines += ["    @target_app.command(" + json.dumps(command_name) + ")", f"    def {_identifier(f'{op.resource}_{command_name}_{op.method.lower()}', set())}("]
    lines.append("        ctx: typer.Context,")
    path_docs = op.path_param_descriptions or ("",) * len(op.path_params)
    for path_param, path_doc in zip(op.path_params, path_docs):
        var_name = _identifier(path_param, used_identifiers)
        param_map.append((path_param, var_name))
        help_text = " ".join(path_doc.split()) or f"Path parameter: {path_param}."
        lines.append(f"        {var_name}: str = typer.Argument(..., help={help_text!r}),")
    for query_param in op.query_params:
        var_name = _identifier(query_param.name, used_identifiers)
        param_map.append((query_param.name, var_name))
        lines.append(
            f"        {var_name}: {_query_annotation(query_param)} = "
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
            if query_param.schema_type == "array":
                var_name = f"_list_values({var_name})"
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
    elif _is_event_stream(op):
        # Print each event as it arrives; a plain request waits for a stream that never ends (#5321).
        lines.append(
            f'            return client.request_stream("{op.method}", endpoint_path, params=params)'
        )
    else:
        lines.append(
            f'            return client.request("{op.method}", endpoint_path, params=params)'
        )
    lines.append("        invoke(ctx, op_call)")
    return lines


CLI_MAIN = ROOT / "fichero-cli" / "src" / "fichero_cli" / "__main__.py"


def _hand_written_commands() -> dict[str, set[str]]:
    """The command names `__main__.py` writes by hand into a group the generated commands join
    (its `existing_apps` map). A generated command never takes one of them: typer keeps the last
    registration, so a clash hides one of the two (#5501)."""
    source = CLI_MAIN.read_text(encoding="utf-8")
    block = re.search(r"existing_apps=\{(.*?)\}", source, re.S)
    app_to_resource = {
        var: resource for resource, var in re.findall(r'"([\w-]+)":\s*(\w+)', block.group(1) if block else "")
    }
    names: dict[str, set[str]] = {}
    for var, name in re.findall(r'@(\w+)\.command\(\s*"([^"]+)"', source):
        if var in app_to_resource:
            names.setdefault(app_to_resource[var], set()).add(name)
    return names


def _generate_module(operations: list[Operation]) -> str:
    per_resource: dict[str, list[tuple[str, Operation]]] = {}
    seen_per_resource: dict[str, set[str]] = {
        resource: set(names) for resource, names in _hand_written_commands().items()
    }
    old_seen: dict[str, set[str]] = {}
    old_names: dict[int, str] = {}
    for op in operations:
        command_name = _command_name(op, seen_per_resource.setdefault(op.resource, set()))
        per_resource.setdefault(op.resource, []).append((command_name, op))
        old_names[id(op)] = _summary_name(op, old_seen.setdefault(op.resource, set()))
    #: The pre-#5501 name, hidden, where it differs and names no other command of the group.
    aliases: dict[int, list[str]] = {
        id(op): [old_names[id(op)]]
        for resource, named in per_resource.items()
        for command_name, op in named
        if old_names[id(op)] not in seen_per_resource[resource]
    }

    lines = [
        '"""Auto-generated OpenAPI CLI commands.',
        "",
        "Generated by fichero-server/scripts/generate_openapi_cli.py.",
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
        "from fichero_cli import FicheroClient",
        "",
        "",
        "def _list_values(values: Optional[list[str]]) -> Optional[list[str]]:",
        '    """A list flag\'s values: repeated flags each whole; one value as JSON when it is a JSON',
        '    list, else split on commas (#5501)."""',
        "    if values is None:",
        "        return None",
        "    if len(values) == 1:",
        "        raw = values[0].strip()",
        '        if raw.startswith("["):',
        "            try:",
        "                parsed = json.loads(raw)",
        "            except json.JSONDecodeError as exc:",
        '                raise typer.BadParameter(f"Invalid JSON list: {exc}") from exc',
        "            if not isinstance(parsed, list):",
        '                raise typer.BadParameter("Expected a JSON list.")',
        "            return parsed",
        '        return [part.strip() for part in raw.split(",") if part.strip()]',
        "    return list(values)",
        "",
        "",
        "def _coerce_json_field(value: Any, schema: dict[str, Any]) -> Any:",
        '    """Coerce CLI option values into the request-body field shape."""',
        "    if value is None:",
        "        return None",
        '    schema_type = schema.get("type")',
        "    if isinstance(value, list):",
        "        items = _list_values(value) or []",
        '        item_type = (schema.get("items") or {}).get("type")',
        '        if item_type in {"integer", "number"}:',
        "            cast = int if item_type == \"integer\" else float",
        "            try:",
        "                return [item if isinstance(item, (int, float)) else cast(item) for item in items]",
        "            except ValueError as exc:",
        '                raise typer.BadParameter(f"Expected numbers: {exc}") from exc',
        "        return items",
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
            lines.extend(_emit_function(op, command_name, aliases.get(id(op), [])))

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
