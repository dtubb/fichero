from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image
from tests.integration._seedlib import seed

from fichero.db import db_manager
from fichero.models import Artifact, DocType, Document, FileType, Workflow
from fichero.workflows.builder import build_graph
from fichero.workflows.default_workflows import _load_preset_files
from fichero.workflows.runtime import build_initial_state, to_workflow_def

import fichero.workflows.tools  # noqa: F401


def test_group_same_documents_preset_clusters_known_duplicates(tmp_path: Path):
    library_path, folder_id, docs = _seed_duplicate_folder(tmp_path)
    workflow = _load_workflow("Group Same Documents")

    response = (
        "{"
        '"overall_similarity":0.87,'
        '"aspect_scores":[{"aspect":"content","score":97},{"aspect":"composition","score":90}],'
        '"most_similar":"content",'
        '"most_different":"style",'
        '"notes":"doc-a variants cluster together; others stay separate.",'
        '"same_document_clusters":['
        '{"cluster_id":"cluster-a","member_indexes":[0,1],"similarity_score":0.98},'
        '{"cluster_id":"cluster-b","member_indexes":[2],"similarity_score":0.41},'
        '{"cluster_id":"cluster-c","member_indexes":[3],"similarity_score":0.38}'
        "]}"
    )

    with patch(
        "fichero.workflows.tools.similarity.vision",
        new=AsyncMock(return_value=response),
    ):
        result = asyncio.run(
            build_graph(workflow, skip_cache=True).ainvoke(
                _workflow_state(library_path, folder_id, task_id="group-same-docs")
            )
        )

    assert not result.get("error")
    output = result["outputs"]["similarity"]["value"]
    clusters = output["same_document_clusters"]
    assert clusters[0]["member_document_ids"] == [docs[0].id, docs[1].id]
    assert [cluster["member_document_ids"] for cluster in clusters[1:]] == [
        [docs[2].id],
        [docs[3].id],
    ]

    db = db_manager.get_database(library_path)
    artifacts = db.query(Artifact, document_id=folder_id, artifact_type="similarity")
    assert len(artifacts) == 1
    assert artifacts[0].data == output


def _seed_duplicate_folder(tmp_path: Path) -> tuple[Path, str, list[Document]]:
    library_path = tmp_path / "same-document-clusters.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    folder = Document(
        id="same-doc-folder",
        name="Same doc folder",
        doc_type=DocType.folder,
    )
    db.save(folder)

    docs: list[Document] = []
    for index, name in enumerate(
        ["doc-a-scan.png", "doc-a-photo.png", "doc-b.png", "doc-c.png"], start=1
    ):
        path = tmp_path / name
        Image.new("RGB", (24, 24), (255, 255, 255)).save(path, format="PNG")
        doc = Document(
            id=f"same-doc-{index}",
            parent_id=folder.id,
            name=name,
            path=str(path),
            doc_type=DocType.file,
            file_type=FileType.image,
            page_content=f"fixture text for {name}",
        )
        db.save(doc)
        docs.append(doc)

    return library_path, folder.id, docs


def _load_workflow(name: str):
    preset = next(p for p in _load_preset_files() if p["name"] == name)
    return to_workflow_def(
        Workflow(
            id=f"default-{name.lower().replace(' ', '-')}-regression-harness",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


def _workflow_state(library_path: Path, selected_doc_id: str, *, task_id: str) -> dict:
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = "default-group-same-documents-regression-harness"
    state["task_id"] = task_id
    return state
