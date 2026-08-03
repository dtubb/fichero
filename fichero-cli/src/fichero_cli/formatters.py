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

    Specialized renderers for entities, claims, documents, and artifacts are
    dispatched based on dict key signatures before falling back to generic.
    """
    # Handle type-specific renderers BEFORE converting to jsonable
    # This preserves the original type information for dispatch
    if isinstance(data, (dict, BaseModel)):
        data_dict = data if isinstance(data, dict) else data.model_dump(mode="json")
        if "canonical_name" in data_dict:
            return render_entity(data_dict, as_json=as_json)
        if "subject_canonical" in data_dict:
            return render_claim(data_dict, as_json=as_json)
        if "filename" in data_dict:
            return render_document(data_dict, as_json=as_json)
        if "artifact_type" in data_dict:
            return render_artifact(data_dict, as_json=as_json)

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
    # #3804: the engine refuses to run an internal component standalone, so a
    # plain list of names is a control that lies — every entry looks runnable.
    # The flag is read from the response, never re-derived here.
    if item.get("direct_runnable") is False:
        text += "  (component — run the parent workflow)"
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


def _truncate(text: str, width: int) -> str:
    """Truncate text to width, appending '...' if truncated."""
    if len(text) > width:
        return text[:width] + "..."
    return text


def _align_columns(items: list[tuple[str, ...]], widths: list[int]) -> str:
    """Pad each field in items to specified widths and join with ' | ' separator.

    Args:
        items: List of tuples, each tuple is a row of fields
        widths: List of column widths to pad to

    Returns:
        Multi-line string with aligned columns
    """
    lines = []
    for item in items:
        padded = [str(field).ljust(width) for field, width in zip(item, widths)]
        lines.append(" | ".join(padded))
    return "\n".join(lines)


def render_entity(entity: dict | Any, *, as_json: bool = False) -> str:
    """Render a KnowledgeEntity for display.

    Args:
        entity: Entity dict or BaseModel with canonical_name, entity_type, description
        as_json: If True, return raw JSON instead of human-readable format

    Returns:
        Formatted string
    """
    if as_json:
        if isinstance(entity, BaseModel):
            data = entity.model_dump(mode="json")
        else:
            data = entity
        return json.dumps(data, indent=2, default=str, sort_keys=True)

    # Convert BaseModel to dict if needed
    if isinstance(entity, BaseModel):
        entity = entity.model_dump(mode="json")

    canonical_name = entity.get("canonical_name", "(missing)")
    entity_type = entity.get("entity_type", "(missing)")
    description = entity.get("description", "")

    # Truncate description to 50 chars
    description = _truncate(str(description), 50)

    # Align 3 columns: 30, 15, 50
    items = [(canonical_name, entity_type, description)]
    return _align_columns(items, [30, 15, 50])


def render_claim(claim: dict | Any, *, as_json: bool = False) -> str:
    """Render a KnowledgeClaim for display.

    Args:
        claim: Claim dict or BaseModel with subject_canonical, predicate_verb, object_phrase,
               source_document_id
        as_json: If True, return raw JSON instead of human-readable format

    Returns:
        Formatted string
    """
    if as_json:
        if isinstance(claim, BaseModel):
            data = claim.model_dump(mode="json")
        else:
            data = claim
        return json.dumps(data, indent=2, default=str, sort_keys=True)

    # Convert BaseModel to dict if needed
    if isinstance(claim, BaseModel):
        claim = claim.model_dump(mode="json")

    subject = _truncate(str(claim.get("subject_canonical", "(missing)")), 25)
    predicate = _truncate(str(claim.get("predicate_verb", "(missing)")), 25)
    obj = _truncate(str(claim.get("object_phrase", "(missing)")), 25)
    doc_id = claim.get("source_document_id", "(missing)")

    from fichero_server.knowledge._common import render_statement

    triple = render_statement(subject, predicate, obj, separator=" → ")
    return f"{triple} (from: {doc_id})"


def render_document(doc: dict | Any, *, as_json: bool = False) -> str:
    """Render a Document for display.

    Args:
        doc: Document dict or BaseModel with filename, doc_type, description
        as_json: If True, return raw JSON instead of human-readable format

    Returns:
        Formatted string
    """
    if as_json:
        if isinstance(doc, BaseModel):
            data = doc.model_dump(mode="json")
        else:
            data = doc
        return json.dumps(data, indent=2, default=str, sort_keys=True)

    # Convert BaseModel to dict if needed
    if isinstance(doc, BaseModel):
        doc = doc.model_dump(mode="json")

    filename = doc.get("filename") or doc.get("name", "(missing)")
    doc_type = doc.get("doc_type", "(missing)")
    description = doc.get("description", "")

    # Truncate description to 50 chars
    description = _truncate(str(description), 50)

    return f"{filename} [{doc_type}] - {description}"


def render_artifact(artifact: dict | Any, *, as_json: bool = False) -> str:
    """Render an Artifact for display.

    Args:
        artifact: Artifact dict or BaseModel with artifact_type, title, document_id
        as_json: If True, return raw JSON instead of human-readable format

    Returns:
        Formatted string
    """
    if as_json:
        if isinstance(artifact, BaseModel):
            data = artifact.model_dump(mode="json")
        else:
            data = artifact
        return json.dumps(data, indent=2, default=str, sort_keys=True)

    # Convert BaseModel to dict if needed
    if isinstance(artifact, BaseModel):
        artifact = artifact.model_dump(mode="json")

    artifact_type = artifact.get("artifact_type", "(missing)")
    title = _truncate(str(artifact.get("title", "")), 40)
    document_id = artifact.get("document_id", "(missing)")

    return f"{artifact_type}: {title} (from doc: {document_id})"


def render_top_entity(entity: dict | Any, *, as_json: bool = False) -> str:
    """Render a TopEntityRow for display in the entity top table view.

    Args:
        entity: Entity dict or BaseModel with name, kind, claim_count
        as_json: If True, return raw JSON instead of human-readable format

    Returns:
        Formatted string with name | kind | claim_count columns
    """
    if as_json:
        if isinstance(entity, BaseModel):
            data = entity.model_dump(mode="json")
        else:
            data = entity
        return json.dumps(data, indent=2, default=str, sort_keys=True)

    # Convert BaseModel to dict if needed
    if isinstance(entity, BaseModel):
        entity = entity.model_dump(mode="json")

    name = _truncate(str(entity.get("name", "(missing)")), 30)
    kind = _truncate(str(entity.get("kind", "(missing)")), 15)
    claim_count = str(entity.get("claim_count", 0))

    # Align 3 columns: 30, 15, 10
    items = [(name, kind, claim_count)]
    return _align_columns(items, [30, 15, 10])
