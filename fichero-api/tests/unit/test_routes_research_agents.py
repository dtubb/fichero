"""Tests for research agent routes.

Research agents manage structured research workflows: projects contain plans,
plans contain tasks, tasks contain steps. Routes live at /api/research/...
(router has no prefix, mounted at "/api/research").
"""

import pytest

from fichero.research_models import (
    ProjectStatus,
    ResearchPlan,
    ResearchProject,
    ResearchTask,
    TaskStatus,
)


BASE = "/api/research"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(proj_id: str = "proj-1", name: str = "My Project") -> ResearchProject:
    return ResearchProject(id=proj_id, name=name)


def _make_plan(plan_id: str = "plan-1", project_id: str = "proj-1") -> ResearchPlan:
    return ResearchPlan(id=plan_id, project_id=project_id, name="Phase 1")


def _make_task(task_id: str = "task-1", plan_id: str = "plan-1") -> ResearchTask:
    return ResearchTask(id=task_id, plan_id=plan_id, name="Search literature")


# ---------------------------------------------------------------------------
# POST /api/research/projects
# ---------------------------------------------------------------------------


class TestCreateProject:
    def test_create_project(self, client):
        r = client.post(f"{BASE}/projects", json={
            "name": "History of Science Project",
            "description": "Survey primary sources.",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "History of Science Project"
        assert "id" in data

    def test_create_project_minimal(self, client):
        r = client.post(f"{BASE}/projects", json={"name": "Minimal"})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/research/projects
# ---------------------------------------------------------------------------


class TestListProjects:
    def test_empty_list(self, client):
        r = client.get(f"{BASE}/projects")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_projects(self, client, db):
        db.save(_make_project("p-1", "Project Alpha"))
        db.save(_make_project("p-2", "Project Beta"))

        r = client.get(f"{BASE}/projects")
        assert r.status_code == 200
        assert len(r.json()) == 2


# ---------------------------------------------------------------------------
# GET /api/research/projects/{id}
# ---------------------------------------------------------------------------


class TestGetProject:
    def test_get_existing(self, client, db):
        db.save(_make_project("p-get", "Named Project"))

        r = client.get(f"{BASE}/projects/p-get")
        assert r.status_code == 200
        assert r.json()["name"] == "Named Project"

    def test_get_missing_returns_404(self, client):
        r = client.get(f"{BASE}/projects/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/research/projects/{id}
# ---------------------------------------------------------------------------


class TestUpdateProject:
    def test_update_project_name(self, client, db):
        db.save(_make_project("p-upd", "Old Name"))

        r = client.patch(f"{BASE}/projects/p-upd", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_update_missing_returns_404(self, client):
        r = client.patch(f"{BASE}/projects/no-such", json={"name": "X"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/research/projects/{id}
# ---------------------------------------------------------------------------


class TestDeleteProject:
    def test_delete_project(self, client, db):
        db.save(_make_project("p-del", "Deletable"))

        r = client.delete(f"{BASE}/projects/p-del")
        assert r.status_code == 200

    def test_delete_missing_returns_404(self, client):
        r = client.delete(f"{BASE}/projects/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/research/plans
# ---------------------------------------------------------------------------


class TestCreatePlan:
    def test_create_plan(self, client, db):
        db.save(_make_project("proj-p"))

        r = client.post(f"{BASE}/plans", json={
            "project_id": "proj-p",
            "name": "Literature Review",
            "description": "Comprehensive source survey.",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["project_id"] == "proj-p"
        assert data["name"] == "Literature Review"

    def test_create_plan_without_existing_project_still_succeeds(self, client):
        # Plan creation does not validate project existence (FK-free store)
        r = client.post(f"{BASE}/plans", json={
            "project_id": "no-such-project",
            "name": "Orphan Plan",
        })
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/research/projects/{id}/plans
# ---------------------------------------------------------------------------


class TestListProjectPlans:
    def test_empty_plans(self, client, db):
        db.save(_make_project("proj-noplan"))

        r = client.get(f"{BASE}/projects/proj-noplan/plans")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_plans(self, client, db):
        db.save(_make_project("proj-pl"))
        db.save(_make_plan("pl-1", "proj-pl"))
        db.save(_make_plan("pl-2", "proj-pl"))

        r = client.get(f"{BASE}/projects/proj-pl/plans")
        assert r.status_code == 200
        assert len(r.json()) == 2


# ---------------------------------------------------------------------------
# POST /api/research/tasks
# ---------------------------------------------------------------------------


class TestCreateTask:
    def test_create_task(self, client, db):
        db.save(_make_project("proj-t"))
        db.save(_make_plan("plan-t", "proj-t"))

        r = client.post(f"{BASE}/tasks", json={
            "plan_id": "plan-t",
            "name": "Search primary sources",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["plan_id"] == "plan-t"

    def test_create_task_without_existing_plan_still_succeeds(self, client):
        # Task creation does not validate plan existence (FK-free store)
        r = client.post(f"{BASE}/tasks", json={
            "plan_id": "no-such-plan",
            "name": "Orphan Task",
        })
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/research/plans/{id}/tasks
# ---------------------------------------------------------------------------


class TestListPlanTasks:
    def test_returns_tasks(self, client, db):
        db.save(_make_project("proj-lt"))
        db.save(_make_plan("plan-lt", "proj-lt"))
        db.save(_make_task("t-1", "plan-lt"))
        db.save(_make_task("t-2", "plan-lt"))

        r = client.get(f"{BASE}/plans/plan-lt/tasks")
        assert r.status_code == 200
        assert len(r.json()) == 2
