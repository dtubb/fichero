"""Tests for action library routes.

Actions are reusable workflow building blocks (builtin + custom).
SwiftUI uses these routes to populate the action palette in the workflow editor.
"""



class TestListActions:
    def test_list_returns_envelope(self, client):
        r = client.get("/api/actions")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "items" in data
        assert "count" in data

    def test_list_includes_builtin_actions(self, client):
        r = client.get("/api/actions")
        assert r.status_code == 200
        # Builtin actions are always populated from the action store
        data = r.json()
        assert isinstance(data, dict)
        assert "items" in data

    def test_list_builtin_only(self, client):
        r = client.get("/api/actions/builtin")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "items" in data
        assert all(a["is_builtin"] for a in data["items"])

    def test_list_custom_only(self, client):
        r = client.get("/api/actions/custom")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "items" in data
        assert all(not a["is_builtin"] for a in data["items"])

    def test_list_recent(self, client):
        r = client.get("/api/actions/recent")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "items" in data

    def test_list_popular(self, client):
        r = client.get("/api/actions/popular")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "items" in data


class TestCategories:
    def test_categories_returns_dict_with_list(self, client):
        r = client.get("/api/actions/categories")
        assert r.status_code == 200
        data = r.json()
        assert "categories" in data
        assert isinstance(data["categories"], list)

    def test_filter_by_category(self, client):
        cats = client.get("/api/actions/categories").json()["categories"]
        if cats:
            r = client.get(f"/api/actions/category/{cats[0]}")
            assert r.status_code == 200
            data = r.json()
            assert isinstance(data, dict)
            assert "items" in data


class TestSearchActions:
    def test_search_returns_envelope(self, client):
        r = client.get("/api/actions/search?q=test")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "items" in data

    def test_search_empty_query_returns_all(self, client):
        r = client.get("/api/actions/search?q=")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "items" in data


class TestGetAction:
    def test_get_builtin_action_by_id(self, client):
        # Get a builtin action ID from the list first
        builtins_response = client.get("/api/actions/builtin").json()
        if builtins_response.get("items"):
            action_id = builtins_response["items"][0]["id"]
            r = client.get(f"/api/actions/{action_id}")
            assert r.status_code == 200
            assert r.json()["id"] == action_id

    def test_get_nonexistent_action_returns_404(self, client):
        r = client.get("/api/actions/definitely-does-not-exist-xyz123")
        assert r.status_code == 404


class TestCreateAction:
    def test_create_custom_action(self, client):
        payload = {
            "name": "My Custom Action",
            "description": "Does something useful",
            "category": "custom",
            "tags": ["test"],
            "icon": "star.fill",
            "node_template": {"tool": "transcribe"},
            "nodes": [],
            "edges": [],
            "author": "test-user",
        }
        r = client.post("/api/actions", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "My Custom Action"
        assert not data["is_builtin"]

    def test_created_action_appears_in_custom_list(self, client):
        payload = {
            "name": "Listed Action",
            "description": "",
            "category": "custom",
            "tags": [],
            "icon": "square",
            "node_template": {},
            "nodes": [],
            "edges": [],
            "author": "",
        }
        created = client.post("/api/actions", json=payload).json()
        custom_list_response = client.get("/api/actions/custom").json()
        ids = [a["id"] for a in custom_list_response["items"]]
        assert created["id"] in ids


class TestUpdateAction:
    def test_update_custom_action_name(self, client):
        payload = {
            "name": "Original Name",
            "description": "",
            "category": "custom",
            "tags": [],
            "icon": "square",
            "node_template": {},
            "nodes": [],
            "edges": [],
            "author": "",
        }
        created = client.post("/api/actions", json=payload).json()
        update = {**payload, "name": "Updated Name"}
        r = client.put(f"/api/actions/{created['id']}", json=update)
        assert r.status_code == 200
        assert r.json()["name"] == "Updated Name"

    def test_update_nonexistent_action_returns_404(self, client):
        r = client.put("/api/actions/no-such-id", json={
            "name": "x", "description": "", "category": "custom",
            "tags": [], "icon": "square", "node_template": {},
            "nodes": [], "edges": [], "author": "",
        })
        assert r.status_code == 404


class TestDeleteAction:
    def test_delete_custom_action(self, client):
        payload = {
            "name": "To Delete",
            "description": "",
            "category": "custom",
            "tags": [],
            "icon": "trash",
            "node_template": {},
            "nodes": [],
            "edges": [],
            "author": "",
        }
        created = client.post("/api/actions", json=payload).json()
        r = client.delete(f"/api/actions/{created['id']}")
        assert r.status_code == 200

    def test_delete_removes_from_list(self, client):
        payload = {
            "name": "Delete Me",
            "description": "",
            "category": "custom",
            "tags": [],
            "icon": "trash",
            "node_template": {},
            "nodes": [],
            "edges": [],
            "author": "",
        }
        created = client.post("/api/actions", json=payload).json()
        client.delete(f"/api/actions/{created['id']}")
        r = client.get(f"/api/actions/{created['id']}")
        assert r.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        r = client.delete("/api/actions/no-such-id")
        assert r.status_code == 404


class TestRecordActionUse:
    def test_record_use_increments_counter(self, client):
        payload = {
            "name": "Usable Action",
            "description": "",
            "category": "custom",
            "tags": [],
            "icon": "square",
            "node_template": {},
            "nodes": [],
            "edges": [],
            "author": "",
        }
        created = client.post("/api/actions", json=payload).json()
        initial_count = created["use_count"]
        r = client.post(f"/api/actions/{created['id']}/use")
        assert r.status_code == 200
        r2 = client.get(f"/api/actions/{created['id']}")
        assert r2.json()["use_count"] == initial_count + 1


class TestExportImportAction:
    def test_export_action(self, client):
        import json as _json
        payload = {
            "name": "Exportable",
            "description": "desc",
            "category": "custom",
            "tags": ["export"],
            "icon": "square",
            "node_template": {"tool": "test"},
            "nodes": [],
            "edges": [],
            "author": "tester",
        }
        created = client.post("/api/actions", json=payload).json()
        r = client.get(f"/api/actions/{created['id']}/export")
        assert r.status_code == 200
        # Export returns {"json_data": "<serialized string>"}
        exported_str = r.json()["json_data"]
        exported = _json.loads(exported_str)
        assert exported["name"] == "Exportable"

    def test_import_action(self, client):
        import json as _json
        action_data = {
            "id": "import-test-id",
            "name": "Importable",
            "description": "imported",
            "category": "custom",
            "tags": [],
            "icon": "square",
            "node_template": {},
            "nodes": [],
            "edges": [],
            "is_builtin": False,
            "is_composite": False,
            "author": "",
            "use_count": 0,
            "last_used_at": None,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }
        r = client.post("/api/actions/import", json={
            "json_data": _json.dumps(action_data),
            "new_id": True,
        })
        assert r.status_code == 200
        assert r.json()["name"] == "Importable"
