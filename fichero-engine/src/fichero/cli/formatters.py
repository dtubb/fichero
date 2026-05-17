"""Rendering for CLI output — human-readable text, or raw JSON with ``--json``.

These formatters work structurally on dicts/lists: a list becomes one line per
item, a dict becomes ``key: value`` lines, and common response envelopes
(``{"documents": [...]}``) are unwrapped to their payload list.

When the client returns Pydantic models (``Document``, ``Workflow`` …), the
top of :func:`render` converts them to JSON-shaped dicts via
``model_dump(mode="json")`` so the existing dict-based rendering logic just
works. The conversion is recursive — a ``list[Document]`` becomes a list of
dicts, a dict with model values has its values dumped, etc.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

# Keys tried, in order, to identify and label an item within a list.
_ID_KEYS = (
    "id",
    "doc_id",
    "document_id",
    "thread_id",
    "workflow_id",
    "entity_id",
    "claim_id",
    "artifact_id",
    "batch_id",
    "node_id",
    "schedule_id",
    "run_id",
    "target_id",
)
_LABEL_KEYS = (
    "canonical_name",
    "text",
    "message",
    "workflow_name",
    "title",
    "name",
    "document_name",
    "filename",
    "label",
    "subject",
    "query",
)
_DETAIL_KEYS = (
    "doc_type",
    "file_type",
    "type",
    "status",
    "claim_type",
    "entity_type",
    "artifact_type",
    "action",
    "level",
    "note_type",
    "operation_type",
    "relation_type",
    "source_type",
)
# Envelope keys whose list value is the real payload.
_ENVELOPE_KEYS = (
    "documents",
    "artifacts",
    "entities",
    "claims",
    "workflows",
    "activities",
    "results",
    "items",
    "rows",
    "matches",
    "hits",
    "notes",
    "interpretations",
    "frameworks",
    "links",
    "snapshots",
    "providers",
    "models",
)


def render(data: Any, *, as_json: bool = False) -> str:
    """Render a backend response for display.

    Accepts plain dicts/lists OR Pydantic model instances (or nested
    combinations). Pydantic models are converted to JSON-shaped dicts at the
    boundary so the rest of the formatter stays purely structural.
    """
    data = _to_jsonable(data)
    if as_json:
        return json.dumps(data, indent=2, default=str, sort_keys=True)
    return _human(data).rstrip() or "(no data)"


def _to_jsonable(data: Any) -> Any:
    """Recursively unwrap Pydantic models into JSON-shaped dicts/lists."""
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if isinstance(data, list):
        return [_to_jsonable(item) for item in data]
    if isinstance(data, dict):
        return {key: _to_jsonable(value) for key, value in data.items()}
    return data


def _human(data: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if data is None:
        return f"{pad}(no data)"
    if isinstance(data, list):
        if not data:
            return f"{pad}(empty)"
        return "\n".join(_line(item, indent) for item in data)
    if isinstance(data, dict):
        for key in _ENVELOPE_KEYS:
            payload = data.get(key)
            if isinstance(payload, list):
                if not payload:
                    return f"{pad}{key}: (empty)"
                return f"{pad}{key} ({len(payload)}):\n{_human(payload, indent + 1)}"
        return "\n".join(_kv(k, v, indent) for k, v in data.items())
    return f"{pad}{data}"


def _line(item: Any, indent: int) -> str:
    pad = "  " * indent
    if not isinstance(item, dict):
        return f"{pad}- {item}"
    parts = [p for p in (_first(item, _ID_KEYS), _first(item, _LABEL_KEYS)) if p]
    text = "  ".join(parts) or "(item)"
    detail = _first(item, _DETAIL_KEYS)
    if detail:
        text += f"  [{detail}]"
    return f"{pad}- {text}"


def _kv(key: str, value: Any, indent: int) -> str:
    pad = "  " * indent
    if isinstance(value, (dict, list)):
        if not value:
            return f"{pad}{key}: (empty)"
        return f"{pad}{key}:\n{_human(value, indent + 1)}"
    return f"{pad}{key}: {value}"


def _first(item: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return None
