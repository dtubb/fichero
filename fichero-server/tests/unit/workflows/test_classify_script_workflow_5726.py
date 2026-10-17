"""`source.recipe.workflow-gaps` (#5726): `classify_script` is a step on its own, not only inside Transcribe (Auto-Detect)."""
from __future__ import annotations

from fichero_server.models import Workflow
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.runtime import to_workflow_def
from fichero_server.workflows.validation import validate_workflow_connections


def test_classify_script_is_a_workflow_of_its_own_5726():
    preset = {p["name"]: p for p in _load_preset_files()}["Classify Script"]
    assert [n["tool"] for n in preset["nodes"]] == ["files", "classify_script"]
    workflow_def = to_workflow_def(Workflow(id="classify-script-gate", name=preset["name"], nodes=preset["nodes"],
                                            edges=preset["edges"], config=preset["config"],
                                            folder_path=preset["folder_path"]))
    assert validate_workflow_connections(workflow_def) == []
