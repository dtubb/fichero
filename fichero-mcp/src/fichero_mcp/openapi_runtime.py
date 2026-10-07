"""What every generated MCP tool calls: one ``FicheroClient.request``, and its error, typed (#5453).

``openapi_tools_generated.py`` holds one function per operation in the engine's OpenAPI contract.
Each makes exactly one :func:`call`; none holds logic of its own. This module is that call:

* reads use the default client, mutations (POST/PUT/PATCH/DELETE) the agent account's when one
  exists (``server._mutating_client``), so the audit log names the agent;
* a refused or failed call raises :class:`EngineError`, whose message is the engine's status and
  detail as JSON. FastMCP returns it as an error tool result, never an empty one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, NamedTuple

from fichero_cli import FicheroClient, FicheroError

ClientFactory = Callable[[], FicheroClient]

_CLIENTS: dict[str, ClientFactory | None] = {"read": None, "write": None}


class GeneratedTool(NamedTuple):
    """One generated tool: its MCP name, OpenAPI tag (its toolset), route and function."""

    name: str
    tag: str
    method: str
    path: str
    fn: Callable[..., Any]


class EngineError(Exception):
    """The engine refused or failed a call. ``str()`` is ``{"status", "detail", "route"}`` as JSON."""

    def __init__(self, status: int | None, detail: Any, route: str) -> None:
        self.status = status
        self.detail = detail
        self.route = route
        super().__init__(json.dumps({"status": status, "detail": detail, "route": route}, default=str))


def configure(read: ClientFactory, write: ClientFactory) -> None:
    """Set the client factories the generated tools call through (done once by ``server``)."""
    _CLIENTS["read"] = read
    _CLIENTS["write"] = write


def _detail(exc: FicheroError) -> Any:
    """The engine's ``detail`` from a FicheroError's ``"<METHOD> <path> -> <status>: <body>"``."""
    text = str(exc)
    marker = f"-> {exc.status_code}: "
    if exc.status_code is None or marker not in text:
        return text
    body = text.split(marker, 1)[1]
    try:
        parsed = json.loads(body)
    except ValueError:
        return body
    return parsed.get("detail", parsed) if isinstance(parsed, dict) else parsed


def call(method: str, path: str, *, params: dict | None = None, json: Any = None, files: Any = None) -> Any:
    """Make ONE engine request and return its parsed answer, or raise :class:`EngineError`."""
    factory = _CLIENTS["read" if method == "GET" else "write"]
    if factory is None:
        raise RuntimeError("fichero_mcp.openapi_runtime.configure() was never called")
    try:
        with factory() as client:
            return client.request(method, path, params=params, json=json, files=files)
    except FicheroError as exc:
        raise EngineError(exc.status_code, _detail(exc), f"{method} {path}") from exc


_IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF8", "gif"),
)


def image(method: str, path: str, *, params: dict | None = None) -> Any:
    """GET a picture and return it as MCP image content, so the agent sees it (#5568).

    The generator emits this for a GET whose answer is ``image/*`` (a folder's canvas, a segment,
    a thumbnail). An answer that is not a picture (some of these routes answer JSON instead) is
    returned parsed; a refusal raises :class:`EngineError` as :func:`call` does.
    """
    from mcp.server.fastmcp import Image

    factory = _CLIENTS["read"]
    if factory is None:
        raise RuntimeError("fichero_mcp.openapi_runtime.configure() was never called")
    try:
        with factory() as client:
            data = client.get_bytes(path, params=params)
    except FicheroError as exc:
        raise EngineError(exc.status_code, _detail(exc), f"{method} {path}") from exc
    for signature, kind in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return Image(data=data, format=kind)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return Image(data=data, format="webp")
    try:
        return json.loads(data)
    except ValueError:
        return {"content_type": "application/octet-stream", "bytes": len(data)}


def body(values: dict[str, Any]) -> dict[str, Any] | None:
    """A JSON body from a tool's arguments: the fields the caller set, or no body at all."""
    payload = {key: value for key, value in values.items() if value is not None}
    return payload or None


def multipart(fields: dict[str, str] | None, uploads: dict[str, str] | None) -> list[tuple[str, Any]] | None:
    """Multipart parts: text ``fields``, and ``uploads`` (form field to a file on the MCP host)."""
    parts: list[tuple[str, Any]] = [(key, (None, value)) for key, value in (fields or {}).items()]
    for key, value in (uploads or {}).items():
        file_path = Path(value).expanduser()
        parts.append((key, (file_path.name, file_path.read_bytes())))
    return parts or None
