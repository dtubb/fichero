"""Tests for the Sources API routes (issue #364)."""



def test_list_sources_empty(client, db):
    """Test listing sources when none exist."""
    response = client.get("/api/sources")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["items"] == []
    assert data["count"] == 0


def test_create_source(client, db):
    """Test creating a new source."""
    source_data = {
        "title": "Test Source Document",
        "file_path": "/test/path/to/source.pdf",
        "document_type": "source",
        "metadata": {"isbn": "1234567890"},
    }
    response = client.post("/api/sources", json=source_data)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Source Document"
    assert data["file_path"] == "/test/path/to/source.pdf"
    assert data["document_type"] == "source"
    assert data["metadata"] == {"isbn": "1234567890"}
    assert "id" in data


def test_get_source(client, db):
    """Test getting a specific source."""
    # Create a source first
    create_response = client.post(
        "/api/sources",
        json={
            "title": "Get Test Source",
            "file_path": "/test/get/source.pdf",
            "document_type": "source",
        },
    )
    assert create_response.status_code == 200
    source_id = create_response.json()["id"]

    # Get the source
    response = client.get(f"/api/sources/{source_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Get Test Source"


def test_get_source_not_found(client, db):
    """Test getting a non-existent source returns 404."""
    response = client.get("/api/sources/non-existent-id")
    assert response.status_code == 404


def test_update_source(client, db):
    """Test updating an existing source."""
    # Create a source first
    create_response = client.post(
        "/api/sources",
        json={
            "title": "Original Title",
            "file_path": "/original/path.pdf",
            "document_type": "source",
        },
    )
    source_id = create_response.json()["id"]

    # Update the source
    update_response = client.put(
        f"/api/sources/{source_id}",
        json={
            "title": "Updated Title",
            "file_path": "/updated/path.pdf",
            "document_type": "source",
            "metadata": {"updated": True},
        },
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["title"] == "Updated Title"
    assert data["metadata"] == {"updated": True}


def test_delete_source(client, db):
    """Test deleting a source."""
    # Create a source first
    create_response = client.post(
        "/api/sources",
        json={
            "title": "Delete Me",
            "file_path": "/delete/me.pdf",
            "document_type": "source",
        },
    )
    source_id = create_response.json()["id"]

    # Delete the source
    response = client.delete(f"/api/sources/{source_id}")
    assert response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/api/sources/{source_id}")
    assert get_response.status_code == 404


def test_list_sources_includes_created(client, db):
    """Test that created sources appear in list."""
    client.post(
        "/api/sources",
        json={
            "title": "List Test Source 1",
            "file_path": "/list/test1.pdf",
            "document_type": "source",
        },
    )
    client.post(
        "/api/sources",
        json={
            "title": "List Test Source 2",
            "file_path": "/list/test2.pdf",
            "document_type": "source",
        },
    )

    response = client.get("/api/sources")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    titles = [s["title"] for s in data["items"]]
    assert "List Test Source 1" in titles
    assert "List Test Source 2" in titles
