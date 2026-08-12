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

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

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

    Text-files passthrough: when no `text` is supplied but `documents`
    carry `page_content`, fall back to reading page_content from each
    document. This lets `files-source → aggregate → extract_all` work
    on a folder of .md / .txt files (no transcribe step needed) — the
    'NER per-page' workflow.
    """
    texts_raw = inputs.get("text")
    documents_raw = inputs.get("documents") or []
    if not isinstance(documents_raw, list):
        documents_raw = [documents_raw] if documents_raw else []

    if texts_raw is None:
        # Fallback: read page_content directly off each upstream document.
        if documents_raw:
            records: list[dict[str, Any]] = []
            for i, doc in enumerate(documents_raw):
                if not isinstance(doc, dict):
                    continue
                content = doc.get("page_content") or doc.get("pageContent") or ""
                if not content:
                    continue
                records.append({
                    "index": i,
                    "text": str(content),
                    "doc_id": str(doc.get("id") or ""),
                    "doc_name": str(doc.get("name") or doc.get("path") or f"item-{i + 1}"),
                })
            return records
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
    parallelism="reducing",
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
            required=False,
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
    """Combine upstream records. See module docstring for semantics.

    Includes a parallel-source barrier (#837): when the upstream is a
    parallel-fan-out node (via LangGraph's Send API), this tool polls
    `state.parallel_results[upstream]` until all expected sub-results
    have landed. Without the poll, LangGraph fires this node in the
    same super-step as the parallel dispatch — before any transcribe /
    extract / etc. results exist — and the resulting empty aggregate
    poisons everything downstream (catalogue + extract_all both fail
    with 'no text input').

    The barrier is auto-detected: if `state.parallel_results` has any
    pending lists (length < total), wait for them to fill before
    coercing. Only adds latency when the upstream actually IS parallel.
    """
    config = inputs.get("_config") or {}
    mode = config.get("mode") or "concat"
    separator = config.get("separator") or "\n\n---\n\n"
    pretty = bool(config.get("pretty_json", True))

    await _wait_for_parallel_completion(state)

    records = _coerce_records(inputs)
    if not records:
        # Re-resolve inputs from state.outputs in case the resolver was
        # called before parallel_results landed. The path-style inputs
        # (`$.nodes.X.text`) were resolved at call-time; if X was
        # parallel and aggregating mid-run, the resolved text is empty.
        # After _wait_for_parallel_completion, state.outputs[X] should
        # have been populated by the auto-aggregator — re-derive records
        # from that fresh data.
        refreshed = _records_from_state_outputs(inputs, state)
        if refreshed:
            return _aggregate(
                refreshed, mode=mode, separator=separator, pretty=pretty,
            )
        logger.info("aggregate: no upstream records; returning empty payload")
        return {"text": "", "records": [], "count": 0}

    return _aggregate(records, mode=mode, separator=separator, pretty=pretty)


async def _wait_for_parallel_completion(state: State) -> None:
    """Block until every parallel-source in state.parallel_results has
    received len >= total results. Times out after 10 minutes (matches
    the typical LLM call budget) — hung sources surface as a workflow
    abort rather than indefinite blocking. (#837)
    """
    import asyncio
    state_keys = list(state.keys()) if isinstance(state, dict) else "non-dict"
    initial_parallel = state.get("parallel_results", {}) if isinstance(state, dict) else None
    print(
        f"[AGG-WAIT] entering — state.keys={state_keys}, "
        f"parallel_results={initial_parallel!r}"
    )
    deadline = asyncio.get_event_loop().time() + 600
    poll_interval = 0.25
    iters = 0
    while asyncio.get_event_loop().time() < deadline:
        iters += 1
        parallel_results = state.get("parallel_results", {})
        if not parallel_results:
            if iters == 1:
                print("[AGG-WAIT] exit early: no parallel_results in state")
            return  # No parallel sources at all — nothing to wait for.
        all_complete = True
        for node_id, results in parallel_results.items():
            if not results:
                all_complete = False
                if iters % 20 == 1:
                    print(
                        f"[AGG-WAIT] iter={iters}: {node_id} has empty list, waiting"
                    )
                break
            expected = next(
                (r.get("total") for r in results
                 if isinstance(r, dict) and isinstance(r.get("total"), int)),
                None,
            )
            if expected is not None and len(results) < expected:
                all_complete = False
                if iters % 20 == 1:
                    print(
                        f"[AGG-WAIT] iter={iters}: {node_id} at "
                        f"{len(results)}/{expected}, waiting"
                    )
                break
        if all_complete:
            print(f"[AGG-WAIT] complete after {iters} iters")
            return
        await asyncio.sleep(poll_interval)
    logger.warning(
        f"aggregate: TIMEOUT after 600s, iters={iters}, "
        f"final parallel_results={state.get('parallel_results', {})!r}"
    )


def _records_from_state_outputs(
    inputs: dict[str, Any], state: State,
) -> list[dict[str, Any]]:
    """Re-derive records when the resolver-supplied inputs.text is stale.

    Two stale-state scenarios this handles (both #837):

    1. **Resolver-before-parallel race.** The path resolver
       (`$.nodes.X.text`) runs at node-start with whatever state was at
       the time. If parallel completion happens AFTER the resolver,
       inputs.text is empty even though state.outputs[X] now has data.
       Scan state.outputs for non-empty text and use those.

    2. **Cache-hit race.** When the parallel processor cache-hits, it
       returns its result via `state.parallel_results[X] = [...]`
       INSTANTLY — but the auto-aggregator (which is what populates
       `state.outputs[X]`) hasn't fired yet. Resolver finds nothing in
       state.outputs but state.parallel_results IS populated. Scan
       parallel_results too and use the cached `result.text`.

    Conservative — only checks the standard text/documents shape; if
    inputs look custom, returns empty and caller falls back to the
    stale empty payload.
    """
    candidate_texts: list[str] = []

    # Scenario 1: state.outputs has data (auto-aggregator already fired).
    outputs = state.get("outputs", {}) or {}
    for _node_id, node_output in outputs.items():
        if not isinstance(node_output, dict):
            continue
        node_text = node_output.get("text")
        if isinstance(node_text, str) and node_text.strip():
            candidate_texts.append(node_text)
        elif isinstance(node_text, list):
            for t in node_text:
                if isinstance(t, str) and t.strip():
                    candidate_texts.append(t)

    # Scenario 2: state.parallel_results has data but auto-aggregator
    # hasn't run yet (cache-hit fast path). Walk per-Send results and
    # extract their `result.text`. Sort by index to preserve page order.
    if not candidate_texts:
        parallel = state.get("parallel_results", {}) or {}
        for _node_id, results in parallel.items():
            if not isinstance(results, list):
                continue
            sorted_results = sorted(
                (r for r in results if isinstance(r, dict)),
                key=lambda r: r.get("index", 0),
            )
            for item in sorted_results:
                if not item.get("success"):
                    continue
                result = item.get("result")
                if not isinstance(result, dict):
                    continue
                text = result.get("text")
                if isinstance(text, str) and text.strip():
                    candidate_texts.append(text)

    if not candidate_texts:
        return []
    return [
        {
            "index": i,
            "text": t,
            "doc_id": "",
            "doc_name": f"item-{i + 1}",
        }
        for i, t in enumerate(candidate_texts)
    ]
