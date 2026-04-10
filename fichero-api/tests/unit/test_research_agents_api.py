"""Unit tests for Agent Research API routes."""

import pytest
from fichero.research_models import (
    CheckItemStatus,
    NoteType,
    ResearchChecklistItem,
    ResearchNote,
    ResearchPlan,
    ResearchProject,
    ResearchResult,
    ResearchSource,
    ResearchStatus,
    ResearchStep,
    ResearchTask,
    SourceType,
    StepType,
)


def test_project_crud(client, db):
    """Create, read, update, archive research projects."""
    # Create
    resp = client.post(
        "/api/research/projects",
        json={
            "name": "Medieval Trade Routes Analysis",
            "description": "Investigating silk road trade patterns in 12th-14th centuries.",
            "research_question": "How did trade routes influence cultural exchange?",
            "goals": ["Map major routes", "Identify key commodities", "Document cultural impacts"],
            "scope_notes": "Focus on Central Asia and Eastern Europe.",
        },
    )
    assert resp.status_code == 200
    project = resp.json()
    assert project["name"] == "Medieval Trade Routes Analysis"
    assert project["research_question"] == "How did trade routes influence cultural exchange?"
    assert project["status"] == "draft"
    assert project["owner_id"] == "user"

    # List
    list_resp = client.get("/api/research/projects")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Filter by status
    active_resp = client.get("/api/research/projects?status=draft")
    assert active_resp.status_code == 200
    assert all(p["status"] == "draft" for p in active_resp.json())

    # Get
    get_resp = client.get(f"/api/research/projects/{project['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == project["id"]

    # Update
    patch_resp = client.patch(
        f"/api/research/projects/{project['id']}",
        json={
            "description": "Updated scope including Mediterranean trade.",
            "status": "active",
        },
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert "Mediterranean" in updated["description"]
    assert updated["status"] == "active"

    # Archive
    del_resp = client.delete(f"/api/research/projects/{project['id']}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "archived"

    # Verify archived
    get_after_del = client.get(f"/api/research/projects/{project['id']}")
    assert get_after_del.status_code == 200
    assert get_after_del.json()["status"] == "archived"


def test_project_not_found(client):
    """404 for missing project."""
    resp = client.get("/api/research/projects/nonexistent-id")
    assert resp.status_code == 404


def test_plan_crud(client, db):
    """Create, read, update plans within projects."""
    # Create project first
    proj_resp = client.post(
        "/api/research/projects",
        json={
            "name": "Test Project",
            "description": "For plan testing.",
        },
    )
    project = proj_resp.json()
    project_id = project["id"]

    # Create plan
    resp = client.post(
        "/api/research/plans",
        json={
            "project_id": project_id,
            "name": "Phase 1: Literature Review",
            "description": "Review existing scholarship on the topic.",
            "phase_number": 1,
            "objectives": ["Survey academic sources", "Identify gaps in research"],
            "success_criteria": ["Minimum 50 sources reviewed", "Gap analysis document"],
            "deliverables": ["Literature review memo"],
        },
    )
    assert resp.status_code == 200
    plan = resp.json()
    assert plan["project_id"] == project_id
    assert plan["phase_number"] == 1
    assert plan["name"] == "Phase 1: Literature Review"

    # List by project
    list_resp = client.get(f"/api/research/plans?project_id={project_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Get
    get_resp = client.get(f"/api/research/plans/{plan['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == plan["id"]

    # Update
    patch_resp = client.patch(
        f"/api/research/plans/{plan['id']}",
        json={"phase_number": 2, "status": "active"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["phase_number"] == 2
    assert patch_resp.json()["status"] == "active"

    # Archive
    del_resp = client.delete(f"/api/research/plans/{plan['id']}")
    assert del_resp.status_code == 200

    # Reject plan with bad project_id
    bad_resp = client.post(
        "/api/research/plans",
        json={
            "project_id": "nonexistent",
            "name": "Bad Plan",
        },
    )
    assert bad_resp.status_code == 404


def test_plan_not_found(client):
    """404 for missing plan."""
    resp = client.get("/api/research/plans/nonexistent-id")
    assert resp.status_code == 404


def test_task_crud(client, db):
    """Create, read, update, complete tasks."""
    # Create hierarchy
    proj_resp = client.post(
        "/api/research/projects",
        json={"name": "Task Test Project", "description": "Testing tasks."},
    )
    project_id = proj_resp.json()["id"]

    plan_resp = client.post(
        "/api/research/plans",
        json={
            "project_id": project_id,
            "name": "Task Test Plan",
            "description": "Plan for tasks.",
        },
    )
    plan_id = plan_resp.json()["id"]

    # Create task
    resp = client.post(
        "/api/research/tasks",
        json={
            "plan_id": plan_id,
            "project_id": project_id,
            "name": "Search Academic Databases",
            "description": "Query JSTOR, Google Scholar, and archive.org.",
            "task_number": 1,
            "priority": 1,
            "estimated_hours": 4.5,
        },
    )
    assert resp.status_code == 200
    task = resp.json()
    assert task["plan_id"] == plan_id
    assert task["project_id"] == project_id
    assert task["priority"] == 1
    assert task["estimated_hours"] == 4.5
    assert task["result"] == "pending"

    # List by plan
    list_resp = client.get(f"/api/research/tasks?plan_id={plan_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Complete task
    complete_resp = client.post(
        f"/api/research/tasks/{task['id']}/complete",
        params={"result_notes": "Found 32 relevant sources."},
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "complete"
    assert complete_resp.json()["result"] == "success"
    assert "32" in complete_resp.json()["result_notes"]

    # Archive
    del_resp = client.delete(f"/api/research/tasks/{task['id']}")
    assert del_resp.status_code == 200

    # Reject task with bad plan_id
    bad_resp = client.post(
        "/api/research/tasks",
        json={
            "plan_id": "nonexistent",
            "project_id": project_id,
            "name": "Bad Task",
        },
    )
    assert bad_resp.status_code == 404


def test_task_not_found(client):
    """404 for missing task."""
    resp = client.get("/api/research/tasks/nonexistent-id")
    assert resp.status_code == 404


def test_step_crud(client, db):
    """Create, read, update, execute, complete steps."""
    # Create hierarchy
    proj_resp = client.post(
        "/api/research/projects",
        json={"name": "Step Test Project", "description": "Testing steps."},
    )
    project_id = proj_resp.json()["id"]

    plan_resp = client.post(
        "/api/research/plans",
        json={
            "project_id": project_id,
            "name": "Step Test Plan",
            "description": "Plan for steps.",
        },
    )
    plan_id = plan_resp.json()["id"]

    task_resp = client.post(
        "/api/research/tasks",
        json={
            "plan_id": plan_id,
            "project_id": project_id,
            "name": "Step Test Task",
            "description": "Task for steps.",
        },
    )
    task_id = task_resp.json()["id"]

    # Create web search step
    resp = client.post(
        "/api/research/steps",
        json={
            "task_id": task_id,
            "plan_id": plan_id,
            "project_id": project_id,
            "step_number": 1,
            "step_type": "web_search",
            "name": "Search for primary sources",
            "description": "Query for contemporary accounts.",
            "query": "12th century silk road trade accounts primary sources",
        },
    )
    assert resp.status_code == 200
    step = resp.json()
    assert step["task_id"] == task_id
    assert step["step_type"] == "web_search"
    assert step["query"] == "12th century silk road trade accounts primary sources"

    # List by task
    list_resp = client.get(f"/api/research/steps?task_id={task_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Execute step
    exec_resp = client.post(f"/api/research/steps/{step['id']}/execute")
    assert exec_resp.status_code == 200
    assert exec_resp.json()["status"] == "in_progress"

    # Complete step with result
    complete_resp = client.post(
        f"/api/research/steps/{step['id']}/complete",
        json={
            "result": "success",
            "result_data": {"sources_found": 15, "top_result": "example.com/source1"},
        },
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "complete"
    assert complete_resp.json()["result"] == "success"
    assert complete_resp.json()["result_data"]["sources_found"] == 15

    # Archive
    del_resp = client.delete(f"/api/research/steps/{step['id']}")
    assert del_resp.status_code == 200


def test_step_not_found(client):
    """404 for missing step."""
    resp = client.get("/api/research/steps/nonexistent-id")
    assert resp.status_code == 404


def test_source_crud(client, db):
    """Create, read, update research sources."""
    # Create project first
    proj_resp = client.post(
        "/api/research/projects",
        json={"name": "Source Test Project", "description": "Testing sources."},
    )
    project_id = proj_resp.json()["id"]

    # Create URL source
    resp = client.post(
        "/api/research/sources",
        json={
            "project_id": project_id,
            "name": "JSTOR Academic Database",
            "description": "Academic journal repository.",
            "source_type": "url",
            "location": "https://www.jstor.org",
            "search_scope": "title-and-abstract",
            "relevance_score": 0.95,
        },
    )
    assert resp.status_code == 200
    source = resp.json()
    assert source["project_id"] == project_id
    assert source["source_type"] == "url"
    assert source["location"] == "https://www.jstor.org"

    # List by project
    list_resp = client.get(f"/api/research/sources?project_id={project_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Update source
    patch_resp = client.patch(
        f"/api/research/sources/{source['id']}",
        json={
            "findings_count": 12,
            "last_searched": "2026-04-10T10:00:00",
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["findings_count"] == 12

    # Archive
    del_resp = client.delete(f"/api/research/sources/{source['id']}")
    assert del_resp.status_code == 200


def test_note_crud(client, db):
    """Create, read, update research notes."""
    # Create project
    proj_resp = client.post(
        "/api/research/projects",
        json={"name": "Note Test Project", "description": "Testing notes."},
    )
    project_id = proj_resp.json()["id"]

    # Create observation note
    resp = client.post(
        "/api/research/notes",
        json={
            "project_id": project_id,
            "note_type": "observation",
            "content": "Interesting pattern: trade volumes spike during political stability periods.",
            "confidence": 0.75,
            "author_id": "user",
            "is_key_finding": True,
        },
    )
    assert resp.status_code == 200
    note = resp.json()
    assert note["project_id"] == project_id
    assert note["note_type"] == "observation"
    assert note["is_key_finding"] is True
    assert note["confidence"] == 0.75

    # List by project
    list_resp = client.get(f"/api/research/notes?project_id={project_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Filter key findings
    key_resp = client.get("/api/research/notes?is_key_finding=true")
    assert key_resp.status_code == 200
    assert all(n["is_key_finding"] for n in key_resp.json())

    # Update note
    patch_resp = client.patch(
        f"/api/research/notes/{note['id']}",
        json={
            "content": "Updated observation with additional context.",
            "confidence": 0.85,
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["confidence"] == 0.85

    # Delete (hard delete for notes)
    del_resp = client.delete(f"/api/research/notes/{note['id']}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"


def test_checklist_item_crud(client, db):
    """Create, read, complete checklist items."""
    # Create project
    proj_resp = client.post(
        "/api/research/projects",
        json={"name": "Checklist Test Project", "description": "Testing checklists."},
    )
    project_id = proj_resp.json()["id"]

    # Create checklist item
    resp = client.post(
        "/api/research/checklist-items",
        json={
            "project_id": project_id,
            "description": "Verify primary source authenticity",
            "category": "source_verification",
        },
    )
    assert resp.status_code == 200
    item = resp.json()
    assert item["project_id"] == project_id
    assert item["status"] == "pending"
    assert item["category"] == "source_verification"

    # List by project
    list_resp = client.get(f"/api/research/checklist-items?project_id={project_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Complete item
    complete_resp = client.post(
        f"/api/research/checklist-items/{item['id']}/complete",
        params={
            "verified_by": "research-agent-1",
            "verification_notes": "Source verified through cross-reference with institutional archive.",
        },
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "complete"
    assert complete_resp.json()["verified_by"] == "research-agent-1"
    assert "cross-reference" in complete_resp.json()["verification_notes"]


def test_sandboxed_tools_placeholder(client):
    """Placeholder sandboxed tools return example responses."""
    # Web search placeholder
    search_resp = client.post(
        "/api/research/tools/web-search",
        json={
            "query": "medieval trade routes silk road",
            "max_results": 5,
        },
    )
    assert search_resp.status_code == 200
    result = search_resp.json()
    assert result["query"] == "medieval trade routes silk road"
    assert len(result["results"]) > 0
    assert "total_found" in result
    assert "search_time_ms" in result

    # Browser navigate placeholder
    nav_resp = client.post(
        "/api/research/tools/browser-navigate",
        json={
            "url": "https://example.com/historical-source",
        },
    )
    assert nav_resp.status_code == 200
    nav_result = nav_resp.json()
    assert nav_result["url"] == "https://example.com/historical-source"
    assert nav_result["success"] is True

    # Document fetch placeholder
    fetch_resp = client.post(
        "/api/research/tools/document-fetch",
        json={
            "url": "https://example.com/document.pdf",
            "extract_claims": True,
        },
    )
    assert fetch_resp.status_code == 200
    fetch_result = fetch_resp.json()
    assert fetch_result["url"] == "https://example.com/document.pdf"
    assert fetch_result["success"] is True
    assert "claims_extracted" in fetch_result
