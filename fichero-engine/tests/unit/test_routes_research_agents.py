"""Tests for research agent routes.

Research agents manage structured research workflows: projects contain plans,
plans contain tasks, tasks contain steps. Routes live at /api/research/...
(router has no prefix, mounted at "/api/research").
"""

import pytest
from fastapi import HTTPException

from fichero.knowledge_models import ClassificationDimension, ClassificationValue
from fichero.models import DocType, Document
from fichero.node_prototypes import PrototypeResolutionError
from fichero.research_models import (
    ResearchPlan,
    ResearchProject,
    ResearchStep,
    ResearchTask,
    StepTool,
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


def _make_step(step_id: str = "step-1", task_id: str = "task-1") -> ResearchStep:
    return ResearchStep(id=step_id, task_id=task_id, tool=StepTool.web_search, label="Search")


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
        assert r.json() == {"items": [], "count": 0}

    @pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
    def test_returns_projects(self, client, db):
        db.save(_make_project("p-1", "Project Alpha"))
        db.save(_make_project("p-2", "Project Beta"))

        r = client.get(f"{BASE}/projects")
        assert r.status_code == 200
        assert len(r.json()["items"]["items"]) == 2


# ---------------------------------------------------------------------------
# GET /api/research/projects/{id}
# ---------------------------------------------------------------------------


class TestGetProject:
    @pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
    def test_get_existing(self, client, db):
        db.save(_make_project("p-get", "Named Project"))

        r = client.get(f"{BASE}/projects/p-get")
        assert r.status_code == 200
        assert r.json()["items"]["name"] == "Named Project"

    def test_get_missing_returns_404(self, client):
        r = client.get(f"{BASE}/projects/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/research/projects/{id}
# ---------------------------------------------------------------------------


class TestUpdateProject:
    @pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
    def test_update_project_name(self, client, db):
        db.save(_make_project("p-upd", "Old Name"))

        r = client.patch(f"{BASE}/projects/p-upd", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["items"]["name"] == "New Name"

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
        assert r.json() == {"items": [], "count": 0}

    @pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
    def test_returns_plans(self, client, db):
        db.save(_make_project("proj-pl"))
        db.save(_make_plan("pl-1", "proj-pl"))
        db.save(_make_plan("pl-2", "proj-pl"))

        r = client.get(f"{BASE}/projects/proj-pl/plans")
        assert r.status_code == 200
        assert len(r.json()["items"]["items"]) == 2


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
    @pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
    def test_returns_tasks(self, client, db):
        db.save(_make_project("proj-lt"))
        db.save(_make_plan("plan-lt", "proj-lt"))
        db.save(_make_task("t-1", "plan-lt"))
        db.save(_make_task("t-2", "plan-lt"))

        r = client.get(f"{BASE}/plans/plan-lt/tasks")
        assert r.status_code == 200
        assert len(r.json()["items"]["items"]) == 2


# ---------------------------------------------------------------------------
# Direct-handler tests (#1297 follow-up: FE↔BE review fixes)
#
# The HTTP routes above are dev-tier gated out of the TestClient (#1151), so
# these call the route coroutines directly with the `db` fixture to verify the
# handler logic the FE↔BE review flagged:
#   - library_destination_folder_id round-trips on create + update
#   - GET /projects/{id}/tasks aggregates tasks across a project's plans
# ---------------------------------------------------------------------------


class TestProjectFolderDestinationHandlers:
    async def test_create_persists_library_destination_folder_id(self, db):
        from fichero.api.routes.research_crud import (
            ProjectCreateRequest,
            create_project,
        )

        project = await create_project(
            ProjectCreateRequest(
                name="With Folder", library_destination_folder_id="folder-abc"
            ),
            db=db,
        )
        assert project.library_destination_folder_id == "folder-abc"
        # Re-read from the DB to confirm it was actually written.
        assert db.get(ResearchProject, project.id).library_destination_folder_id == "folder-abc"
        workspace = db.get(Document, project.id)
        assert workspace is not None
        assert workspace.prototype_key == "research_workspace"
        assert workspace.is_workspace is True
        assert workspace.attributes["library_destination_folder_id"] == "folder-abc"

    async def test_update_changes_library_destination_folder_id(self, db):
        from fichero.api.routes.research_crud import (
            ProjectUpdateRequest,
            update_project,
        )

        db.save(_make_project("p-folder", "Folder Project"))
        updated = await update_project(
            "p-folder",
            ProjectUpdateRequest(library_destination_folder_id="folder-xyz"),
            db=db,
        )
        assert updated.library_destination_folder_id == "folder-xyz"
        assert db.get(ResearchProject, "p-folder").library_destination_folder_id == "folder-xyz"

    async def test_list_projects_reads_folded_workspace_nodes(self, db):
        from fichero.api.routes.research_crud import list_projects

        db.save(
            Document(
                id="ws-proj-1",
                name="Workspace Alpha",
                doc_type=DocType.folder,
                node_kind="workspace",
                prototype_key="research_workspace",
                is_workspace=True,
                attributes={
                    "description": "alpha",
                    "status": "active",
                    "created_by": "human",
                    "library_destination_folder_id": "folder-a",
                    "metadata": {"topic": "letters"},
                },
            )
        )

        result = await list_projects(db=db)
        assert result.count >= 1
        project = next(item for item in result.items if item.id == "ws-proj-1")
        assert project.name == "Workspace Alpha"
        assert project.library_destination_folder_id == "folder-a"
        assert project.metadata == {"topic": "letters"}

    async def test_get_project_uses_inherited_workspace_prototype_defaults(self, db):
        from fichero.api.routes.research_crud import get_project

        db.save(
            Document(
                id="ws-proj-inherited",
                name="Workspace Inherited",
                doc_type=DocType.folder,
                node_kind="workspace",
                prototype_key="research_workspace",
                is_workspace=True,
                attributes={"description": "alpha inherited", "metadata": {"topic": "letters"}},
            )
        )

        project = await get_project("ws-proj-inherited", db=db)
        assert project.status.value == "active"
        assert project.created_by == "human"
        assert project.metadata == {"topic": "letters"}

    def test_workspace_items_route_works_for_research_project_node(self, client, db):
        workspace = Document(
            id="ws-proj-2",
            name="Workspace Beta",
            doc_type=DocType.folder,
            node_kind="workspace",
            prototype_key="research_workspace",
            is_workspace=True,
        )
        target = Document(id="doc-target", name="Source Doc", doc_type=DocType.file)
        db.save(workspace)
        db.save(target)

        patched = client.patch(
            f"/api/documents/{workspace.id}/workspace",
            json={
                "add": [
                    {
                        "id": "item-1",
                        "target_type": "document",
                        "target_id": target.id,
                        "role": "source",
                    }
                ]
            },
        )
        assert patched.status_code == 200

        fetched = client.get(f"/api/documents/{workspace.id}/workspace/items")
        assert fetched.status_code == 200
        payload = fetched.json()
        assert payload["count"] == 1
        assert payload["items"][0]["target"]["id"] == target.id

    async def test_missing_folded_workspace_raises_not_found(self, db):
        from fichero.api.routes.research_crud import get_project

        db.save(_make_project("legacy-only", "Legacy Only"))
        db._execute("DELETE FROM documents WHERE id = $id", {"id": "legacy-only"})

        with pytest.raises(HTTPException) as exc:
            await get_project("legacy-only", db=db)

        assert exc.value.status_code == 404

    async def test_missing_workspace_prototype_definition_raises(self, db):
        from fichero.api.routes.research_crud import get_project

        db.save(
            Document(
                id="ws-bad-proto",
                name="Broken Workspace",
                doc_type=DocType.folder,
                node_kind="workspace",
                prototype_key="research_workspace",
                is_workspace=True,
                attributes={"description": "broken"},
            )
        )
        workspace_proto = next(
            value
            for value in db.query(
                ClassificationValue,
                dimension=ClassificationDimension.document_prototype,
            )
            if value.key == "research_workspace"
        )
        db.delete(workspace_proto)

        with pytest.raises(PrototypeResolutionError):
            await get_project("ws-bad-proto", db=db)


class TestListProjectTasksHandler:
    async def test_aggregates_tasks_across_all_plans_in_project(self, db):
        from fichero.api.routes.research_crud import list_project_tasks

        db.save(_make_project("proj-agg"))
        db.save(_make_plan("plan-a", "proj-agg"))
        db.save(_make_plan("plan-b", "proj-agg"))
        db.save(_make_task("ta-1", "plan-a"))
        db.save(_make_task("ta-2", "plan-a"))
        db.save(_make_task("tb-1", "plan-b"))
        # A task in an unrelated project's plan must NOT leak in.
        db.save(_make_project("proj-other"))
        db.save(_make_plan("plan-other", "proj-other"))
        db.save(_make_task("to-1", "plan-other"))

        result = await list_project_tasks("proj-agg", db=db)
        assert result.count == 3
        plan_ids = {t.plan_id for t in result.items}
        assert plan_ids == {"plan-a", "plan-b"}


class TestResearchContentHandlers:
    async def test_list_plans_tasks_steps_read_folded_document_nodes(self, db):
        from fichero.api.routes.research_crud import list_plans, list_tasks, list_steps

        db.save(
            Document(
                id="ws-folded",
                name="Workspace",
                doc_type=DocType.folder,
                node_kind="workspace",
                prototype_key="research_workspace",
                is_workspace=True,
                attributes={
                    "description": "",
                    "status": "active",
                    "created_by": "human",
                    "library_destination_folder_id": None,
                    "metadata": {},
                },
            )
        )
        db.save(
            Document(
                id="plan-folded",
                parent_id="ws-folded",
                name="Plan Folded",
                doc_type=DocType.folder,
                node_kind="plan",
                prototype_key="research_plan",
                attributes={
                    "description": "plan",
                    "status": "active",
                    "order_index": 1,
                    "metadata": {"topic": "letters"},
                },
            )
        )
        db.save(
            Document(
                id="task-folded",
                parent_id="plan-folded",
                name="Task Folded",
                doc_type=DocType.folder,
                node_kind="task",
                prototype_key="research_task",
                attributes={
                    "description": "task",
                    "status": "pending",
                    "priority": 2,
                    "assigned_to": "agent",
                    "metadata": {},
                    "completed_at": None,
                },
            )
        )
        db.save(
            Document(
                id="step-folded",
                parent_id="task-folded",
                name="Step Folded",
                doc_type=DocType.file,
                node_kind="step",
                prototype_key="research_step",
                attributes={
                    "tool": "web_search",
                    "description": "step",
                    "config": {"query": "letters"},
                    "status": "pending",
                    "result": {},
                    "error": None,
                    "order_index": 0,
                    "completed_at": None,
                },
            )
        )

        plans = await list_plans("ws-folded", db=db)
        assert plans.count == 1
        assert plans.items[0].id == "plan-folded"

        tasks = await list_tasks("plan-folded", db=db)
        assert tasks.count == 1
        assert tasks.items[0].id == "task-folded"

        steps = await list_steps("task-folded", db=db)
        assert steps.count == 1
        assert steps.items[0].id == "step-folded"

    def test_plan_task_step_appear_in_document_children_hierarchy(self, client, db):
        workspace = Document(
            id="ws-tree",
            name="Workspace Tree",
            doc_type=DocType.folder,
            node_kind="workspace",
            prototype_key="research_workspace",
            is_workspace=True,
        )
        plan = Document(
            id="plan-tree",
            parent_id="ws-tree",
            name="Plan Tree",
            doc_type=DocType.folder,
            node_kind="plan",
            prototype_key="research_plan",
            attributes={"description": "", "status": "draft", "order_index": 0, "metadata": {}},
        )
        task = Document(
            id="task-tree",
            parent_id="plan-tree",
            name="Task Tree",
            doc_type=DocType.folder,
            node_kind="task",
            prototype_key="research_task",
            attributes={
                "description": "",
                "status": "pending",
                "priority": 0,
                "assigned_to": None,
                "metadata": {},
                "completed_at": None,
            },
        )
        step = Document(
            id="step-tree",
            parent_id="task-tree",
            name="Step Tree",
            doc_type=DocType.file,
            node_kind="step",
            prototype_key="research_step",
            attributes={
                "tool": "web_search",
                "description": "",
                "config": {},
                "status": "pending",
                "result": {},
                "error": None,
                "order_index": 0,
                "completed_at": None,
            },
        )
        db.save(workspace)
        db.save(plan)
        db.save(task)
        db.save(step)

        plan_children = client.get("/api/documents/ws-tree/children")
        assert plan_children.status_code == 200
        assert [item["id"] for item in plan_children.json()["items"]] == ["plan-tree"]

        task_children = client.get("/api/documents/plan-tree/children")
        assert task_children.status_code == 200
        assert [item["id"] for item in task_children.json()["items"]] == ["task-tree"]

        step_children = client.get("/api/documents/task-tree/children")
        assert step_children.status_code == 200
        assert [item["id"] for item in step_children.json()["items"]] == ["step-tree"]

    async def test_missing_folded_plan_raises_not_found(self, db):
        from fichero.api.routes.research_crud import get_plan

        db.save(_make_plan("legacy-plan", "proj-1"))
        db._execute("DELETE FROM documents WHERE id = $id", {"id": "legacy-plan"})

        with pytest.raises(HTTPException) as exc:
            await get_plan("legacy-plan", db=db)

        assert exc.value.status_code == 404
