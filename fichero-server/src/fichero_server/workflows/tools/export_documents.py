"""Export Documents workflow tool.

Exports the selected folder or whole library as Markdown, Word .docx,
and/or Excel .xlsx using the existing export_service functions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fichero_server.db import db_manager
from fichero_server.export_service import (
    export_eleventy_site,
    export_markdown_folder,
    export_word_docx,
    export_excel_xlsx,
)
from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)


EXPORT_DOCUMENTS_CONFIG = {
    "formats": {
        "type": "array",
        "items": {
            "type": "string",
            "enum": ["markdown", "docx", "xlsx", "eleventy"],
        },
        "default": ["markdown", "docx", "xlsx"],
        "description": (
            "Export formats to produce. 'eleventy' publishes an 11ty/Netlify "
            "static website (collections = folders)."
        ),
    },
    "destination": {
        "type": "string",
        "default": "~/Desktop",
        "description": "Output folder path. ~ is expanded to the user home directory.",
    },
}


@register_tool(
    name="export_documents",
    display_name="Export Documents",
    description="Export selected documents as Markdown, Word, and/or Excel files.",
    category="output",
    icon="square.and.arrow.down",
    color="orange",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="source_id",
            name="Source Folder",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="Folder/document ID to export. Uses workflow selection when omitted.",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description=(
                "Upstream document metadata (e.g. from a Files source node). "
                "Used as the export target when neither source_id nor a UI "
                "selection is present."
            ),
        ),
    ],
    output_ports=[
        PortDef(
            id="files",
            name="Files",
            port_type="output",
            data_type=DataType.FILES,
            description="Absolute paths of exported files and folders.",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of export artifacts produced.",
        ),
    ],
    config_schema=EXPORT_DOCUMENTS_CONFIG,
    sort_order=910,
)
async def export_documents(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Export documents to Markdown, DOCX, and/or XLSX.

    Reuses fichero_server.export_service so the output format stays identical to
    the route-driven exporters.
    """
    # Workflow builder passes node config as flat keys in inputs; some direct
    # invocation paths may wrap it under _config. Read both for compatibility.
    config = inputs.get("_config") or {}
    formats = (
        config.get("formats")
        or inputs.get("formats")
        or ["markdown", "docx", "xlsx"]
    )
    destination = (
        config.get("destination")
        or inputs.get("destination")
        or "~/Desktop"
    ).strip()

    source_id = (
        inputs.get("source_id")
        or _resolve_source_id(state)
        or _first_document_id(inputs.get("documents"))
    )

    library_path = state.get("library_path", "")
    if not library_path:
        return {"files": [], "count": 0, "error": "library_path not set"}

    db = db_manager.get_database(library_path)

    destination_path = Path(destination).expanduser().resolve()
    try:
        destination_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("export_documents: cannot create destination %s: %s", destination_path, exc)
        return {"files": [], "count": 0, "error": f"Cannot create destination: {exc}"}

    if not _is_writable(destination_path):
        return {
            "files": [],
            "count": 0,
            "error": f"Destination is not writable: {destination_path}",
        }

    export_name = _export_name(db, source_id)
    export_dir = destination_path / export_name
    export_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    requested_formats = set(formats)

    if "markdown" in requested_formats:
        md_dir = export_dir / f"{export_name}_markdown"
        result = export_markdown_folder(
            db,
            output_path=md_dir,
            target_id=source_id,
            recursive=True,
            overwrite=True,
        )
        written.extend(str(f.path) for f in result.files)
        written.extend(str(a.path) for a in result.assets)

    if "docx" in requested_formats:
        docx_path = export_dir / f"{export_name}.docx"
        result = export_word_docx(
            db,
            output_path=docx_path,
            target_id=source_id,
            recursive=True,
            overwrite=True,
        )
        written.append(str(result.output_path))

    if "xlsx" in requested_formats:
        xlsx_path = export_dir / f"{export_name}.xlsx"
        result = export_excel_xlsx(
            db,
            output_path=xlsx_path,
            target_id=source_id,
            recursive=True,
            overwrite=True,
        )
        written.append(str(result.output_path))

    if "eleventy" in requested_formats:
        # 11ty/Netlify static-site target (#2535), chainable as a workflow node.
        site_dir = export_dir / f"{export_name}_site"
        result = export_eleventy_site(
            db,
            output_path=site_dir,
            target_id=source_id,
            recursive=True,
            overwrite=True,
        )
        written.extend(str(f.path) for f in result.files)
        written.extend(str(a.path) for a in result.assets)

    return {"files": written, "count": len(written)}


def _first_document_id(documents: Any) -> str | None:
    """Return the first upstream document id, if any (#4324).

    The UI selection (state.selected_doc_ids) still wins when present — for a
    folder selection it names the FOLDER itself, while upstream source nodes
    expand a folder to its file descendants. The documents port makes the
    export runnable as a wired graph node when there is no UI selection.
    """
    if not isinstance(documents, list):
        return None
    for doc in documents:
        if isinstance(doc, dict) and doc.get("id"):
            return str(doc["id"])
    return None


def _resolve_source_id(state: State) -> str | None:
    """Return a folder/doc ID from workflow state when the tool input is empty.

    Prefers the first selected document; whole-library export when nothing is
    selected.
    """
    selected = state.get("selected_doc_ids") or []
    return selected[0] if selected else None


def _export_name(db, source_id: str | None) -> str:
    from fichero_server.models import Document

    if source_id:
        doc = db.get(Document, source_id)
        if doc and doc.name:
            return _safe_filename(doc.name)
    return "library-export"


def _safe_filename(name: str) -> str:
    """Return a filesystem-safe name that preserves readable characters."""
    safe = "".join(c if c.isalnum() or c in (" ", "-", "_", ".") else "_" for c in name)
    return safe.strip().strip(".") or "export"


def _is_writable(path: Path) -> bool:
    """Check whether we can create files in .

    Uses os.access on Unix; falls back to a writable probe on other platforms.
    """
    import os

    if os.name != "nt":
        return os.access(path, os.W_OK)
    try:
        probe = path / ".fichero_write_probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False
