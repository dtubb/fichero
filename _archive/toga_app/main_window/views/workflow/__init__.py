"""Workflow View - Workflow editing and running mode.

Components:
- WorkflowEditor: Node canvas + step editor + output log
- WorkflowInspector: Provider/Model dropdowns + Add Provider

Usage:
    from fichero.app.main_window.views.workflow import WorkflowEditor, WorkflowInspector

    editor = WorkflowEditor()
    inspector = WorkflowInspector()

    # Load a workflow
    editor.load(workflow)
    inspector.load(workflow)
"""

from fichero.app.main_window.views.workflow.editor import WorkflowEditor
from fichero.app.main_window.views.workflow.inspector import WorkflowInspector

__all__ = [
    "WorkflowEditor",
    "WorkflowInspector",
]
