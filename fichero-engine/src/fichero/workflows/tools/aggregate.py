"""
Aggregate Tool

Explicit fan-in node that reshapes upstream fan-out results into a single
downstream payload. The builder already runs an implicit aggregation
between a Send-based fan-out and its downstream node; this tool lets
users make that collapse visible on the canvas and choose how the
records combine.

Four modes:
- "concat":            joins all text records with a separator string
- "list":              keeps records as a typed list (downstream sees all)
- "json_array":        emits records as a JSON array string
- "group_by_document": keys records by document id / name for downstream
                       tools that need per-doc access

Accepts upstream text/data/documents; emits `text` (canonical output
port used by downstream LLM tools), `records` (list payload), and
`count` (how many records were aggregated). Never raises.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fichero.llm import LLMConfig
from fichero.workflows.registry import register_tool
from fichero.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)


AGGREGATE_CONFIG = {
    "mode": {
        "type": "string",
        "enum": ["concat", "list", "json_array", "group_by_document"],
        "default": "concat",
        "description": (
            "How to combine upstream records. concat = text with separator; "
            "list = keep as array; json_array = JSON-encoded array; "
            "group_by_document = dict keyed by doc id/name."
        ),
    },
    "separator": {
        "type": "string",
        "default": "\n\n---\n\n",
        "description": "Separator used when mode=concat.",
    },
    "pretty_json": {
        "type": "boolean",
        "default": True,
        "description": "Indent JSON output (mode=json_array / group_by_document).",
    },
}


def _coerce_records(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten upstream into (doc_name, doc_id, text) records.

    Accepts the same shapes the implicit aggregator produces:
    - inputs["text"] can be a string OR list of strings
    - inputs["documents"] can be list of dicts (doc metadata) or missing
    """
    texts_raw = inputs.get("text")
    documents_raw = inputs.get("documents") or []
    if not isinstance(documents_raw, list):
        documents_raw = [documents_raw] if documents_raw else []

    if texts_raw is None:
        return []

    if isinstance(texts_raw, list):
        texts = [str(t) if t is not None else "" for t in texts_raw]
    else:
        texts = [str(texts_raw)]

    records: list[dict[str, Any]] = []
    for i, text in enumerate(texts):
        doc = documents_raw[i] if i < len(documents_raw) else {}
        if not isinstance(doc, dict):
            doc = {}
        records.append({
            "index": i,
            "text": text,
            "doc_id": str(doc.get("id") or ""),
            "doc_name": str(doc.get("name") or doc.get("path") or f"item-{i + 1}"),
        })
    return records


def _aggregate(
    records: list[dict[str, Any]],
    *,
    mode: str,
    separator: str,
    pretty: bool,
) -> dict[str, Any]:
    """Apply the chosen aggregation mode and return output-port shape."""
    count = len(records)
    indent = 2 if pretty else None

    if mode == "concat" or not records:
        text = separator.join(rec["text"] for rec in records)
        return {"text": text, "records": records, "count": count}

    if mode == "list":
        # Keep text as joined for the canonical `text` port so downstream
        # LLM tools still see a single string; records carries the
        # structured list for tools that want it.
        text = separator.join(rec["text"] for rec in records)
        return {"text": text, "records": records, "count": count}

    if mode == "json_array":
        payload = [
            {"index": r["index"], "doc_id": r["doc_id"], "doc_name": r["doc_name"], "text": r["text"]}
            for r in records
        ]
        text = json.dumps(payload, ensure_ascii=False, indent=indent)
        return {"text": text, "records": records, "count": count}

    if mode == "group_by_document":
        grouped: dict[str, str] = {}
        for rec in records:
            key = rec["doc_id"] or rec["doc_name"]
            if key in grouped:
                grouped[key] = grouped[key] + "\n" + rec["text"]
            else:
                grouped[key] = rec["text"]
        text = json.dumps(grouped, ensure_ascii=False, indent=indent)
        return {"text": text, "records": records, "count": count}

    # Unknown mode — fall through to concat so the workflow never dies on
    # a bad enum value. Log loudly so the user notices.
    logger.warning("aggregate: unknown mode %r, falling back to concat", mode)
    text = separator.join(rec["text"] for rec in records)
    return {"text": text, "records": records, "count": count}


@register_tool(
    name="aggregate",
    display_name="Aggregate",
    description="Combine upstream fan-out results into a single payload.",
    category="transform",
    icon="arrow.triangle.merge",
    color="teal",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Text records from upstream (string or list).",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description="Optional document metadata aligned with text records.",
        ),
    ],
    output_ports=[
        PortDef(
            id="text",
            name="Text",
            port_type="output",
            data_type=DataType.TEXT,
            description="Combined text payload.",
        ),
        PortDef(
            id="records",
            name="Records",
            port_type="output",
            data_type=DataType.ARRAY,
            description="Full structured record list.",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of records aggregated.",
        ),
    ],
    config_schema=AGGREGATE_CONFIG,
    sort_order=50,
)
async def aggregate(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Combine upstream records. See module docstring for semantics."""
    config = inputs.get("_config") or {}
    mode = config.get("mode") or "concat"
    separator = config.get("separator") or "\n\n---\n\n"
    pretty = bool(config.get("pretty_json", True))

    records = _coerce_records(inputs)
    if not records:
        logger.info("aggregate: no upstream records; returning empty payload")
        return {"text": "", "records": [], "count": 0}

    return _aggregate(records, mode=mode, separator=separator, pretty=pretty)
