"""A folder's children, listed for an agent, carry no bulk (#5695), tested to the spec:
`openapi.mcp.answers-fit-an-agent` (docs/contributor_manual/specs/harness/surfaces-from-openapi.md).

WHY: the overnight MCP walk (2026-10-11): `documents_get_children(limit=8)` answered ~60 KB, every page carrying
its transcription twice (page_content and metadata.transcription) and its workflow runs; 92 pages, ~700 KB.
"""

from __future__ import annotations

from fichero_server.models import DocType, Document, FileType

TEXT = "una línea leída de la página " * 200  # ~6 KB, as a read page's text is


def _folder(db, n: int = 8) -> Document:
    folder = Document(name="CACIQUES", doc_type=DocType.folder)
    db.save(folder)
    for i in range(1, n + 1):
        db.save(Document(name=f"{i}_Hoja.jpg", doc_type=DocType.file, file_type=FileType.image, parent_id=folder.id,
                         page_content=TEXT, metadata={"transcription": TEXT, "width": 600},
                         workflow_runs=[{"run_id": f"r{i}", "workflow": "w", "log": TEXT}]))
    return folder


def test_an_agents_list_of_children_is_lean_and_the_apps_is_whole(db, client):
    folder = _folder(db)

    lean = client.get(f"/api/documents/{folder.id}/children", params={"summary": True})
    assert lean.status_code == 200, lean.text
    assert len(lean.content) < 16_000, len(lean.content)
    items = lean.json()["items"]
    assert [i["name"] for i in items] == [f"{n}_Hoja.jpg" for n in range(1, 9)]
    assert all(i.get("page_content") is None and not i.get("workflow_runs") for i in items)
    assert all(i["metadata"] == {"width": 600} for i in items)

    whole = client.get(f"/api/documents/{folder.id}/children").json()["items"]
    assert all(i["page_content"] == TEXT for i in whole)  # the app, calling with no parameters, keeps it all

    listed = client.get("/api/documents", params={"parent_id": folder.id, "summary": True}).json()["items"]
    assert all(i.get("page_content") is None for i in listed)


def test_an_agents_tool_asks_for_the_lean_answer_by_default(client):
    spec = client.get("/openapi.json").json()
    for path in ("/api/documents/{doc_id}/children", "/api/documents"):
        assert spec["paths"][path]["get"]["x-fichero-agent-defaults"]["summary"] is True, path
