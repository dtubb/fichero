"""
Write File Tool

Writes upstream text / artifact / catalogue content to a user-chosen
directory from inside a workflow. Two modes:

- "per_file":  writes one file per upstream document (fan-out preserved).
               Good for per-image transcripts.
- "aggregate": concatenates all upstream text into a single file.
               Good for catalogue exports or merged report documents.

Safety: filenames derived from a template are sanitized — no "..", no
absolute paths, no path separators leak through. Collisions auto-suffix
"-2", "-3", … instead of clobbering. The output_dir is the user's
responsibility to pick (folder picker in the node editor); the tool
refuses to write outside it.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)


WRITE_FILE_CONFIG = {
    "output_dir": {
        "type": "string",
        "default": "",
        "description": "Folder to write files into (absolute path).",
    },
    "filename_template": {
        "type": "string",
        "default": "{doc_name}-{tool}-{model}.{ext}",
        "description": "Filename template. Placeholders: {doc_name}, {tool}, "
        "{model}, {provider}, {ext}, {index}.",
    },
    "format": {
        "type": "string",
        "enum": ["txt", "md", "json"],
        "default": "txt",
        "description": "Output file format (chooses extension + content encoding).",
    },
    "mode": {
        "type": "string",
        "enum": ["per_file", "aggregate"],
        "default": "per_file",
        "description": "per_file writes one file per upstream doc; "
        "aggregate writes one combined file for the whole run.",
    },
    "aggregate_separator": {
        "type": "string",
        "default": "\n\n---\n\n",
        "description": "Separator between records in aggregate mode.",
    },
}


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._\- ]")


def _safe_filename(raw: str, fallback: str = "file") -> str:
    """Return raw with path-unsafe chars replaced.

    Path-safe means no separators, no '..', no leading dot, no empty. The
    sanitized string preserves intent (alphanumerics, dash, underscore,
    dot, space) but drops anything else.
    """
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", raw).strip(" .")
    if not cleaned or cleaned == "." or ".." in cleaned:
        return fallback
    return cleaned[:200]


def _render_template(
    template: str,
    *,
    doc_name: str,
    tool: str,
    model: str,
    provider: str,
    ext: str,
    index: int,
) -> str:
    """Substitute placeholders and sanitize the result.

    Template tokens are substituted as a single safe step then the whole
    string is sanitized so a malicious placeholder value (e.g. a doc name
    containing "/../") cannot escape the output directory.
    """
    raw = template
    for key, value in (
        ("{doc_name}", doc_name),
        ("{tool}", tool),
        ("{model}", model),
        ("{provider}", provider),
        ("{ext}", ext),
        ("{index}", str(index)),
    ):
        raw = raw.replace(key, value)
    return _safe_filename(raw, fallback=f"{tool}-{index}.{ext}")


def _unique_path(directory: Path, filename: str) -> Path:
    """Return a path inside `directory` that doesn't exist yet.

    If filename already exists, append "-2", "-3", … before the extension.
    """
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for i in range(2, 10_000):
        candidate = directory / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(
        f"Unable to find unique filename under {directory} after 10000 attempts"
    )


def _coerce_text(value: Any) -> str:
    """Turn whatever upstream handed us into a UTF-8 writable string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "\n".join(_coerce_text(v) for v in value)
    if isinstance(value, dict):
        import json

        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _extract_records(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten upstream inputs into (doc_name, text, extra) records.

    Accepts either a parallel-style dict with per-file lists (text, documents)
    or a simple text+documents pair. Downstream writes one record per
    per-file run; aggregate mode concatenates them.
    """
    texts_raw = inputs.get("text")
    documents_raw = inputs.get("documents") or []
    if not isinstance(documents_raw, list):
        documents_raw = [documents_raw] if documents_raw else []

    texts: list[str]
    if isinstance(texts_raw, list):
        texts = [_coerce_text(t) for t in texts_raw]
    elif texts_raw is None:
        texts = []
    else:
        texts = [_coerce_text(texts_raw)]

    if not texts:
        return []

    records: list[dict[str, Any]] = []
    for i, text in enumerate(texts):
        doc = documents_raw[i] if i < len(documents_raw) else {}
        if not isinstance(doc, dict):
            doc = {}
        records.append({
            "index": i,
            "text": text,
            "doc_name": str(doc.get("name") or doc.get("path") or f"item-{i + 1}"),
            "doc_id": str(doc.get("id") or ""),
        })
    return records


@register_tool(
    name="write_file",
    display_name="Write File",
    description="Save upstream text to a file on disk (per-file or aggregate).",
    category="output",
    icon="square.and.arrow.down",
    color="orange",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            description="Text to write (string, list of strings, or dict).",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description="Optional upstream document metadata for filename templating.",
        ),
    ],
    output_ports=[
        PortDef(
            id="output_files",
            name="Output Files",
            port_type="output",
            data_type=DataType.ARRAY,
            description="Absolute paths of files written.",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of files written.",
        ),
    ],
    config_schema=WRITE_FILE_CONFIG,
    sort_order=900,
)
async def write_file(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Write upstream text to disk.

    Never raises — on failure returns an empty output_files list and logs
    the error. Workflow runs shouldn't crash because the user picked a
    folder they've since deleted.
    """
    config = inputs.get("_config") or {}
    output_dir_raw = (config.get("output_dir") or "").strip()
    if not output_dir_raw:
        logger.warning("write_file: output_dir is empty, nothing to do")
        return {"output_files": [], "count": 0, "error": "output_dir not set"}

    output_dir = Path(output_dir_raw).expanduser().resolve()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("write_file: cannot create %s: %s", output_dir, exc)
        return {"output_files": [], "count": 0, "error": str(exc)}

    template = config.get("filename_template") or "{doc_name}-{tool}-{model}.{ext}"
    ext = config.get("format") or "txt"
    mode = config.get("mode") or "per_file"
    separator = config.get("aggregate_separator") or "\n\n---\n\n"

    provider = getattr(llm_config, "provider", "") or ""
    model = getattr(llm_config, "model", "") or ""
    upstream_tool = str(config.get("_upstream_tool") or "write")

    records = _extract_records(inputs)
    if not records:
        logger.info("write_file: no records to write")
        return {"output_files": [], "count": 0}

    written: list[str] = []

    if mode == "aggregate":
        combined = separator.join(rec["text"] for rec in records)
        filename = _render_template(
            template,
            doc_name="aggregate",
            tool=upstream_tool,
            model=model or "unknown",
            provider=provider,
            ext=ext,
            index=0,
        )
        # Template might already end with .{ext}; if not, append it.
        if not filename.lower().endswith(f".{ext.lower()}"):
            filename = f"{filename}.{ext}"
        path = _unique_path(output_dir, filename)
        try:
            path.write_text(combined, encoding="utf-8")
            written.append(str(path))
            logger.info("write_file: wrote aggregate %s", path)
        except OSError as exc:
            logger.error("write_file: failed to write %s: %s", path, exc)
    else:  # per_file
        for rec in records:
            filename = _render_template(
                template,
                doc_name=rec["doc_name"],
                tool=upstream_tool,
                model=model or "unknown",
                provider=provider,
                ext=ext,
                index=rec["index"],
            )
            if not filename.lower().endswith(f".{ext.lower()}"):
                filename = f"{filename}.{ext}"
            path = _unique_path(output_dir, filename)
            try:
                path.write_text(rec["text"], encoding="utf-8")
                written.append(str(path))
            except OSError as exc:
                logger.error("write_file: failed to write %s: %s", path, exc)

    return {"output_files": written, "count": len(written)}
