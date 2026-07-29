"""Organize same-document clusters into subfolders via the action registry."""

from __future__ import annotations

from typing import Any

# NOTE: fichero_server.api.routes.documents is imported inside the tool body, not
# here (#3950). A tool importing an API ROUTE is a layering inversion, and it
# created a second import cycle:
#     tools/__init__ -> this module -> api.routes.documents
#     -> api.main -> api.routes.chat -> api.routes.documents (half-initialised)
# which made `import fichero_server.workflows.tools` impossible standalone and so
# blocked any background warm-up. The route import is a side effect that
# registers the document.* actions — those are needed when this tool RUNS,
# which is precisely when the deferred import fires.
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.db import db_manager
from fichero_server.models import DocType, Document
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.similarity import SameDocumentCluster
from fichero_server.workflows.types import DataType, PortDef, State


def _cluster_folder_name(cluster_index: int) -> str:
    return f"Same Document {cluster_index}"


def _existing_cluster_folder(db, parent_id: str, name: str) -> Document | None:
    for child in db.query(Document, parent_id=parent_id, doc_type=DocType.folder):
        if child.name == name:
            return child
    return None


@register_tool(
    name="organize_same_documents",
    display_name="Organize Same Documents",
    description="Create one subfolder per duplicate cluster and move members into it via the audited action registry",
    category="utility",
    icon="folder.badge.plus",
    color="teal",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="clusters",
            name="Clusters",
            port_type="input",
            data_type=DataType.JSON,
            required=True,
            description="Typed same-document clusters from the similarity tool.",
        )
    ],
    output_ports=[
        PortDef(
            id="summary",
            name="Summary",
            port_type="output",
            data_type=DataType.JSON,
            description="Created folder and move counts.",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of duplicate clusters organized.",
        ),
    ],
    sort_order=30,
)
async def organize_same_documents(
    inputs: dict[str, Any],
    state: State,
    llm_config,
) -> dict[str, Any]:
    """Create one folder per duplicate cluster and move member docs into it."""
    del llm_config

    library_path = state.get("library_path", "")
    if not library_path:
        raise ValueError("Organize same documents requires a library path")

    selected_doc_ids = list(state.get("selected_doc_ids") or [])
    if len(selected_doc_ids) != 1:
        raise ValueError("Organize same documents requires exactly one selected folder")

    db = db_manager.get_database(library_path)
    target = db.get(Document, selected_doc_ids[0])
    if target is None or target.doc_type != DocType.folder:
        raise ValueError("Organize same documents requires a folder target")

    raw_clusters = list(inputs.get("clusters") or [])
    if not raw_clusters:
        raise ValueError("Organize same documents requires clusters")

    # Imported here rather than at module scope (#3950). The bare module import
    # is load-bearing: it registers the document.* actions that registry.invoke
    # below depends on. Keep both.
    import fichero_server.api.routes.documents  # noqa: F401  (registers document.* actions)
    from fichero_server.api.routes.documents import DocumentCreate

    ctx = ActionContext(
        actor="workflow",
        run_id=state.get("task_id"),
        library_path=library_path,
    )
    summary = {
        "clusters_examined": 0,
        "clusters_organized": 0,
        "clusters_skipped": 0,
        "folders_created": 0,
        "documents_moved": 0,
        "folder_ids": [],
    }

    for index, raw_cluster in enumerate(raw_clusters, start=1):
        cluster = SameDocumentCluster.model_validate(raw_cluster)
        summary["clusters_examined"] += 1
        if len(cluster.member_document_ids) <= 1:
            summary["clusters_skipped"] += 1
            continue

        folder_name = _cluster_folder_name(index)
        folder = _existing_cluster_folder(db, target.id, folder_name)
        if folder is None:
            created = registry.invoke(
                db,
                "document.create",
                DocumentCreate(
                    name=folder_name,
                    parent_id=target.id,
                    doc_type=DocType.folder,
                ).model_dump(mode="json"),
                ctx,
            )
            folder = db.get(Document, created.result["id"])
            if folder is None or folder.parent_id != target.id or folder.doc_type != DocType.folder:
                raise ValueError(f"Cluster folder '{folder_name}' was not created correctly")
            summary["folders_created"] += 1

        summary["folder_ids"].append(folder.id)
        summary["clusters_organized"] += 1
        for doc_id in cluster.member_document_ids:
            document = db.get(Document, doc_id)
            if document is None:
                raise ValueError(f"Cluster member document not found: {doc_id}")
            if document.parent_id == folder.id:
                continue
            registry.invoke(
                db,
                "document.move",
                {"doc_id": doc_id, "parent_id": folder.id},
                ctx,
            )
            moved = db.get(Document, doc_id)
            if moved is None or moved.parent_id != folder.id:
                raise ValueError(f"Document move did not persist for {doc_id}")
            summary["documents_moved"] += 1

    return {"summary": summary, "count": summary["clusters_organized"]}
