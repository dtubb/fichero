"""The CLI must not offer what the engine will refuse to run (#3804).

`config.internal` marks a workflow that only works inside a parent's
``sub_workflow`` node. The engine refuses to run one standalone, and
``/api/workflows`` publishes that decision as ``direct_runnable``.

The CLI never saw it. ``list_workflows()`` parsed each item into the STORAGE
model ``Workflow``, which has no such field, so Pydantic dropped it silently —
and with it ``untested``, ``accepts_model_override`` and ``requires_vision``.
The result was a list that presented every component as runnable and a ``run``
that resolved the name, sent the execute call, and surfaced the engine's
refusal as an opaque 400. A control that offers what cannot be done is worse
than a missing control: it makes the user distrust the refusal, not the offer.
"""

from __future__ import annotations

import httpx
import pytest

from fichero_cli import FicheroClient
from fichero_cli import __main__ as cli
from fichero_cli.client import FicheroError
from fichero_cli.formatters import render


def _workflow_item(workflow_id: str, name: str, **overrides) -> dict:
    """One item exactly as ``/api/workflows`` serves it."""
    item = {
        "id": workflow_id,
        "name": name,
        "description": "",
        "provider": "",
        "model": "",
        "format": "nodes",
        "nodes": [],
        "edges": [],
        "folder_path": "/",
        "sort_order": 0,
        "untested": False,
        "direct_runnable": True,
        "accepts_model_override": True,
        "requires_vision": False,
    }
    item.update(overrides)
    return item


ITEMS = [
    _workflow_item("wf-parent", "Transcribe Spanish Script", requires_vision=True),
    _workflow_item("wf-child", "Spanish Script Passes", direct_runnable=False),
]


def _client(items: list[dict]) -> FicheroClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/workflows"
        return httpx.Response(200, json={"items": items, "count": len(items)})

    return FicheroClient(
        base_url="http://test",
        token="token",
        library_path="/tmp/x.fichero",
        transport=httpx.MockTransport(handler),
    )


def test_list_workflows_keeps_the_engines_run_eligibility():
    """The regression that made every other item here possible."""
    with _client(ITEMS) as client:
        workflows = client.list_workflows()

    assert len(workflows) == 2, "fixture must contain both a parent and a component"
    by_name = {w.name: w for w in workflows}
    assert by_name["Spanish Script Passes"].direct_runnable is False
    assert by_name["Transcribe Spanish Script"].direct_runnable is True
    # The other engine-computed answers ride the same fix.
    assert by_name["Transcribe Spanish Script"].requires_vision is True


def test_resolve_workflow_refuses_an_internal_component_by_name():
    with _client(ITEMS) as client:
        with pytest.raises(FicheroError) as excinfo:
            cli._resolve_workflow(client, "Spanish Script Passes")

    message = str(excinfo.value)
    assert "internal component" in message
    assert "Run the parent workflow instead" in message


def test_resolve_workflow_refuses_an_internal_component_by_id():
    """Bypassing the name lookup must not bypass the refusal."""
    with _client(ITEMS) as client:
        with pytest.raises(FicheroError):
            cli._resolve_workflow(client, "wf-child")


def test_resolve_workflow_still_resolves_a_runnable_workflow():
    with _client(ITEMS) as client:
        assert cli._resolve_workflow(client, "Transcribe Spanish Script") == "wf-parent"
        assert cli._resolve_workflow(client, "wf-parent") == "wf-parent"


def test_unknown_workflow_still_reports_not_found_not_not_runnable():
    with _client(ITEMS) as client:
        with pytest.raises(FicheroError) as excinfo:
            cli._resolve_workflow(client, "No Such Workflow")

    assert "No workflow named" in str(excinfo.value)


def test_human_list_marks_components_that_cannot_be_run():
    """`fichero workflow list` is the list Daniel reads. Names alone say every
    row is runnable."""
    rendered = render(ITEMS)

    lines = {line for line in rendered.splitlines()}
    assert any(
        "Spanish Script Passes" in line and "component" in line for line in lines
    ), rendered
    assert not any(
        "Transcribe Spanish Script" in line and "component" in line for line in lines
    ), rendered


def test_json_list_carries_the_flag_for_scripted_callers():
    rendered = render(ITEMS, as_json=True)

    assert '"direct_runnable": false' in rendered
    assert '"requires_vision": true' in rendered
