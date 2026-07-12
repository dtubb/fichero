"""Scoped entity-reconciliation candidate route coverage (#3318)."""


def test_folder_scope_requires_folder_id(client):
    response = client.get("/api/kg/entity-curation/candidates?scope=folder")

    assert response.status_code == 422
    assert "folder_id is required" in response.json()["detail"]


def test_library_scope_is_the_default(client):
    response = client.get("/api/kg/entity-curation/candidates")

    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}
