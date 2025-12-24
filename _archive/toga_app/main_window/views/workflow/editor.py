"""Workflow Editor - Node canvas + step editor + output log.

Shows a visual workflow graph with:
- Node canvas showing workflow steps
- Step editor for configuring selected step
- Output log showing execution progress

Usage:
    from fichero.app.main_window.views.workflow import WorkflowEditor

    editor = WorkflowEditor()
    editor.load(workflow)
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from rubicon.objc import ObjCClass

if TYPE_CHECKING:
    from fichero.models import Workflow

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

_AUTORESIZE_FLEX = 18  # NSViewWidthSizable | NSViewHeightSizable

# =============================================================================
# Cocoa Classes
# =============================================================================

NSView = ObjCClass("NSView")
NSColor = ObjCClass("NSColor")
NSTextField = ObjCClass("NSTextField")
NSFont = ObjCClass("NSFont")


# =============================================================================
# Workflow Editor
# =============================================================================

class WorkflowEditor:
    """Workflow editor with node canvas, step editor, and output log.

    Components (will be implemented in Phase 4):
    - canvas.py: Node graph visualization
    - step_editor.py: Step configuration panel
    - output_log.py: Columnar execution log
    """

    def __init__(self):
        self._workflow: Workflow | None = None

        # Container view
        self._container = NSView.alloc().initWithFrame_(((0, 0), (400, 600)))
        self._container.setAutoresizingMask_(_AUTORESIZE_FLEX)
        self._container.wantsLayer = True
        self._container.layer.backgroundColor = NSColor.windowBackgroundColor.CGColor

        # Placeholder label (temporary until canvas is implemented)
        self._placeholder = NSTextField.alloc().initWithFrame_(((0, 0), (400, 100)))
        self._placeholder.stringValue = "Workflow Editor\n(Coming soon)"
        self._placeholder.editable = False
        self._placeholder.bordered = False
        self._placeholder.drawsBackground = False
        self._placeholder.alignment = 1  # Center
        self._placeholder.font = NSFont.systemFontOfSize_(18)
        self._placeholder.textColor = NSColor.secondaryLabelColor
        self._container.addSubview_(self._placeholder)

        # Center the placeholder
        self._placeholder.setFrameOrigin_(((200 - 200), 250))
        self._placeholder.setFrameSize_((400, 100))

        logger.info("WorkflowEditor created (placeholder)")

    @property
    def native(self) -> Any:
        """The native container NSView."""
        return self._container

    @property
    def workflow(self) -> Workflow | None:
        """Currently loaded workflow."""
        return self._workflow

    def load(self, workflow: Workflow | None) -> None:
        """Load a workflow for editing.

        Args:
            workflow: Workflow model to edit
        """
        self._workflow = workflow

        if workflow:
            name = getattr(workflow, 'name', 'Untitled')
            steps = getattr(workflow, 'steps', [])
            self._placeholder.stringValue = f"Workflow: {name}\n{len(steps)} steps"
        else:
            self._placeholder.stringValue = "Workflow Editor\n(Select a workflow)"

        logger.debug(f"WorkflowEditor loaded: {workflow}")

    def clear(self) -> None:
        """Clear the editor."""
        self._workflow = None
        self._placeholder.stringValue = "Workflow Editor\n(Select a workflow)"

    # -------------------------------------------------------------------------
    # Run Controls (stub - will connect to LangGraph executor)
    # -------------------------------------------------------------------------

    def run(self) -> None:
        """Run the workflow."""
        if not self._workflow:
            logger.warning("No workflow to run")
            return
        # TODO: Connect to LangGraph executor
        logger.info(f"TODO: Run workflow {self._workflow.name}")

    def stop(self) -> None:
        """Stop the running workflow."""
        # TODO: Connect to LangGraph executor
        logger.info("TODO: Stop workflow")

    def pause(self) -> None:
        """Pause the running workflow."""
        # TODO: Connect to LangGraph executor
        logger.info("TODO: Pause workflow")
