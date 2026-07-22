"""Tests for projects / research workspace routes (#918)."""

from fichero.models.knowledge import Project, ProjectInclusion, ProjectStatus


class TestProjectsCRUD:
    def test_create_and_get_project(self, client):
        response = client.post(
            "/api/projects",
            json={
                "name": "Chapter 3",
                "description": "Argument workspace",
                "color": "#336699",
                "icon": "book",
                "status": "active",
                "members": ["daniel"],
            },
        )
        assert response.status_code == 200
        project = response.json()
        assert project["name"] == "Chapter 3"
        assert project["status"] == "active"

        get_response = client.get(f"/api/projects/{project['id']}")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == project["id"]

    def test_list_projects_returns_envelope(self, client, db):
        db.save(Project(name="A", status=ProjectStatus.active))
        db.save(Project(name="B", status=ProjectStatus.archived))

        response = client.get("/api/projects")
        assert response.status_code == 200
        payload = response.json()
        assert "items" in payload
        assert "count" in payload
        assert payload["count"] == 2

    def test_patch_project_updates_fields(self, client, db):
        project = Project(name="Old", status=ProjectStatus.active)
        db.save(project)

        response = client.patch(
            f"/api/projects/{project.id}",
            json={"name": "New", "status": "archived"},
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["name"] == "New"
        assert updated["status"] == "archived"

    def test_delete_project_cascades_inclusions(self, client, db):
        project = Project(name="Workspace")
        db.save(project)
        inclusion = ProjectInclusion(
            project_id=project.id,
            target_id="doc-1",
            target_type="document",
        )
        db.save(inclusion)

        response = client.delete(f"/api/projects/{project.id}")
        assert response.status_code == 204
        assert db.get(Project, project.id) is None
        assert db.get(ProjectInclusion, inclusion.id) is None


class TestProjectInclusions:
    def test_include_item_and_list_items(self, client, db):
        project = Project(name="Workspace")
        db.save(project)

        include_response = client.post(
            f"/api/projects/{project.id}/include",
            json={
                "target_id": "claim-1",
                "target_type": "claim",
                "role": "argument",
                "notes": "central claim",
            },
        )
        assert include_response.status_code == 200
        inclusion = include_response.json()
        assert inclusion["project_id"] == project.id
        assert inclusion["target_type"] == "claim"

        list_response = client.get(f"/api/projects/{project.id}/items")
        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["count"] == 1
        assert payload["items"][0]["id"] == inclusion["id"]

    def test_include_item_deduplicates_same_target(self, client, db):
        project = Project(name="Workspace")
        db.save(project)

        first = client.post(
            f"/api/projects/{project.id}/include",
            json={"target_id": "entity-1", "target_type": "entity"},
        )
        second = client.post(
            f"/api/projects/{project.id}/include",
            json={"target_id": "entity-1", "target_type": "entity"},
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]

    def test_include_item_rejects_unknown_target_type(self, client, db):
        project = Project(name="Workspace")
        db.save(project)

        response = client.post(
            f"/api/projects/{project.id}/include",
            json={"target_id": "x", "target_type": "banana"},
        )
        assert response.status_code == 400
        assert "target_type must be one of" in response.json()["detail"]

    def test_items_filter_by_target_type(self, client, db):
        project = Project(name="Workspace")
        db.save(project)
        db.save(ProjectInclusion(project_id=project.id, target_id="d1", target_type="document"))
        db.save(ProjectInclusion(project_id=project.id, target_id="c1", target_type="claim"))

        response = client.get(f"/api/projects/{project.id}/items?target_type=claim")
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        assert payload["items"][0]["target_type"] == "claim"

    def test_membership_lists_projects_for_target(self, client, db):
        chapter = Project(name="Chapter 3")
        review = Project(name="JLAR Review")
        db.save(chapter)
        db.save(review)
        db.save(ProjectInclusion(project_id=chapter.id, target_id="entity-42", target_type="entity"))
        db.save(ProjectInclusion(project_id=review.id, target_id="entity-42", target_type="entity"))

        response = client.get("/api/projects/membership/entity-42?target_type=entity")
        assert response.status_code == 200
        payload = response.json()
        names = {item["name"] for item in payload["items"]}
        assert names == {"Chapter 3", "JLAR Review"}
