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
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.db import db_manager
from fichero.models import Document, DocType, FileType
from fichero.llm import LLMConfig

logger = logging.getLogger(__name__)


def _resolve_page_to_parent(doc: "Document", db) -> "Document | None":
    """Resolve a page document to its parent file, preserving page context.

    Page documents have path=None; their parent (typically a PDF) holds the
    file. Today no downstream tool supports per-page OCR — process_vision
    OCRs the whole PDF regardless — so the user selecting "page 3" of a
    100-page book ends up processing all 100 pages. Per-page fan-out is
    tracked in the 0.0.3 #670 follow-up.

    Until then, this helper at least makes the promotion observable:
    - loud warning in the log so the behaviour isn't silent
    - `requested_page` and `page_promotion_warning` on the returned
      document's metadata so downstream tools that opt into the hint can
      branch on it without a schema change
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
        requested.metadata["page_promotion_warning"] = (
            f"User selected page {doc.sequence + 1} but per-page OCR isn't "
            f"wired in; processing whole parent file instead."
        )
    logger.warning(
        "files_tool: page %s (seq=%s) promoted to parent %s — "
        "tool will process the whole file. See #670 for per-page fan-out.",
        doc.id, doc.sequence, parent.id,
    )
    return requested


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
    input_ports=[],
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

            def _add(path: str, document: Document) -> None:
                if document.id in seen_ids:
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
                    return False
                ordered = sorted(page_children, key=lambda p: p.sequence or 0)
                for page in ordered:
                    _add(file_doc.path, page)
                return True

            def _expand_folder(folder: Document) -> None:
                """Recursively collect file descendants of a folder."""
                children = db.query(Document, parent_id=folder.id)
                for child in children:
                    if child.doc_type == DocType.folder:
                        _expand_folder(child)
                    elif child.path and not _expand_to_pages(child):
                        _add(child.path, child)

            for doc in docs:
                if doc.doc_type == DocType.folder:
                    _expand_folder(doc)
                    logger.info(
                        f"files_tool: expanded folder {doc.id} → {len(pairs)} entries so far"
                    )
                elif doc.path:
                    if not _expand_to_pages(doc):
                        _add(doc.path, doc)
                elif doc.parent_id:
                    # Page selected directly — emit just this page,
                    # using the parent's path as the file pointer.
                    resolved_parent = _resolve_page_to_parent(doc, db)
                    if resolved_parent is not None and resolved_parent.path:
                        _add(resolved_parent.path, doc)
                else:
                    logger.warning(
                        f"files_tool: doc {doc.id} type={doc.doc_type} "
                        "has no path and no parent — skipping"
                    )

            files = [path for path, _ in pairs]
            documents = [d.model_dump() for _, d in pairs]
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
            resolved: dict[str, Document] = {}
            for doc in docs:
                if doc.path:
                    resolved[doc.path] = doc
                elif doc.parent_id:
                    resolved_parent = _resolve_page_to_parent(doc, db)
                    if resolved_parent is not None and resolved_parent.path:
                        resolved[resolved_parent.path] = resolved_parent
            files = list(resolved.keys())
            documents = [d.model_dump() for d in resolved.values()]
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

        # Get all files in collection
        files = _get_files_in_folder(
            db=db,
            folder_id=collection_id,
            recursive=recursive,
            file_types=file_types,
            status_filter=status_filter,
            limit=limit,
        )

        # Extract file paths and document data
        file_paths = [doc.path for doc in files if doc.path]
        doc_data = [doc.model_dump() for doc in files]

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
    input_ports=[],
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

        # Get files
        files = _get_files_in_folder(
            db=db,
            folder_id=folder_id,
            recursive=include_subfolders,
            file_types=file_types,
            limit=limit,
        )

        # Get direct subfolders (for hierarchical processing)
        subfolders = db.query(Document, parent_id=folder_id, doc_type=DocType.folder)
        subfolder_ids = [sf.id for sf in subfolders]

        file_paths = [doc.path for doc in files if doc.path]
        doc_data = [doc.model_dump() for doc in files]

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
    input_ports=[],
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
        return {
            "files": [],
            "documents": [],
            "count": 0,
            "error": "No search query provided",
        }

    search_type = inputs.get("search_type", "hybrid")
    collection_id = inputs.get("collection_id")
    file_types = inputs.get("file_types", [])
    status_filter = inputs.get("status_filter", "all")
    min_score = inputs.get("min_score", 0.0)
    limit = inputs.get("limit", 100)

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

        # Run search
        results, total, stats = db.search(
            query=query,
            limit=limit,
            min_score=min_score,
            search_type=search_type,
            filters=filters,
        )

        # Get full documents for each result
        files = []
        doc_data = []

        for result in results:
            doc = db.get(Document, result.document_id)
            if doc:
                # If collection_id filter, check ancestry
                if collection_id:
                    if not _is_descendant_of(db, doc, collection_id):
                        continue

                if doc.path:
                    files.append(doc.path)

                doc_dict = doc.model_dump()
                doc_dict["search_score"] = result.score
                doc_dict["highlights"] = result.highlights
                doc_data.append(doc_dict)

        logger.info(f"Search '{query}': found {len(files)} files")

        return {
            "files": files,
            "documents": doc_data,
            "count": len(files),
        }

    except Exception as e:
        logger.error(f"Search tool failed: {e}")
        return {"files": [], "documents": [], "count": 0, "error": str(e)}


# =============================================================================
# Helper Functions
# =============================================================================


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
