"""Tests for workspace-as-folder view availability."""

from fichero_server.models import DocType, Document, FileType


def _view_by_id(payload: dict, view_id: str) -> dict:
    return {view["id"]: view for view in payload["views"]}[view_id]


class TestWorkspaceFolderViews:
    def test_workspace_folder_views_include_curated_items_and_descendants(self, client, db):
        folder = Document(
            id="folder-1",
            name="Workspace",
            doc_type=DocType.folder,
            is_workspace=True,
            curated_items=[
                {
                    "type": "quote",
                    "text": "A curated line",
                    "url": "https://example.test/source",
                }
            ],
        )
        child = Document(
            id="child-1",
            parent_id=folder.id,
            name="Source.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path="/tmp/source.pdf",
        )
        page = Document(
            id="page-1",
            parent_id=child.id,
            name="Page 1",
            doc_type=DocType.page,
            sequence=1,
        )
        db.save(folder)
        db.save(child)
        db.save(page)

        response = client.get(f"/api/folders/{folder.id}/views")

        assert response.status_code == 200
        payload = response.json()
        assert payload["folder_id"] == folder.id
        assert payload["is_workspace"] is True
        assert payload["curated_item_count"] == 1
        assert payload["child_count"] == 2
        assert _view_by_id(payload, "list")["item_count"] == 3
        assert _view_by_id(payload, "list")["populated"] is True
        assert _view_by_id(payload, "webkit")["item_count"] == 2
        assert _view_by_id(payload, "realitykit")["populated"] is True

    def test_folder_map_view_populated_from_descendant_geo_metadata(self, client, db):
        folder = Document(id="folder-map", name="Map folder", doc_type=DocType.folder)
        child = Document(
            id="geo-child",
            parent_id=folder.id,
            name="Geo note",
            doc_type=DocType.file,
            metadata={"latitude": 45.95, "longitude": -66.64},
        )
        db.save(folder)
        db.save(child)

        response = client.get(f"/api/folders/{folder.id}/views")

        assert response.status_code == 200
        payload = response.json()
        assert _view_by_id(payload, "map")["populated"] is True
        assert _view_by_id(payload, "map")["item_count"] == 1

    def test_non_folder_document_rejected_for_folder_views(self, client, db):
        doc = Document(id="not-folder", name="Loose file", doc_type=DocType.file)
        db.save(doc)

        response = client.get(f"/api/folders/{doc.id}/views")

        assert response.status_code == 400
        assert response.json()["detail"] == "Document is not a folder"
