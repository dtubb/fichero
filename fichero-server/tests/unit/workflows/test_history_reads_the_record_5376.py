"""A run holds one checkpoint, so the thread history reads its earlier steps from the run's saved record
(#5376, `activity.run.checkpoints-pruned`): the app's history view still lists every finished step."""
from types import SimpleNamespace

from fichero_server.api.routes.workflow_execution.threads import _steps_from_record


def _run(*events):
    return SimpleNamespace(progress_timeline={"events": list(events)})


def test_each_finished_step_in_the_record_is_an_entry_in_order():
    run = _run({"event": "node_begin", "node_id": "a"},
               {"event": "node_end", "node_id": "a", "timestamp": "t1"},
               {"event": "log"},
               {"event": "node_end", "node_id": "b", "timestamp": "t2"})
    got = _steps_from_record(run, lambda n: n.upper())
    assert [(c.step, c.node_name, c.timestamp) for c in got] == [(0, "A", "t1"), (1, "B", "t2")]


def test_a_step_from_the_record_is_not_restorable():
    (c,) = _steps_from_record(_run({"event": "node_end", "node_id": "a"}), str)
    assert c.restorable is False


def test_no_record_gives_no_entries():
    assert _steps_from_record(None, str) == []
    assert _steps_from_record(SimpleNamespace(progress_timeline=None), str) == []


def test_the_history_route_adds_them_when_one_checkpoint_is_held():
    import inspect

    from fichero_server.api.routes.workflow_execution import threads

    src = inspect.getsource(threads.get_thread_history)
    assert "_steps_from_record(run, _translate_node_name)" in src
