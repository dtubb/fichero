"""`workflows.defaults.scope-contract-undeclared`, `workflows.defaults.declared-scope` (docs/contributor_manual/specs/ui/workflows.md,
Step 1.1, #4397): every workflow runs at one declared scope, served with the sentence that names it.

WHY: a run's scope was discovered from its effects (Catalogue on one selected PDF ran over the folder). The engine now says,
per workflow, whether it runs once for each file or once on the folder; the run menu reads the answer and never works it out.
"""

from __future__ import annotations

import pytest

from fichero_server.models import Workflow
from fichero_server.workflows.validation import SCOPE_SENTENCES, SCOPES, workflow_scope


def test_a_workflow_with_nothing_declared_runs_on_each_file():
    assert workflow_scope({}, [{"tool": "transcribe"}]) == "per_file"
    assert workflow_scope(None, None) == "per_file"


def test_a_folder_level_tool_makes_the_workflow_once_per_folder():
    assert workflow_scope({}, [{"tool": "files"}, {"tool": "catalogue"}]) == "once_per_folder"


def test_a_declared_scope_wins_either_way():
    assert workflow_scope({"scope": "per_file"}, [{"tool": "catalogue"}]) == "per_file"
    assert workflow_scope({"scope": "once_per_folder"}, [{"tool": "transcribe"}]) == "once_per_folder"


def test_each_scope_has_its_one_sentence_naming_where_it_runs():
    assert set(SCOPE_SENTENCES) == set(SCOPES)
    assert "each file" in SCOPE_SENTENCES["per_file"] and "once on the folder" in SCOPE_SENTENCES["once_per_folder"].lower()


def test_a_workflow_cannot_declare_a_third_scope():
    with pytest.raises(ValueError, match="per_file"):
        Workflow(name="x", config={"scope": "everywhere"})
    assert Workflow(name="x", config={"scope": "once_per_folder"}).config["scope"] == "once_per_folder"


def test_the_list_serves_each_workflows_scope_and_sentence(client, db):
    folder_level = Workflow(name="Folder record", format="nodes", nodes=[{"id": "c", "tool": "catalogue"}])
    each_file = Workflow(name="Each file", format="nodes", nodes=[{"id": "t", "tool": "transcribe"}],
                         config={"scope": "per_file"})
    db.save(folder_level)
    db.save(each_file)
    items = {i["id"]: i for i in client.get("/api/workflows").json()["items"]}
    assert items[folder_level.id]["scope"] == "once_per_folder"
    assert items[folder_level.id]["scope_sentence"] == SCOPE_SENTENCES["once_per_folder"]
    assert items[each_file.id]["scope"] == "per_file"
    assert all(i["scope"] in SCOPES and i["scope_sentence"] == SCOPE_SENTENCES[i["scope"]] for i in items.values())
