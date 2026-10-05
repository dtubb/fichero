#!/usr/bin/env python3
"""Generate the MCP tools from the committed OpenAPI contract (#5453).

Writes ``fichero-mcp/src/fichero_mcp/openapi_tools_generated.py``: one tool per operation
outside the shared exclusion list (and the event streams, which a tool call cannot hold open).
A tool is named ``fichero_<tag>_<handler>``: its OpenAPI tag, which is also its toolset, then the
route handler's name less the words the tag already says. Its description and parameter docs
come from the route's summary, description and schema. Each tool makes ONE
``openapi_runtime.call`` (one ``FicheroClient.request``) and holds no logic.

The parse, the exclusion list and the naming helpers are the CLI generator's, from
``openapi_operations.py``. ``scripts/check_mcp_generated_current.py`` fails when the committed
module differs from what this writes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from openapi_operations import (  # noqa: E402
    ROOT,
    Operation,
    RequestField,
    _build_operations,
    _camel_resource_tokens,
    _identifier,
    _is_event_stream,
)

OUTPUT = ROOT / "fichero-mcp" / "src" / "fichero_mcp" / "openapi_tools_generated.py"

_PY_TYPES = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list[Any]",
    "object": "dict[str, Any]",
}
#: Names a generated function body uses itself, so a parameter may not take them.
_RESERVED = {"Annotated", "Any", "Field", "Optional", "GeneratedTool"}


def operations() -> list[Operation]:
    """The operations that get a tool: the shared list, less the event streams."""
    return [op for op in _build_operations() if not _is_event_stream(op)]


def tool_name(op: Operation, seen: set[str]) -> str:
    """``fichero_<tag>_<handler less the tag's words>``, unique within ``seen``."""
    tag = re.sub(r"[^a-z0-9]+", "_", op.tag.lower()).strip("_")
    tokens = [t for t in re.split(r"_+", op.function_name.lower()) if t]
    tag_tokens = _camel_resource_tokens(op.tag)
    rest = [t for t in tokens if t not in tag_tokens] or tokens
    base = f"fichero_{tag}_{'_'.join(rest)}"
    candidate, index = base, 2
    if candidate in seen:
        candidate = f"{base}_{op.method.lower()}"
    while candidate in seen:
        candidate, index = f"{base}_{index}", index + 1
    seen.add(candidate)
    return candidate


def _py_type(schema: dict) -> str:
    kind = schema.get("type")
    if not kind:
        for option in schema.get("anyOf") or schema.get("oneOf") or []:
            if option.get("type") and option.get("type") != "null":
                kind = option["type"]
                break
    return _PY_TYPES.get(kind, "Any")


def _field_doc(field: RequestField) -> str:
    schema = field.schema
    text = " ".join(str(schema.get("description") or schema.get("title") or field.name).split())
    text = text if text.endswith((".", "?", "!", ")")) else text + "."
    if schema.get("enum"):
        text += " One of: " + ", ".join(str(v) for v in schema["enum"]) + "."
    if "default" in schema and schema["default"] is not None:
        text += f" Default: {json.dumps(schema['default'])}."
    return text


def _param(var: str, annotation: str, doc: str, required: bool) -> str:
    if required:
        return f"    {var}: Annotated[{annotation}, Field(description={doc!r})],"
    return f"    {var}: Annotated[Optional[{annotation}], Field(description={doc!r})] = None,"


def _docstring(op: Operation) -> str:
    parts = [op.summary.strip()]
    if op.description:
        parts.append(op.description)
    acts = "reads" if op.method == "GET" else "changes data, as the agent account when one exists"
    parts.append(f"Route: {op.method} {op.path} (toolset `{op.tag}`; {acts}).")
    return "\n\n".join(parts)


def _emit_tool(op: Operation, name: str) -> list[str]:
    used = set(_RESERVED)
    params: list[str] = []
    path_vars: dict[str, str] = {}
    for path_param, doc in zip(op.path_params, op.path_param_descriptions or ("",) * len(op.path_params)):
        var = _identifier(path_param, used)
        path_vars[path_param] = var
        params.append(_param(var, "str", doc or f"Path parameter {path_param}.", True))
    query: list[tuple[str, str]] = []
    for qp in op.query_params:
        var = _identifier(qp.name, used)
        query.append((qp.name, var))
        annotation = "list[str]" if qp.schema_type == "array" else _PY_TYPES.get(qp.schema_type, "str")
        params.append(_param(var, annotation, qp.description or f"Query parameter {qp.name}.", qp.required))
    body_fields: list[tuple[str, str]] = []
    body_var = None
    if op.request_kind == "json" and op.request_fields:
        for field in op.request_fields:
            var = _identifier(field.name, used)
            body_fields.append((field.name, var))
            params.append(_param(var, _py_type(field.schema), _field_doc(field), field.required))
    elif op.request_kind == "json":
        body_var = _identifier("body", used)
        params.append(_param(body_var, "Any", "The JSON request body.", op.request_required))
    elif op.request_kind == "multipart":
        fields_var = _identifier("fields", used)
        uploads_var = _identifier("uploads", used)
        params.append(_param(fields_var, "dict[str, str]", "Multipart text fields, name to value.", False))
        params.append(_param(
            uploads_var, "dict[str, str]",
            "Multipart files: form field name to a file path on the machine this MCP server runs on.", False,
        ))

    lines = [f"def {name}("]
    if params:
        lines.append("    *,")
        lines.extend(params)
    lines.append(") -> Any:")
    lines.append(f"    {_docstring(op)!r}")
    path_expr = op.path
    for source, var in path_vars.items():
        path_expr = path_expr.replace("{" + source + "}", "{" + var + "}")
    path_literal = ("f" if path_vars else "") + json.dumps(path_expr)
    args = [json.dumps(op.method), path_literal]
    if query:
        args.append("params={" + ", ".join(f"{json.dumps(k)}: {v}" for k, v in query) + "}")
    if body_fields:
        args.append("json=_rt.body({" + ", ".join(f"{json.dumps(k)}: {v}" for k, v in body_fields) + "})")
    elif body_var:
        args.append(f"json={body_var}")
    elif op.request_kind == "multipart":
        args.append(f"files=_rt.multipart({fields_var}, {uploads_var})")
    lines.append(f"    return _rt.call({', '.join(args)})")
    return lines


def render() -> str:
    """The generated module's full text."""
    seen: set[str] = set()
    named = [(tool_name(op, seen), op) for op in operations()]
    lines = [
        '"""Auto-generated MCP tools: one per operation in the engine\'s OpenAPI contract (#5453).',
        "",
        "Generated by fichero-server/scripts/generate_openapi_mcp.py from",
        "fichero-server/tests/contracts/openapi.json. Do not edit manually:",
        'scripts/check_mcp_generated_current.py fails when this differs from a regeneration."""',
        "",
        "# ruff: noqa: E501",
        "from typing import Annotated, Any, Optional",
        "",
        "from pydantic import Field",
        "",
        "from fichero_mcp import openapi_runtime as _rt",
        "from fichero_mcp.openapi_runtime import GeneratedTool",
    ]
    for name, op in named:
        lines.extend(["", ""])
        lines.extend(_emit_tool(op, name))
    lines.extend(["", "", "TOOLS: tuple[GeneratedTool, ...] = ("])
    for name, op in named:
        lines.append(
            f"    GeneratedTool({json.dumps(name)}, {json.dumps(op.tag)}, {json.dumps(op.method)}, "
            f"{json.dumps(op.path)}, {name}),"
        )
    lines.append(")")
    lines.append("TAGS: tuple[str, ...] = (" + "".join(f"{json.dumps(t)}, " for t in sorted({op.tag for _, op in named})).rstrip() + ")")
    return "\n".join(lines) + "\n"


def main() -> int:
    text = render()
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"✓ Generated {text.count('    GeneratedTool(')} MCP tools from the OpenAPI contract -> {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
