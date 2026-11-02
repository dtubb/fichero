"""Step 3.4 (#4450, #3181): defaults come from the app; chains belong to the library that made them.

`workflows.defaults-resolve-from-the-app-not-the-library` (the resolution half): a default workflow is found in a library that
never held a copy, a library's own row of the same id wins, and a workflow a person built in the global library never reaches
another library. `workflows.defaults.chains-not-persisted`: a chain is stored in its library, survives a restart, and is not
seen from another library.
"""

from __future__ import annotations

import pytest

from fichero_server.db import db_manager
from fichero_server.execution.chaining import ChainStep, ChainStore, WorkflowChain
from fichero_server.models import Workflow
from fichero_server.workflows import default_workflows as dw


@pytest.fixture
def two_libraries(tmp_path, monkeypatch):
    from tests.integration._seedlib import seed

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    paths = [tmp_path / "a.fichero", tmp_path / "b.fichero"]
    for p in paths:
        seed(p)
    yield paths
    for p in paths:
        db_manager.close_database(p)


def _chain(name="C"):
    return WorkflowChain(name=name, steps=[ChainStep(id="s1", workflow_id="w1", name="one")])


def test_a_chain_is_stored_in_its_library_and_survives_a_restart(two_libraries):
    a, b = two_libraries
    store = ChainStore()
    chain = store.save(_chain("mine"), db_manager.get_database(a))
    db_manager.close_database(a)  # a restart: nothing held in this process
    reopened = db_manager.get_database(a)
    fresh = ChainStore()
    assert fresh.get(chain.id, reopened).name == "mine"
    assert [c.name for c in fresh.list(db=reopened)] == ["mine"] and fresh.count(reopened) == 1
    assert fresh.get(chain.id, db_manager.get_database(b)) is None, "another library does not see it"
    assert fresh.list(db=db_manager.get_database(b)) == []


def test_a_library_chain_is_not_in_the_process_memory_and_delete_removes_it(two_libraries):
    a, _ = two_libraries
    db = db_manager.get_database(a)
    store = ChainStore()
    chain = store.save(_chain(), db)
    assert store.get(chain.id) is None, "no library named: the process's own chains, which this is not"
    assert store.delete(chain.id, db) is True and store.delete(chain.id, db) is False
    assert store.get(chain.id, db) is None


def test_with_no_library_a_chain_is_held_in_memory_as_before():
    store = ChainStore()
    chain = store.save(_chain())
    assert store.get(chain.id).id == chain.id and store.count() == 1 and store.delete(chain.id) is True


@pytest.fixture
def global_defaults(two_libraries, monkeypatch):
    """Library a stands in for the global defaults library; library b is the project being opened."""
    a, b = two_libraries
    gdb = db_manager.get_database(a)
    monkeypatch.setattr(dw, "get_global_defaults_database", lambda: gdb)
    return gdb, db_manager.get_database(b)


def test_a_default_resolves_in_a_library_that_holds_no_copy(global_defaults):
    gdb, project = global_defaults
    wid = dw.preset_workflow_id("Translate")
    gdb.save(Workflow(id=wid, name="Translate", is_system=True, is_template=True, nodes=[], edges=[]))
    assert project.get(Workflow, wid) is None
    found = dw.resolve_default_workflow(wid)
    assert found is not None and found.name == "Translate"


def test_a_workflow_a_person_built_in_the_global_library_never_leaks_to_another(global_defaults):
    gdb, _ = global_defaults
    gdb.save(Workflow(id="mine-1", name="My own", nodes=[], edges=[]))
    assert dw.resolve_default_workflow("mine-1") is None
    assert all(w.id != "mine-1" for w in dw.list_global_default_workflows())
