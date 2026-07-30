"""Unit tests for the audited research CRUD action family (#3024 slice 1).

Projects/plans/tasks/steps now route through ``registry.invoke`` and write an
ActionAudit row for every write route. These tests pin the generic #1848
contract here: effect lands, audit lands, undo restores the prior state, and
the route path hits the right action name.
"""

from __future__ import annotations

import fichero_server.api.routes.research.crud  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit
from fichero_server.models.research import (
    PlanStatus,
    ResearchPlan,
    ResearchProject,
    ResearchStep,
    ResearchTask,
    StepStatus,
    TaskStatus,
)


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


def _undo(db, audit_id: str, ctx: ActionContext):
    audit = db.get(ActionAudit, audit_id)
    reg = registry.get(audit.action_name)
    assert reg.undoable and reg.invert is not None
    inverse = reg.invert(audit.before, audit.after, ctx)
    assert inverse is not None
    name, params = inverse
    result = registry.invoke(db, name, params, ctx)
    return name, result


def _mk_project(db, name: str = "Project") -> ResearchProject:
    project = ResearchProject(name=name)
    db.save(project)
    return project


def _mk_plan(db, project_id: str, name: str = "Plan") -> ResearchPlan:
    plan = ResearchPlan(project_id=project_id, name=name)
    db.save(plan)
    return plan


def _mk_task(db, plan_id: str, name: str = "Task") -> ResearchTask:
    task = ResearchTask(plan_id=plan_id, name=name)
    db.save(task)
    return task


class TestResearchProjectActions:
    def test_create_update_delete_undo_chain(self, db):
        ctx = _ctx()
        created = registry.invoke(
            db,
            "research.project.create",
            {"name": "Research One", "description": "A"},
            ctx,
        )
        project_id = created.result.id
        assert db.get(ResearchProject, project_id) is not None
        assert db.get(ActionAudit, created.audit_id).action_name == "research.project.create"

        inv_name, _ = _undo(db, created.audit_id, ctx)
        assert inv_name == "research.project.delete"
        assert db.get(ResearchProject, project_id) is None

        recreated_name, recreated = _undo(db, db.all(ActionAudit)[-1].id, ctx)
        assert recreated_name == "research.project.restore"
        assert db.get(ResearchProject, project_id) is not None
        assert recreated.result.id == project_id

        updated = registry.invoke(
            db,
            "research.project.update",
            {"project_id": project_id, "status": "paused", "description": "B"},
            ctx,
        )
        assert db.get(ResearchProject, project_id).status.value == "paused"
        assert db.get(ActionAudit, updated.audit_id).before["description"] == "A"

        undo_name, _ = _undo(db, updated.audit_id, ctx)
        assert undo_name == "research.project.restore"
        restored = db.get(ResearchProject, project_id)
        assert restored.description == "A"

        deleted = registry.invoke(
            db, "research.project.delete", {"project_id": project_id}, ctx
        )
        assert db.get(ResearchProject, project_id) is None
        assert db.get(ActionAudit, deleted.audit_id).action_name == "research.project.delete"

        undo_delete_name, _ = _undo(db, deleted.audit_id, ctx)
        assert undo_delete_name == "research.project.restore"
        assert db.get(ResearchProject, project_id) is not None


class TestResearchPlanTaskStepActions:
    def test_plan_create_and_update_are_undoable(self, db):
        ctx = _ctx()
        project = _mk_project(db)

        created = registry.invoke(
            db,
            "research.plan.create",
            {
                "project_id": project.id,
                "name": "Phase 1",
                "term": "gold",
                "planning_payload": {"archives": ["national archives"]},
            },
            ctx,
        )
        plan_id = created.result.id
        assert db.get(ResearchPlan, plan_id) is not None
        assert db.get(ActionAudit, created.audit_id).action_name == "research.plan.create"
        assert db.get(ResearchPlan, plan_id).metadata["research_term"] == "gold"

        inv_name, _ = _undo(db, created.audit_id, ctx)
        assert inv_name == "research.plan.delete"
        assert db.get(ResearchPlan, plan_id) is None

        restored_name, _ = _undo(db, db.all(ActionAudit)[-1].id, ctx)
        assert restored_name == "research.plan.restore"
        assert db.get(ResearchPlan, plan_id) is not None

        updated = registry.invoke(
            db,
            "research.plan.update",
            {"plan_id": plan_id, "status": "active", "order_index": 2},
            ctx,
        )
        plan = db.get(ResearchPlan, plan_id)
        assert plan.status == PlanStatus.active
        assert plan.order_index == 2
        undo_name, _ = _undo(db, updated.audit_id, ctx)
        assert undo_name == "research.plan.restore"
        assert db.get(ResearchPlan, plan_id).order_index == 0

    def test_task_and_step_update_undo_restore_completed_fields(self, db):
        ctx = _ctx()
        project = _mk_project(db)
        plan = _mk_plan(db, project.id)

        created_task = registry.invoke(
            db,
            "research.task.create",
            {"plan_id": plan.id, "name": "Archive Search", "priority": 1},
            ctx,
        )
        task_id = created_task.result.id
        assert db.get(ResearchTask, task_id) is not None
        assert _undo(db, created_task.audit_id, ctx)[0] == "research.task.delete"
        assert db.get(ResearchTask, task_id) is None
        _undo(db, db.all(ActionAudit)[-1].id, ctx)

        updated_task = registry.invoke(
            db,
            "research.task.update",
            {"task_id": task_id, "status": "completed", "priority": 0},
            ctx,
        )
        task = db.get(ResearchTask, task_id)
        assert task.status == TaskStatus.completed
        assert task.completed_at is not None
        assert _undo(db, updated_task.audit_id, ctx)[0] == "research.task.restore"
        restored_task = db.get(ResearchTask, task_id)
        assert restored_task.status == TaskStatus.pending
        assert restored_task.completed_at is None

        created_step = registry.invoke(
            db,
            "research.step.create",
            {
                "task_id": task_id,
                "tool": "web_search",
                "label": "Search",
                "config": {"query": "mining"},
            },
            ctx,
        )
        step_id = created_step.result.id
        assert db.get(ResearchStep, step_id) is not None

        updated_step = registry.invoke(
            db,
            "research.step.update",
            {
                "step_id": step_id,
                "status": "completed",
                "result": {"url": "https://example.com"},
                "order_index": 2,
            },
            ctx,
        )
        step = db.get(ResearchStep, step_id)
        assert step.status == StepStatus.completed
        assert step.result["url"] == "https://example.com"
        assert step.completed_at is not None
        assert _undo(db, updated_step.audit_id, ctx)[0] == "research.step.restore"
        restored_step = db.get(ResearchStep, step_id)
        assert restored_step.status == StepStatus.pending
        assert restored_step.result == {}
        assert restored_step.completed_at is None


def test_research_crud_write_routes_write_action_audit(client, db):
    project = client.post("/api/research/projects", json={"name": "Audit Project"})
    assert project.status_code == 200
    project_id = project.json()["id"]
    assert db.all(ActionAudit)[-1].action_name == "research.project.create"

    patched_project = client.patch(
        f"/api/research/projects/{project_id}",
        json={"description": "Updated"},
    )
    assert patched_project.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "research.project.update"

    plan = client.post(
        "/api/research/plans",
        json={"project_id": project_id, "name": "Audit Plan"},
    )
    assert plan.status_code == 200
    plan_id = plan.json()["id"]
    assert db.all(ActionAudit)[-1].action_name == "research.plan.create"

    patched_plan = client.patch(
        f"/api/research/plans/{plan_id}",
        json={"status": "active"},
    )
    assert patched_plan.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "research.plan.update"

    task = client.post(
        "/api/research/tasks",
        json={"plan_id": plan_id, "name": "Audit Task"},
    )
    assert task.status_code == 200
    task_id = task.json()["id"]
    assert db.all(ActionAudit)[-1].action_name == "research.task.create"

    patched_task = client.patch(
        f"/api/research/tasks/{task_id}",
        json={"status": "completed"},
    )
    assert patched_task.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "research.task.update"

    step = client.post(
        "/api/research/steps",
        json={"task_id": task_id, "tool": "web_search", "label": "Audit Step"},
    )
    assert step.status_code == 200
    step_id = step.json()["id"]
    assert db.all(ActionAudit)[-1].action_name == "research.step.create"

    patched_step = client.patch(
        f"/api/research/steps/{step_id}",
        json={"status": "completed", "result": {"ok": True}},
    )
    assert patched_step.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "research.step.update"

    deleted_project = client.delete(f"/api/research/projects/{project_id}")
    assert deleted_project.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "research.project.delete"
