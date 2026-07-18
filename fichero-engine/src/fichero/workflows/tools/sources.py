"""
Source Tools

Tools that provide files as input to workflows.
- collection: Files from a library collection
- folder: Files from a specific folder
- search: Files matching a search query

All source tools output FILES (list of file paths) that can be consumed
by downstream processing tools like transcribe, describe, etc.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.db import db_manager
from fichero.models import Document, DocType, FileType
from fichero.llm import LLMConfig
from fichero.retrieval.graph_rag import GraphAwareRetriever

logger = logging.getLogger(__name__)


def _resolve_abs_path(file_doc: "Document", library_root: "str | None") -> str:
    """Resolve a document's stored path to an absolute on-disk path for downstream
    file tools (vision/transcribe/audio).

    Stored paths are library-relative (``files/fi/<hash>_<name>.pdf``) for COPY
    ingests so the bundle can be moved/renamed (#1663). Downstream tools open the
    path directly, which fails when the engine CWD isn't the library root (#2183).
    ``resolve_source`` resolves bookmark (survives moves) → absolute → library-
    relative, confined to allowed roots via path_security. Falls back to the raw
    stored path when it can't resolve, so behaviour is never worse than before:
    a legitimate LINK-ingest file outside the library returns its raw absolute
    path (confinement rejects it, so resolve_source returns None → fallback).
    """
    from fichero.storage import resolve_source

    resolved = resolve_source(file_doc, library_root=library_root)
    return str(resolved) if resolved else (file_doc.path or "")


def _resolve_page_to_parent(doc: "Document", db) -> "Document | None":
    """Resolve a page document to its parent file, preserving page context.

    Page documents have path=None; their parent (typically a PDF) holds the
    file. The files tool emits the selected page document and only borrows the
    parent path; downstream vision tools use the page sequence to process that
    page.

    This helper keeps the path lookup observable:
    - `requested_page` on the returned document's metadata so downstream tools
      that opt into the hint can branch on it without a schema change
    - returned doc is a deep copy so the cached parent Document in the DB
      layer isn't mutated
    """
    if not doc.parent_id:
        return None
    parent = db.get(Document, doc.parent_id)
    if not parent or not parent.path:
        logger.warning(
            "files_tool: doc %s has no path; parent %s also has no path",
            doc.id, doc.parent_id,
        )
        return None
    requested = parent
    if doc.sequence is not None:
        requested = parent.model_copy(deep=True)
        requested.metadata = dict(parent.metadata or {})
        requested.metadata["requested_page"] = doc.sequence
    logger.info(
        "files_tool: page %s (seq=%s) resolved through parent %s path; "
        "downstream receives the selected page document.",
        doc.id, doc.sequence, parent.id,
    )
    return requested


# =============================================================================
# Eager-load cap (#2544)
# =============================================================================

# A folder/collection source otherwise loads ALL Documents eagerly into workflow
# state: a 100k-image folder materializes 100k Document objects + 100k JSON dicts
# before any processing starts, which blows up RAM up front. We bound that eager
# load with a generous default cap, overridable per install via the
# FICHERO_SOURCE_MAX_FILES env var. The default is high enough that normal
# folders (Marshall/Choco) are never clipped; only pathologically huge folders
# hit it, and when they do we LOG LOUDLY (no silent truncation).
_DEFAULT_SOURCE_MAX_FILES = 5000


def _source_max_files() -> int:
    """Resolve the default eager-load cap from FICHERO_SOURCE_MAX_FILES (#2544).

    Returns the configured cap, or ``_DEFAULT_SOURCE_MAX_FILES`` when unset/blank.
    A value of ``0`` (or negative) is the explicit opt-in for "all files" — no
    cap. An unparseable value falls back to the default with a loud warning.
    """
    raw = os.environ.get("FICHERO_SOURCE_MAX_FILES")
    if raw is None or raw.strip() == "":
        return _DEFAULT_SOURCE_MAX_FILES
    try:
        value = int(raw.strip())
    except ValueError:
        logger.warning(
            "FICHERO_SOURCE_MAX_FILES=%r is not an integer — using default cap %d",
            raw,
            _DEFAULT_SOURCE_MAX_FILES,
        )
        return _DEFAULT_SOURCE_MAX_FILES
    return value if value > 0 else 0  # <= 0 = unbounded (explicit "all files")


def _resolve_source_limit(requested: int) -> int:
    """Resolve the effective file cap for a source tool run (#2544).

    An explicit per-run ``limit`` from the tool inputs always wins (it is already
    a deliberate cap). When none is set — the common case, ``requested == 0`` —
    fall back to the env-configured default cap so a huge folder doesn't blow up
    RAM up front. Returns ``0`` for unbounded.
    """
    if requested and requested > 0:
        return requested
    return _source_max_files()


def _load_capped_folder_files(
    db,
    folder_id: str,
    *,
    recursive: bool,
    file_types: list[str] | None,
    status_filter: str,
    requested_limit: int,
    source_label: str,
) -> list["Document"]:
    """Load files in a folder, bounded by the effective source cap (#2544).

    Returns the (possibly truncated) list of Documents, preserving the existing
    ``_get_files_in_folder`` ordering so ``files``/``documents`` stay index-
    aligned downstream. When the cap clips the folder, logs LOUDLY that only the
    first N were taken and how to raise the cap — it never silently truncates as
    if it had processed everything.
    """
    cap = _resolve_source_limit(requested_limit)
    if cap <= 0:
        # Explicit opt-in to load every file (FICHERO_SOURCE_MAX_FILES=0).
        return _get_files_in_folder(
            db=db,
            folder_id=folder_id,
            recursive=recursive,
            file_types=file_types,
            status_filter=status_filter,
            limit=0,
        )
    # Fetch one extra so we can distinguish "exactly cap files, all taken" from
    # "more than cap exist, clipped" without a second full traversal.
    files = _get_files_in_folder(
        db=db,
        folder_id=folder_id,
        recursive=recursive,
        file_types=file_types,
        status_filter=status_filter,
        limit=cap + 1,
    )
    if len(files) > cap:
        taken = files[:cap]
        logger.warning(
            "%s: folder has MORE than the %d-file source cap — taking the first "
            "%d of (at least) %d+ files; the remainder are NOT processed this "
            "run. Raise FICHERO_SOURCE_MAX_FILES=<n> (or set it to 0 for all "
            "files) to process everything.",
            source_label,
            cap,
            cap,
            cap,
        )
        return taken
    return files


# =============================================================================
# Files Tool
# =============================================================================


@register_tool(
    name="files",
    display_name="Files",
    description="Pass through input files from workflow context",
    category="source",
    icon="doc.on.doc",
    color="green",
    uses_llm=False,
    supports_batch=False,
    tested=True,  # part of the validated HTR transcription chain
    input_ports=[
        PortDef(
            id="query",
            name="Query",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="Search query",
        ),
    ],
    output_ports=[
        PortDef(
            id="files",
            name="Files",
            port_type="output",
            data_type=DataType.FILES,
            description="Input file paths",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="output",
            data_type=DataType.JSON,
            description="Input document metadata",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of input files",
        ),
    ],
    sort_order=1,
)
async def files_tool(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Return files/documents already provided to this workflow execution.

    Priority:
    1. Explicit inputs["files"] from mapped upstream data
    2. state["selected_doc_ids"] — document IDs passed from the UI selection
    3. state["input_files"] from executor initialization
    """
    # Priority 1: explicit upstream mapping (skip if empty — fall through to state-based selection)
    raw_files = inputs.get("files")
    if raw_files:
        if isinstance(raw_files, str):
            files = [raw_files]
        else:
            files = list(raw_files or [])
        raw_documents = inputs.get("documents") or state.get("documents", [])
        documents = list(raw_documents or [])
        logger.info(f"Files source tool: {len(files)} files from explicit inputs")
        return {"files": files, "documents": documents, "count": len(files)}

    # Priority 2: UI selection passed via execute inputs
    selected_doc_ids = state.get("selected_doc_ids", [])
    if selected_doc_ids:
        library_path = state.get("library_path")
        if not library_path:
            logger.warning("files_tool: selected_doc_ids present but library_path missing — falling through to input_files")
        else:
            db = db_manager.get_database(library_path)
            docs = [db.get(Document, doc_id) for doc_id in selected_doc_ids]
            docs = [d for d in docs if d is not None]
            if len(docs) < len(selected_doc_ids):
                missing = set(selected_doc_ids) - {d.id for d in docs}
                logger.warning(
                    "files_tool: %d/%d selected_doc_ids not found (stale/invalid): %s",
                    len(missing),
                    len(selected_doc_ids),
                    list(missing)[:5],
                )

            # Stored paths are library-relative (e.g. "files/fi/<hash>_<name>.pdf")
            # for COPY ingests, so the bundle can be renamed/moved (#1663). Downstream
            # tools (vision/transcribe) open these paths directly, which fails when
            # the engine CWD isn't the library root. Resolve each file to its absolute,
            # confined on-disk path via the canonical resolver; fall back to the raw
            # path if it can't resolve so behaviour is never worse than before.
            def _abs(file_doc: "Document") -> str:
                return _resolve_abs_path(file_doc, library_path)

            # Per-page fan-out (#891). We emit one (file_path, document)
            # entry per ATOMIC UNIT of work:
            # - Folder → recursively expand to file descendants
            # - Parent PDF (or any file with page children) → expand to
            #   one entry per page child. Each entry shares the parent's
            #   on-disk path (downstream tools use the document.id and
            #   .page_content, not just the path). This gives extract_all
            #   a per-page source_document_id so every entity/claim is
            #   anchored to a specific page.
            # - Leaf file (no page children) → one entry as before
            # - Page selected directly → one entry, parent resolved for path
            #
            # `pairs` preserves order and supports duplicate paths (which
            # parent PDFs WILL have, one per page child). Earlier code
            # used a path-keyed dict that collapsed page children.
            pairs: list[tuple[str, Document]] = []
            seen_ids: set[str] = set()

            # Bound the eager load (#2544): selecting a 100k-image folder in the
            # UI would otherwise expand to 100k (path, Document) pairs and 100k
            # JSON dicts below. files_tool has no explicit limit input, so use
            # the env-configured default cap. 0 = unbounded (explicit opt-in).
            _pairs_cap = _source_max_files()
            _cap_logged = False

            def _add(path: str, document: Document) -> None:
                nonlocal _cap_logged
                if document.id in seen_ids:
                    return
                if _pairs_cap > 0 and len(pairs) >= _pairs_cap:
                    if not _cap_logged:
                        logger.warning(
                            "files_tool: selection expands to MORE than the "
                            "%d-file source cap — taking the first %d files "
                            "only; the remainder are NOT processed this run. "
                            "Raise FICHERO_SOURCE_MAX_FILES=<n> (or 0 for all "
                            "files) to process everything.",
                            _pairs_cap,
                            _pairs_cap,
                        )
                        _cap_logged = True
                    return
                seen_ids.add(document.id)
                pairs.append((path, document))

            def _expand_to_pages(file_doc: Document) -> bool:
                """If file_doc has page children, emit one entry per page
                and return True. Otherwise return False.

                Gated on file_type == .pdf because only PDFs currently
                get per-page children at ingest time. Saves a DB query
                for every leaf file in folder expansions and keeps the
                pre-#891 contract for non-PDFs.
                """
                if not file_doc.path:
                    return False
                if file_doc.file_type != FileType.pdf:
                    return False
                page_children = db.query(
                    Document, parent_id=file_doc.id, doc_type=DocType.page
                )
                if not page_children:
                    # No page children — a PDF imported before per-page splitting
                    # landed, or where the split silently failed at ingest
                    # (#2430). Split on the spot so the workflow fans out
                    # per-page instead of transcribing the whole PDF onto the
                    # parent. This auto-backfills already-imported PDFs on their
                    # next workflow run. (no-silent-fallback)
                    from pathlib import Path

                    from fichero.ingest import _create_pdf_page_children

                    abs_path = _abs(file_doc)
                    try:
                        created = _create_pdf_page_children(
                            file_doc, Path(abs_path), db, auto_embed=False
                        )
                    except Exception as exc:
                        logger.error(
                            "files_tool: on-the-spot PDF split failed for %s: %s",
                            file_doc.id,
                            exc,
                        )
                        created = []
                    if not created:
                        return False
                    logger.info(
                        "files_tool: split %s into %d page children on the spot "
                        "(was unsplit at ingest, #2430)",
                        file_doc.id,
                        len(created),
                    )
                    page_children = created
                ordered = sorted(page_children, key=lambda p: p.sequence or 0)
                abs_path = _abs(file_doc)  # resolve the parent file once, not per page
                for page in ordered:
                    _add(abs_path, page)
                return True

            def _expand_folder(folder: Document) -> None:
                """Recursively collect file descendants of a folder."""
                children = db.query(Document, parent_id=folder.id)
                for child in children:
                    if child.doc_type == DocType.folder:
                        _expand_folder(child)
                    elif child.path and not _expand_to_pages(child):
                        _add(_abs(child), child)

            for doc in docs:
                if doc.doc_type == DocType.folder:
                    _expand_folder(doc)
                    logger.info(
                        f"files_tool: expanded folder {doc.id} → {len(pairs)} entries so far"
                    )
                elif doc.path:
                    if not _expand_to_pages(doc):
                        _add(_abs(doc), doc)
                elif doc.parent_id:
                    # Page selected directly — emit just this page,
                    # using the parent's path as the file pointer.
                    resolved_parent = _resolve_page_to_parent(doc, db)
                    if resolved_parent is not None and resolved_parent.path:
                        _add(_abs(resolved_parent), doc)
                else:
                    logger.warning(
                        f"files_tool: doc {doc.id} type={doc.doc_type} "
                        "has no path and no parent — skipping"
                    )

            files = [path for path, _ in pairs]
            documents = [d.model_dump(mode="json") for _, d in pairs]
            logger.info(
                f"Files source tool: {len(files)} entries from selected_doc_ids "
                f"({len(seen_ids)} unique docs)"
            )
            return {"files": files, "documents": documents, "count": len(files)}

    # Priority 3: executor-level input_files
    raw_files = state.get("input_files", [])
    if isinstance(raw_files, str):
        files = [raw_files]
    else:
        files = list(raw_files or [])

    raw_documents = state.get("documents", [])
    documents = list(raw_documents or [])

    logger.info(f"Files source tool: {len(files)} files from input_files")
    return {"files": files, "documents": documents, "count": len(files)}


# =============================================================================
# Selection Tool
# =============================================================================


@register_tool(
    name="selection",
    display_name="Selection",
    description="Use the currently selected documents from the library UI",
    category="source",
    icon="cursorarrow.rays",
    color="green",
    uses_llm=False,
    supports_batch=False,
    input_ports=[],  # Source - no inputs
    output_ports=[
        PortDef(
            id="files",
            name="Files",
            port_type="output",
            data_type=DataType.FILES,
            description="File paths from current selection",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="output",
            data_type=DataType.JSON,
            description="Selected document metadata",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of selected files",
        ),
    ],
    sort_order=2,
)
async def selection_tool(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Resolve selected_doc_ids from workflow state into workflow files.

    Unlike ``files_tool``, this node fails fast when no selection is present.
    """
    selected_doc_ids = list(state.get("selected_doc_ids") or [])
    if not selected_doc_ids:
        return {
            "files": [],
            "documents": [],
            "count": 0,
            "error": "No documents selected. Select one or more documents before running this workflow.",
        }

    return await files_tool(inputs={}, state=state, llm_config=llm_config)


# =============================================================================
# Collection Tool
# =============================================================================


@register_tool(
    name="collection",
    display_name="Collection",
    description="Get all files from a library collection",
    category="source",
    icon="folder",
    color="green",
    uses_llm=False,
    supports_batch=False,
    input_ports=[],  # Source - no inputs
    output_ports=[
        PortDef(
            id="files",
            name="Files",
            port_type="output",
            data_type=DataType.FILES,
            description="File paths from collection",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="output",
            data_type=DataType.JSON,
            description="Full document metadata",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of files",
        ),
    ],
    config_schema={
        "collection_id": {"type": "string", "description": "Collection"},
        "recursive": {
            "type": "boolean",
            "default": True,
            "description": "Include subfolders",
        },
        "file_types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "File types",
        },
        "status_filter": {
            "type": "string",
            "enum": ["all", "pending", "completed"],
            "default": "all",
            "description": "Status",
        },
        "limit": {"type": "integer", "default": 0, "description": "Max files"},
    },
    sort_order=2,
)
async def collection_tool(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Get files from a library collection.

    Args:
        inputs: Config containing collection_id and filters
        state: Workflow state (contains library_path)
        llm_config: Not used for this tool

    Returns:
        Dict with files (paths), documents (full metadata), count
    """
    collection_id = inputs.get("collection_id")
    if not collection_id:
        return {
            "files": [],
            "documents": [],
            "count": 0,
            "error": "No collection_id provided",
        }

    # Priority 0: UI selection override — if specific doc IDs were selected,
    # return only those docs instead of the whole collection.
    selected_doc_ids = state.get("selected_doc_ids", [])
    if selected_doc_ids:
        library_path = state.get("library_path") or inputs.get("library_path")
        if library_path:
            db = db_manager.get_database(library_path)
            docs = [db.get(Document, doc_id) for doc_id in selected_doc_ids]
            docs = [d for d in docs if d is not None]
            # Use list-of-pairs so multiple pages of the same PDF are kept
            # as separate entries (dict keyed by path collapses them, #2242).
            resolved_pairs: list[tuple[str, Document]] = []
            seen_ids: set[str] = set()
            for doc in docs:
                if doc.id in seen_ids:
                    continue
                if doc.path:
                    seen_ids.add(doc.id)
                    resolved_pairs.append((_resolve_abs_path(doc, library_path), doc))
                elif doc.parent_id:
                    resolved_parent = _resolve_page_to_parent(doc, db)
                    if resolved_parent is not None and resolved_parent.path:
                        seen_ids.add(doc.id)
                        resolved_pairs.append(
                            (_resolve_abs_path(resolved_parent, library_path), doc)
                        )
            files = [path for path, _ in resolved_pairs]
            documents = [d.model_dump(mode="json") for _, d in resolved_pairs]
            logger.info(
                f"collection_tool: {len(files)} files from selected_doc_ids "
                f"(overriding collection {collection_id})"
            )
            return {"files": files, "documents": documents, "count": len(files)}

    recursive = inputs.get("recursive", True)
    file_types = inputs.get("file_types", [])
    status_filter = inputs.get("status_filter", "all")
    limit = inputs.get("limit", 0)

    # Get library path from state or config
    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        return {
            "files": [],
            "documents": [],
            "count": 0,
            "error": "No library_path in state",
        }

    try:
        db = db_manager.get_database(library_path)

        # Get all files in collection, bounded by the eager-load cap (#2544).
        files = _load_capped_folder_files(
            db,
            collection_id,
            recursive=recursive,
            file_types=file_types,
            status_filter=status_filter,
            requested_limit=limit,
            source_label=f"Collection {collection_id}",
        )

        # Keep file_paths and doc_data index-aligned: filter both by doc.path (#2240)
        aligned = [(doc, _resolve_abs_path(doc, library_path)) for doc in files if doc.path]
        file_paths = [path for _, path in aligned]
        doc_data = [doc.model_dump(mode="json") for doc, _ in aligned]

        logger.info(f"Collection {collection_id}: found {len(files)} files")

        return {
            "files": file_paths,
            "documents": doc_data,
            "count": len(files),
        }

    except Exception as e:
        logger.error(f"Collection tool failed: {e}")
        return {"files": [], "documents": [], "count": 0, "error": str(e)}


# =============================================================================
# Folder Tool
# =============================================================================


@register_tool(
    name="folder",
    display_name="Folder",
    description="Get files from a specific folder",
    category="source",
    icon="folder.fill",
    color="green",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="query",
            name="Query",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="Search query",
        ),
    ],
    output_ports=[
        PortDef(
            id="files",
            name="Files",
            port_type="output",
            data_type=DataType.FILES,
            description="File paths from folder",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="output",
            data_type=DataType.JSON,
            description="Full document metadata",
        ),
        PortDef(
            id="subfolders",
            name="Subfolders",
            port_type="output",
            data_type=DataType.JSON,
            description="Direct subfolder IDs",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of files",
        ),
    ],
    config_schema={
        "folder_id": {"type": "string", "description": "Folder ID"},
        "folder_path": {"type": "string", "description": "Folder path"},
        "include_subfolders": {
            "type": "boolean",
            "default": False,
            "description": "Include subfolders",
        },
        "file_types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "File types",
        },
        "limit": {"type": "integer", "default": 0, "description": "Max files"},
    },
    sort_order=3,
)
async def folder_tool(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Get files from a specific folder.

    Unlike collection, folder is for targeting a specific subfolder
    and can output subfolders for hierarchical processing.
    """
    folder_id = inputs.get("folder_id")
    folder_path = inputs.get("folder_path")

    if not folder_id and not folder_path:
        return {
            "files": [],
            "documents": [],
            "subfolders": [],
            "count": 0,
            "error": "No folder_id or folder_path provided",
        }

    include_subfolders = inputs.get("include_subfolders", False)
    file_types = inputs.get("file_types", [])
    limit = inputs.get("limit", 0)

    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        return {
            "files": [],
            "documents": [],
            "subfolders": [],
            "count": 0,
            "error": "No library_path in state",
        }

    try:
        db = db_manager.get_database(library_path)

        # If folder_path provided, find the folder by path
        if not folder_id and folder_path:
            # Find folder by name/path - simplified for now
            folders = db.query(
                Document, doc_type=DocType.folder, name=folder_path.split("/")[-1]
            )
            if folders:
                folder_id = folders[0].id
            else:
                return {
                    "files": [],
                    "documents": [],
                    "subfolders": [],
                    "count": 0,
                    "error": f"Folder not found: {folder_path}",
                }

        # Get files, bounded by the eager-load cap (#2544).
        files = _load_capped_folder_files(
            db,
            folder_id,
            recursive=include_subfolders,
            file_types=file_types,
            status_filter="all",
            requested_limit=limit,
            source_label=f"Folder {folder_id}",
        )

        # Get direct subfolders (for hierarchical processing)
        subfolders = db.query(Document, parent_id=folder_id, doc_type=DocType.folder)
        subfolder_ids = [sf.id for sf in subfolders]

        # Resolve abs paths, keep file_paths/doc_data index-aligned, and
        # expand PDFs that already have per-page children (#2239/#2240).
        aligned_paths: list[str] = []
        aligned_docs: list[Document] = []
        for doc in files:
            if not doc.path:
                continue
            abs_path = _resolve_abs_path(doc, library_path)
            if doc.file_type == FileType.pdf:
                page_children = db.query(Document, parent_id=doc.id, doc_type=DocType.page)
                if page_children:
                    for page in sorted(page_children, key=lambda p: p.sequence or 0):
                        aligned_paths.append(abs_path)
                        aligned_docs.append(page)
                    continue
            aligned_paths.append(abs_path)
            aligned_docs.append(doc)
        file_paths = aligned_paths
        doc_data = [d.model_dump(mode="json") for d in aligned_docs]

        logger.info(
            f"Folder {folder_id}: found {len(files)} files, {len(subfolder_ids)} subfolders"
        )

        return {
            "files": file_paths,
            "documents": doc_data,
            "subfolders": subfolder_ids,
            "count": len(files),
        }

    except Exception as e:
        logger.error(f"Folder tool failed: {e}")
        return {
            "files": [],
            "documents": [],
            "subfolders": [],
            "count": 0,
            "error": str(e),
        }


# =============================================================================
# Search Tool
# =============================================================================


@register_tool(
    name="search",
    display_name="Search",
    description="Find files matching a search query",
    category="source",
    icon="magnifyingglass",
    color="green",
    uses_llm=False,
    supports_batch=False,
    tested=True,  # part of the validated HTR transcription chain
    input_ports=[
        # The run function reads inputs.get("query"), and the shipped
        # transcription presets feed a draft transcription into it as the
        # search query. Declaring the port lets graph validation accept
        # that edge instead of rejecting an "unknown target port 'query'".
        PortDef(
            id="query",
            name="Query",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="Search query",
        ),
    ],
    output_ports=[
        PortDef(
            id="files",
            name="Files",
            port_type="output",
            data_type=DataType.FILES,
            description="Matching file paths",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="output",
            data_type=DataType.JSON,
            description="Full document metadata with scores",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of matches",
        ),
    ],
    config_schema={
        "query": {"type": "string", "description": "Search query"},
        "search_type": {
            "type": "string",
            "enum": ["hybrid", "semantic", "fulltext"],
            "default": "hybrid",
            "description": "Search type",
        },
        "collection_id": {"type": "string", "description": "Collection"},
        "file_types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "File types",
        },
        "status_filter": {
            "type": "string",
            "enum": ["all", "pending", "completed"],
            "default": "all",
            "description": "Status",
        },
        "min_score": {"type": "number", "default": 0.0, "description": "Min score"},
        "limit": {"type": "integer", "default": 100, "description": "Max results"},
        "graph_hops": {
            "type": "integer",
            "default": 1,
            "description": "KG traversal depth for graph-aware retrieval",
        },
        "max_kg_claims": {
            "type": "integer",
            "default": 12,
            "description": "Max KG claim context rows to add",
        },
    },
    sort_order=4,
)
async def search_tool(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Find files matching a search query.

    Uses the database's hybrid search (semantic + fulltext).
    Can be filtered by collection, file type, and status.
    """
    query = inputs.get("query")
    if not query:
        # #2613: a missing query is a graceful skip, not a systemic failure.
        # Downstream nodes receive empty arrays and the UI sees a clear
        # "skipped — no query" status instead of an aborted run.
        return {
            "files": [],
            "documents": [],
            "count": 0,
            "skipped": True,
            "skip_reason": "No search query provided",
        }

    search_type = inputs.get("search_type", "hybrid")
    collection_id = inputs.get("collection_id")
    file_types = inputs.get("file_types", [])
    status_filter = inputs.get("status_filter", "all")
    min_score = inputs.get("min_score", 0.0)
    limit = inputs.get("limit", 100)
    graph_hops = max(0, min(3, int(inputs.get("graph_hops", 1))))
    max_kg_claims = max(0, min(100, int(inputs.get("max_kg_claims", 12))))

    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        return {
            "files": [],
            "documents": [],
            "count": 0,
            "error": "No library_path in state",
        }

    try:
        db = db_manager.get_database(library_path)

        # Build filters
        filters = {}
        if file_types:
            filters["file_type"] = file_types[0] if len(file_types) == 1 else file_types
        if status_filter != "all":
            filters["status"] = status_filter

        retrieval = GraphAwareRetriever(db).retrieve(
            query=query,
            max_sources=limit,
            include_sources=False,
            search_type=search_type,
            filters=filters,
            min_score=min_score,
            graph_hops=graph_hops,
            max_kg_claims=max_kg_claims,
        )

        files = []
        doc_data = []

        for item in retrieval.context_docs:
            if item.get("kind") == "document":
                doc = db.get(Document, item.get("id"))
                if doc is None:
                    continue
                # If collection_id filter, check ancestry
                if collection_id and not _is_descendant_of(db, doc, collection_id):
                    continue
                if doc.path:
                    files.append(_resolve_abs_path(doc, library_path))
                doc_dict = doc.model_dump(mode="json")
                doc_dict["search_score"] = item.get("search_score")
                doc_dict["highlights"] = None
                doc_data.append(doc_dict)
                continue

            # KG-augmented context rows are useful to researcher flows,
            # but are not filesystem inputs for downstream file tools.
            doc_data.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "page_content": item.get("content"),
                    "doc_type": "kg_claim",
                    "file_type": None,
                    "path": None,
                    "search_score": None,
                    "highlights": None,
                    "kind": item.get("kind"),
                }
            )

        logger.info(
            "research_search query_len=%d search_type=%s limit=%d "
            "graph_hops=%d max_kg_claims=%d document_count=%d context_count=%d "
            "kg_claims_used=%d kg_entities_used=%d",
            len(query or ""),
            search_type,
            limit,
            graph_hops,
            max_kg_claims,
            len(files),
            len(doc_data),
            getattr(retrieval, "kg_claims_used", 0),
            getattr(retrieval, "kg_entities_used", 0),
        )

        return {
            "files": files,
            "documents": doc_data,
            "count": len(files),
            "document_count": len(files),
            "context_count": len(doc_data),
            "kg_claims_used": getattr(retrieval, "kg_claims_used", 0),
            "kg_entities_used": getattr(retrieval, "kg_entities_used", 0),
        }

    except Exception as e:
        if _is_reference_search_unavailable_error(e):
            logger.info(
                "Search tool: reference corpus/index unavailable, returning empty result: %s",
                e,
            )
            return {
                "files": [],
                "documents": [],
                "count": 0,
                "document_count": 0,
                "context_count": 0,
                "kg_claims_used": 0,
                "kg_entities_used": 0,
            }
        logger.error(f"Search tool failed: {e}")
        return {
            "files": [],
            "documents": [],
            "count": 0,
            "document_count": 0,
            "context_count": 0,
            "kg_claims_used": 0,
            "kg_entities_used": 0,
            "error": str(e),
        }


# =============================================================================
# Helper Functions
# =============================================================================


def _is_reference_search_unavailable_error(exc: Exception) -> bool:
    """Return True when search infra is absent and reference search should be optional.

    Transcription presets use the search node as auxiliary context for pass-two
    review. A library with no vector/search index should produce an empty
    reference list, not abort the whole workflow after pass one already saved
    its artifacts.
    """
    message = str(exc).lower()
    infra_markers = (
        "embedding",
        "embeddings",
        "vector",
        "vectors",
        "lance",
        "search index",
        "fts",
        "full-text",
        "full text",
        "bm25",
        "index",
    )
    unavailable_markers = (
        "does not exist",
        "not found",
        "no such",
        "missing",
        "unavailable",
        "not available",
        "cannot open",
        "failed to open",
    )
    return any(marker in message for marker in infra_markers) and any(
        marker in message for marker in unavailable_markers
    )


def _get_files_in_folder(
    db,
    folder_id: str,
    recursive: bool = True,
    file_types: list[str] | None = None,
    status_filter: str = "all",
    limit: int = 0,
) -> list[Document]:
    """Get all files in a folder (optionally recursive).

    Args:
        db: Database instance
        folder_id: Parent folder ID
        recursive: Whether to include files from subfolders
        file_types: Optional filter by file type
        status_filter: "all", "pending", or "completed"
        limit: Max files to return (0 = no limit)

    Returns:
        List of Document objects
    """
    files = []

    # Get direct children that are files
    children = db.query(Document, parent_id=folder_id)

    for child in children:
        # If it's a file, add it
        if child.doc_type == DocType.file:
            # Apply filters
            if (
                file_types
                and child.file_type
                and child.file_type.value not in file_types
            ):
                continue
            if status_filter == "pending" and child.status.value != "pending":
                continue
            if status_filter == "completed" and child.status.value != "completed":
                continue

            files.append(child)

            if limit > 0 and len(files) >= limit:
                return files

        # If it's a folder and recursive, recurse
        elif child.doc_type == DocType.folder and recursive:
            subfolder_files = _get_files_in_folder(
                db=db,
                folder_id=child.id,
                recursive=True,
                file_types=file_types,
                status_filter=status_filter,
                limit=limit - len(files) if limit > 0 else 0,
            )
            files.extend(subfolder_files)

            if limit > 0 and len(files) >= limit:
                return files

    return files


def _is_descendant_of(db, doc: Document, ancestor_id: str) -> bool:
    """Check if document is a descendant of a folder.

    Walks up the parent chain to see if ancestor_id is in it.
    """
    current = doc
    visited = set()  # Prevent infinite loops

    while current and current.id not in visited:
        visited.add(current.id)

        if current.parent_id == ancestor_id:
            return True
        if current.parent_id is None:
            return False

        current = db.get(Document, current.parent_id)

    return False
