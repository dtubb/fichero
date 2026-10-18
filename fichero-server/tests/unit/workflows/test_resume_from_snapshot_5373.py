"""A resumed run keeps the graph it started with (#5373, `activity.run.resume-from-snapshot`): its nodes and edges come
from the run's own snapshot, not the stored workflow an edit has since changed."""
from fichero_server.models import Workflow
from fichero_server.workflows.resume_snapshot import as_started


def _wf(nodes, edges):
    return Workflow(id="w", name="W", nodes=nodes, edges=edges)


def _node(i, tool="t", **kw):
    return {"id": i, "tool": tool, "label": i, "config": {}, "inputs": {}, **kw}


SNAP = {"nodes": [{"id": "a", "tool": "t", "label": "a", "config": {"k": 1}, "inputs": {}},
                  {"id": "b", "tool": "t", "label": "b", "config": {}, "inputs": {}}],
        "edges": [{"source": "a", "target": "b"}]}


def test_an_edit_made_while_paused_does_not_change_the_graph():
    edited = _wf([_node("a", config={"k": 2}), _node("c")], [{"source": "a", "target": "c"}])
    got = as_started(edited, SNAP)
    assert [n["id"] for n in got.nodes] == ["a", "b"]  # c (added) is gone, b (deleted) is back
    assert got.nodes[0]["config"] == {"k": 1}
    assert got.edges == [{"source": "a", "target": "b"}]


def test_a_field_the_snapshot_does_not_keep_stays_from_the_stored_node():
    stored = _wf([_node("a", position_x=3.0, position_y=4.0), _node("b")], [])
    assert as_started(stored, SNAP).nodes[0]["position_x"] == 3.0


def test_a_run_with_no_snapshot_resumes_on_the_stored_workflow():
    stored = _wf([_node("a")], [])
    assert as_started(stored, None) is stored and as_started(stored, {}) is stored


def test_the_stored_workflow_is_not_changed():
    stored = _wf([_node("a", config={"k": 2})], [])
    as_started(stored, SNAP)
    assert stored.nodes[0]["config"] == {"k": 2}


def test_resume_applies_it():
    import inspect

    from fichero_server.api.routes.workflow_execution import core

    assert "as_started(workflow, snapshot)" in inspect.getsource(core.resume_workflow)
