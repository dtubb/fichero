"""Unit tests for research_agents API routes."""

from unittest.mock import patch, AsyncMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Project CRUD
# ─────────────────────────────────────────────────────────────────────────────


def test_project_crud(client, db):
    """Create, read, update, delete research projects."""
    # Create
    resp = client.post(
        "/api/research/projects",
        json={
            "name": "Southern Colombia Mining 1880-1920",
            "description": "Systematic study of mining history.",
            "created_by": "human",
        },
    )
    assert resp.status_code == 200
    project = resp.json()
    assert project["name"] == "Southern Colombia Mining 1880-1920"
    assert project["status"] == "active"
    project_id = project["id"]

    # List
    list_resp = client.get("/api/research/projects")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) >= 1

    # Get
    get_resp = client.get(f"/api/research/projects/{project_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == project_id

    # Filter by status
    filter_resp = client.get("/api/research/projects?status=active")
    assert filter_resp.status_code == 200
    assert all(p["status"] == "active" for p in filter_resp.json()["items"])

    # Update
    patch_resp = client.patch(
        f"/api/research/projects/{project_id}",
        json={"description": "Updated description.", "status": "paused"},
    )
    assert patch_resp.status_code == 200
    assert "Updated description" in patch_resp.json()["description"]
    assert patch_resp.json()["status"] == "paused"

    # Delete
    del_resp = client.delete(f"/api/research/projects/{project_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"


def test_project_not_found(client):
    """404 for missing project."""
    resp = client.get("/api/research/projects/nonexistent-id")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Plan CRUD
# ─────────────────────────────────────────────────────────────────────────────


def test_plan_crud(client, db):
    """Create, read, update plans within a project."""
    # Create project first
    proj_resp = client.post(
        "/api/research/projects",
        json={"name": "Test Project", "description": ""},
    )
    project_id = proj_resp.json()["id"]

    # Create plan
    plan_resp = client.post(
        "/api/research/plans",
        json={
            "project_id": project_id,
            "name": "Phase 1: Archive Search",
            "description": "Search national archives.",
            "order_index": 0,
        },
    )
    assert plan_resp.status_code == 200
    plan = plan_resp.json()
    assert plan["name"] == "Phase 1: Archive Search"
    plan_id = plan["id"]

    # List plans for project
    list_resp = client.get(f"/api/research/projects/{project_id}/plans")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) >= 1

    # Get single plan
    get_resp = client.get(f"/api/research/plans/{plan_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == plan_id

    # Update plan
    patch_resp = client.patch(
        f"/api/research/plans/{plan_id}",
        json={"description": "Updated plan description."},
    )
    assert patch_resp.status_code == 200
    assert "Updated plan description" in patch_resp.json()["description"]


@pytest.mark.asyncio
async def test_plan_term_planning_generates_metadata(client, db):
    """Term-driven plan creation stores the agent's planning output."""
    mock_agent = AsyncMock(
        return_value={
            "result": (
                '{"archives":["national archives"],'
                '"locations":["Bogota","Medellin"],'
                '"multilingual_terms":{"en":["mining term"],"es":["termino minero"]},'
                '"summary":"Grounded research starter plan"}'
            ),
            "tool_calls": [
                {"tool": "research_web_search", "args": {"query": "mining term"}}
            ],
            "iterations": 1,
        }
    )
    with patch("fichero_server.api.routes.research_crud.react_agent", mock_agent):
        proj_resp = client.post(
            "/api/research/projects",
            json={"name": "Term Planning Project"},
        )
        project_id = proj_resp.json()["id"]

        plan_resp = client.post(
            "/api/research/plans",
            json={
                "project_id": project_id,
                "name": "Phase 1: term planning",
                "term": "mining term",
            },
        )

    assert plan_resp.status_code == 200
    plan = plan_resp.json()
    assert plan["metadata"]["research_term"] == "mining term"
    assert plan["metadata"]["research_plan"]["archives"] == ["national archives"]
    assert plan["metadata"]["research_plan"]["locations"] == ["Bogota", "Medellin"]
    assert plan["metadata"]["research_plan"]["multilingual_terms"]["es"] == [
        "termino minero"
    ]
    assert plan["metadata"]["research_plan"]["agent_result"]["tool_calls"][0][
        "tool"
    ] == "research_web_search"


def test_plan_not_found(client):
    """404 for missing plan."""
    resp = client.get("/api/research/plans/nonexistent-id")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Task CRUD
# ─────────────────────────────────────────────────────────────────────────────


def test_task_crud(client, db):
    """Create, read, update tasks within a plan."""
    # Setup project + plan
    proj_resp = client.post("/api/research/projects", json={"name": "Test Project"})
    project_id = proj_resp.json()["id"]
    plan_resp = client.post(
        "/api/research/plans",
        json={"project_id": project_id, "name": "Test Plan"},
    )
    plan_id = plan_resp.json()["id"]

    # Create task
    task_resp = client.post(
        "/api/research/tasks",
        json={
            "plan_id": plan_id,
            "name": "Search archive catalog",
            "description": "Find mining records.",
            "priority": 1,
        },
    )
    assert task_resp.status_code == 200
    task = task_resp.json()
    assert task["name"] == "Search archive catalog"
    assert task["status"] == "pending"
    task_id = task["id"]

    # List tasks
    list_resp = client.get(f"/api/research/plans/{plan_id}/tasks")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) >= 1

    # Update task
    patch_resp = client.patch(
        f"/api/research/tasks/{task_id}",
        json={"status": "in_progress", "priority": 0},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "in_progress"
    assert patch_resp.json()["priority"] == 0


def test_task_not_found(client):
    """404 for missing task."""
    resp = client.get("/api/research/tasks/nonexistent-id")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Step CRUD
# ─────────────────────────────────────────────────────────────────────────────


def test_step_crud(client, db):
    """Create and update research steps."""
    # Setup project + plan + task
    proj_resp = client.post("/api/research/projects", json={"name": "Test Project"})
    project_id = proj_resp.json()["id"]
    plan_resp = client.post(
        "/api/research/plans", json={"project_id": project_id, "name": "Plan"}
    )
    plan_id = plan_resp.json()["id"]
    task_resp = client.post(
        "/api/research/tasks", json={"plan_id": plan_id, "name": "Task"}
    )
    task_id = task_resp.json()["id"]

    # Create step
    step_resp = client.post(
        "/api/research/steps",
        json={
            "task_id": task_id,
            "tool": "web_search",
            "label": "Search archives",
            "description": "Query archive catalog",
            "config": {"query": "archive catalog"},
            "order_index": 0,
        },
    )
    assert step_resp.status_code == 200
    step = step_resp.json()
    assert step["tool"] == "web_search"
    assert step["status"] == "pending"
    assert step["config"]["query"] == "archive catalog"
    step_id = step["id"]

    # List steps
    list_resp = client.get(f"/api/research/tasks/{task_id}/steps")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) >= 1

    # Update step result
    patch_resp = client.patch(
        f"/api/research/steps/{step_id}",
        json={
            "status": "completed",
            "result": {"url": "https://example.com", "title": "Archive record"},
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "completed"
    assert patch_resp.json()["result"]["url"] == "https://example.com"


# ─────────────────────────────────────────────────────────────────────────────
# Search Sources
# ─────────────────────────────────────────────────────────────────────────────


def test_search_source_crud(client, db):
    """Create and list search sources."""
    proj_resp = client.post("/api/research/projects", json={"name": "Test Project"})
    project_id = proj_resp.json()["id"]

    source_resp = client.post(
        "/api/research/sources",
        json={
            "project_id": project_id,
            "source_type": "url",
            "label": "National Archives",
            "url": "https://www.archives.gov",
            "description": "US National Archives.",
            "access_status": "public",
            "reliability": 0.9,
        },
    )
    assert source_resp.status_code == 200
    source = source_resp.json()
    assert source["label"] == "National Archives"
    assert source["source_type"] == "url"

    # List sources
    list_resp = client.get(f"/api/research/projects/{project_id}/sources")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Research Notes
# ─────────────────────────────────────────────────────────────────────────────


def test_note_crud(client, db):
    """Create and update research notes."""
    proj_resp = client.post("/api/research/projects", json={"name": "Test Project"})
    project_id = proj_resp.json()["id"]

    note_resp = client.post(
        "/api/research/notes",
        json={
            "project_id": project_id,
            "note_type": "observation",
            "content": "Found mining concession records from 1885.",
            "tags": ["mining", "1885"],
        },
    )
    assert note_resp.status_code == 200
    note = note_resp.json()
    assert "1885" in note["content"]
    assert note["note_type"] == "observation"
    note_id = note["id"]

    # List notes
    list_resp = client.get(f"/api/research/projects/{project_id}/notes")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) >= 1

    # Update note
    patch_resp = client.patch(
        f"/api/research/notes/{note_id}",
        json={"note_type": "finding", "tags": ["mining", "1885", "concession"]},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["note_type"] == "finding"
    assert "concession" in patch_resp.json()["tags"]


def test_note_not_found(client):
    """404 for missing note."""
    resp = client.get("/api/research/notes/nonexistent-id")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Research Checklists
# ─────────────────────────────────────────────────────────────────────────────


def test_checklist_crud(client, db):
    """Create and toggle checklist items."""
    proj_resp = client.post("/api/research/projects", json={"name": "Test Project"})
    project_id = proj_resp.json()["id"]

    checklist_resp = client.post(
        "/api/research/checklists",
        json={
            "project_id": project_id,
            "title": "Archive Verification",
            "items": [
                {"id": "item-1", "label": "Verify document date", "checked": False},
                {"id": "item-2", "label": "Check signature authenticity", "checked": False},
            ],
        },
    )
    assert checklist_resp.status_code == 200
    checklist = checklist_resp.json()
    assert checklist["title"] == "Archive Verification"
    checklist_id = checklist["id"]
    item_id = checklist["items"][0]["id"]

    # Toggle item
    toggle_resp = client.patch(
        f"/api/research/checklists/{checklist_id}/items/{item_id}",
        json={"checked": True, "notes": "Date confirmed as 1885."},
    )
    assert toggle_resp.status_code == 200
    updated_items = toggle_resp.json()["items"]
    item = next(i for i in updated_items if i["id"] == item_id)
    assert item["checked"] is True
    assert "1885" in item["notes"]


# ─────────────────────────────────────────────────────────────────────────────
# Sandboxed Tools
# ─────────────────────────────────────────────────────────────────────────────


def test_web_search_success(client):
    """Web search returns results from DuckDuckGo."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = """
    <a class="result__a" href="https://example.com">Example Result</a>
    <a class="result__url" href="https://example.com">example.com</a>
    <p class="result__snippet">This is a snippet about mining in Colombia.</p>
    """
    mock_response.raise_for_status = lambda: None

    mock_async_client = AsyncMock()
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)
    mock_async_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_async_client):
        resp = client.post(
            "/api/research/tools/web-search",
            json={"query": "mining Colombia 1880", "max_results": 5},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "mining Colombia 1880"
    assert "results" in data
    assert "total_results" in data
    assert "execution_time_ms" in data


def test_web_search_empty_query(client):
    """Web search rejects empty query."""
    resp = client.post(
        "/api/research/tools/web-search",
        json={"query": "a", "max_results": 5},
    )
    assert resp.status_code == 400


def test_web_search_timeout(client):
    """Web search handles timeout gracefully."""
    import httpx

    mock_async_client = AsyncMock()
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)
    mock_async_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("httpx.AsyncClient", return_value=mock_async_client):
        resp = client.post(
            "/api/research/tools/web-search",
            json={"query": "mining Colombia", "max_results": 5},
        )

    assert resp.status_code == 504


def test_browser_navigate_success(client):
    """Browser navigate extracts page content."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html"}
    mock_response.text = """
    <html><head><title>Test Archive - Mining Records</title></head>
    <body>
    <a href="https://example.com/link1">Link 1</a>
    <a href="https://example.com/link2">Link 2</a>
    </body></html>
    """
    mock_response.raise_for_status = lambda: None

    mock_async_client = AsyncMock()
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)
    mock_async_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_async_client):
        resp = client.post(
            "/api/research/tools/browser-navigate",
            json={"url": "https://example.com/archive", "timeout_seconds": 30},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["url"] == "https://example.com/archive"
    assert "Test Archive" in data["title"]
    assert len(data["extracted_links"]) >= 2


def test_browser_navigate_sandbox_blocked(client):
    """Browser navigate blocks sandbox violations."""
    resp = client.post(
        "/api/research/tools/browser-navigate",
        json={"url": "file:///etc/passwd"},
    )
    assert resp.status_code == 400
    assert "not allowed" in resp.json()["detail"]


def test_document_fetch_success(client):
    """Document fetch returns content and optionally creates source."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html; charset=utf-8"}
    mock_response.text = "<html><head><title>Test Page</title></head></html>"
    mock_response.raise_for_status = lambda: None

    mock_async_client = AsyncMock()
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)
    mock_async_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_async_client):
        resp = client.post(
            "/api/research/tools/document-fetch",
            json={
                "url": "https://example.com/document",
                "project_id": "test-project-id",
                "create_as_source": False,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["url"] == "https://example.com/document"
    assert data["success"] is True
    assert data["title"] is not None


def test_document_fetch_sandbox_blocked(client):
    """Document fetch blocks sandbox violations."""
    resp = client.post(
        "/api/research/tools/document-fetch",
        json={"url": "ftp://example.com/file", "project_id": "test"},
    )
    assert resp.status_code == 400
    assert "not allowed" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# Sandbox Security
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com",
        "smb://server/share",
        "s3://bucket/file",
    ],
)
def test_sandbox_blocks_dangerous_urls(client, url):
    """Sandbox blocks file/ftp/smb/s3 URLs for browser-navigate and document-fetch."""
    # browser-navigate
    r = client.post("/api/research/tools/browser-navigate", json={"url": url})
    assert r.status_code == 400

    # document-fetch
    r = client.post(
        "/api/research/tools/document-fetch",
        json={"url": url, "project_id": "test"},
    )
    assert r.status_code == 400
