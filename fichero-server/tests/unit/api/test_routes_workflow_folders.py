"""GET /api/workflows/folders — how verb families PRESENT, served not hard-coded.

The capability bar draws its verbs in the order work actually happens
(prepare the image, find the regions, read them, clean, translate, extract,
catalogue). That order is data, and until 2026-08-28 it lived as a literal
list in Swift because preset `sort_order` could not supply it — every shipped
preset carries 0. Serving it makes it editable later without a client build.
"""

from __future__ import annotations


class TestWorkflowFolders:
    def test_serves_the_working_route_in_order(self, client):
        body = client.get("/api/workflows/folders").json()
        items = body["items"]

        assert body["count"] == len(items) and items
        orders = [f["sort_order"] for f in items]
        assert orders == sorted(orders), "served list must already be in route order"

        paths = [f["path"] for f in items]
        # The route's spine: you find the regions before you read them, and you
        # read them before you catalogue them.
        assert paths.index("/Detect Regions") < paths.index("/Transcribe")
        assert paths.index("/Transcribe") < paths.index("/Catalogue")

    def test_every_folder_carries_a_glyph_and_a_name(self, client):
        for folder in client.get("/api/workflows/folders").json()["items"]:
            assert folder["icon"], folder["path"]
            assert folder["display_name"], folder["path"]

    def test_folders_is_not_swallowed_by_the_workflow_id_route(self, client):
        # /folders is declared BEFORE /{workflow_id}; reversing that would make
        # this endpoint 404 as "workflow not found", silently, at run time.
        response = client.get("/api/workflows/folders")
        assert response.status_code == 200
        assert "items" in response.json()
