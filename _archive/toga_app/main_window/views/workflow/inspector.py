"""Workflow Inspector - Provider/Model dropdowns + Add Provider.

Shows:
- Provider dropdown (from DuckDB)
- Model dropdown (filtered by provider)
- Add Provider button (opens Mac Mail-style sheet)
- Workflow settings

Usage:
    from fichero.app.main_window.views.workflow import WorkflowInspector

    inspector = WorkflowInspector()
    inspector.load(workflow)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, TYPE_CHECKING

from rubicon.objc import ObjCClass, SEL, objc_method, objc_property

if TYPE_CHECKING:
    from fichero.models import Workflow, Provider, Model

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

INSPECTOR_WIDTH = 300
AUTORESIZE_FLEX = 18
BORDER_NONE = 0

# =============================================================================
# Cocoa Classes
# =============================================================================

NSObject = ObjCClass("NSObject")
NSView = ObjCClass("NSView")
NSScrollView = ObjCClass("NSScrollView")
NSTextField = ObjCClass("NSTextField")
NSPopUpButton = ObjCClass("NSPopUpButton")
NSButton = ObjCClass("NSButton")
NSBox = ObjCClass("NSBox")
NSColor = ObjCClass("NSColor")
NSFont = ObjCClass("NSFont")


# =============================================================================
# Flipped View (top-down layout)
# =============================================================================

class _WorkflowInspectorFlippedView(NSView):
    """NSView with flipped coordinates for top-down layout."""

    @objc_method
    def isFlipped(self) -> bool:
        return True


# =============================================================================
# Button Delegate
# =============================================================================

class _WorkflowInspectorDelegate(NSObject):
    """Handles button actions."""

    _inspector = objc_property(object, weak=True)

    @objc_method
    def addProvider_(self, sender) -> None:
        """Open Add Provider sheet."""
        inspector = self._inspector
        if inspector and inspector._on_add_provider:
            inspector._on_add_provider()

    @objc_method
    def providerChanged_(self, sender) -> None:
        """Provider selection changed."""
        inspector = self._inspector
        if inspector:
            inspector._update_models()

    @objc_method
    def modelChanged_(self, sender) -> None:
        """Model selection changed."""
        inspector = self._inspector
        if inspector:
            inspector._on_model_change()


# =============================================================================
# Workflow Inspector
# =============================================================================

class WorkflowInspector:
    """Workflow settings inspector.

    Shows:
    - Provider dropdown
    - Model dropdown
    - Add Provider button
    - Run button
    """

    def __init__(
        self,
        width: int = INSPECTOR_WIDTH,
        on_add_provider: Callable[[], None] | None = None,
    ):
        self._width = width
        self._workflow: Workflow | None = None
        self._providers: list[Provider] = []
        self._models: list[Model] = []
        self._on_add_provider = on_add_provider

        # UI references
        self._provider_popup = None
        self._model_popup = None
        self._status_field = None

        # Delegate
        self._delegate = _WorkflowInspectorDelegate.alloc().init()
        self._delegate._inspector = self

        # Build UI
        self._scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (width, 600)))
        self._scroll.hasVerticalScroller = True
        self._scroll.autohidesScrollers = True
        self._scroll.borderType = BORDER_NONE
        self._scroll.backgroundColor = NSColor.windowBackgroundColor
        self._scroll.setAutoresizingMask_(AUTORESIZE_FLEX)

        self._content = _WorkflowInspectorFlippedView.alloc().initWithFrame_(((0, 0), (width, 600)))
        self._scroll.documentView = self._content

        self._build_ui()
        self._load_providers()
        logger.debug("WorkflowInspector created")

    def _build_ui(self):
        """Build the inspector UI."""
        y = 10

        # Workflow section
        y = self._add_section_header("WORKFLOW", y)
        self._provider_popup, y = self._add_popup("Provider", y)
        self._model_popup, y = self._add_popup("Model", y)

        # Add Provider button
        add_btn = NSButton.alloc().initWithFrame_(((10, y), (self._width - 20, 24)))
        add_btn.title = "+ Add Provider"
        add_btn.bezelStyle = 1  # Rounded
        add_btn.setTarget_(self._delegate)
        add_btn.setAction_(SEL("addProvider:"))
        self._content.addSubview_(add_btn)
        y += 34

        y += 10

        # Processing section
        y = self._add_section_header("PROCESSING", y)

        # Status field
        status_label = NSTextField.alloc().initWithFrame_(((10, y), (self._width - 20, 14)))
        status_label.stringValue = "Status"
        status_label.editable = False
        status_label.bordered = False
        status_label.drawsBackground = False
        status_label.font = NSFont.systemFontOfSize_weight_(11, 0.5)
        status_label.textColor = NSColor.secondaryLabelColor
        self._content.addSubview_(status_label)
        y += 16

        self._status_field = NSTextField.alloc().initWithFrame_(((10, y), (self._width - 20, 20)))
        self._status_field.stringValue = "Ready"
        self._status_field.editable = False
        self._status_field.bordered = False
        self._status_field.drawsBackground = False
        self._status_field.font = NSFont.systemFontOfSize_(12)
        self._content.addSubview_(self._status_field)
        y += 30

        # Run button (will be connected to workflow execution)
        run_btn = NSButton.alloc().initWithFrame_(((10, y), (self._width - 20, 32)))
        run_btn.title = "Run Workflow"
        run_btn.bezelStyle = 1  # Rounded
        # run_btn.setTarget_(self._delegate)
        # run_btn.setAction_(SEL("runWorkflow:"))
        self._content.addSubview_(run_btn)
        y += 42

        # Set content size
        self._content.setFrameSize_((self._width, y + 20))

    def _add_section_header(self, title: str, y: int) -> int:
        """Add section header. Returns new y."""
        label = NSTextField.alloc().initWithFrame_(((10, y + 4), (self._width - 20, 16)))
        label.stringValue = title
        label.editable = False
        label.bordered = False
        label.drawsBackground = False
        label.font = NSFont.systemFontOfSize_weight_(11, 0.6)
        label.textColor = NSColor.secondaryLabelColor
        self._content.addSubview_(label)

        divider = NSBox.alloc().initWithFrame_(((10, y + 22), (self._width - 20, 1)))
        divider.boxType = 4  # Separator
        self._content.addSubview_(divider)

        return y + 28

    def _add_popup(self, label_text: str, y: int) -> tuple[Any, int]:
        """Add label + popup button. Returns (popup, new_y)."""
        label = NSTextField.alloc().initWithFrame_(((10, y), (self._width - 20, 14)))
        label.stringValue = label_text
        label.editable = False
        label.bordered = False
        label.drawsBackground = False
        label.font = NSFont.systemFontOfSize_weight_(11, 0.5)
        label.textColor = NSColor.secondaryLabelColor
        self._content.addSubview_(label)

        popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            ((10, y + 16), (self._width - 20, 24)), False
        )
        self._content.addSubview_(popup)

        return popup, y + 48

    @property
    def native(self) -> Any:
        """The native NSScrollView."""
        return self._scroll

    @property
    def workflow(self) -> Workflow | None:
        """Currently loaded workflow."""
        return self._workflow

    def _load_providers(self):
        """Load providers from database."""
        try:
            from fichero.db import db
            from fichero.models import Provider

            self._providers = list(db.query(Provider, enabled=True))
            self._update_provider_popup()
        except Exception as e:
            logger.warning(f"Could not load providers: {e}")
            self._providers = []

    def _update_provider_popup(self):
        """Update provider dropdown items."""
        self._provider_popup.removeAllItems()

        if not self._providers:
            self._provider_popup.addItemWithTitle_("No providers configured")
        else:
            for p in self._providers:
                self._provider_popup.addItemWithTitle_(p.name)

        self._update_models()

    def _update_models(self):
        """Update model dropdown based on selected provider."""
        self._model_popup.removeAllItems()

        if not self._providers:
            self._model_popup.addItemWithTitle_("No models available")
            return

        # Get selected provider
        idx = self._provider_popup.indexOfSelectedItem()
        if idx < 0 or idx >= len(self._providers):
            return

        provider = self._providers[idx]

        # Load models for this provider
        try:
            from fichero.db import db
            from fichero.models import Model

            self._models = list(db.query(Model, provider_id=provider.id))

            if not self._models:
                self._model_popup.addItemWithTitle_("No models available")
            else:
                for m in self._models:
                    self._model_popup.addItemWithTitle_(m.name)
        except Exception as e:
            logger.warning(f"Could not load models: {e}")
            self._model_popup.addItemWithTitle_("Error loading models")

    def _on_model_change(self):
        """Called when model selection changes."""
        # Could save selection to workflow config
        pass

    def load(self, workflow: Workflow | None) -> None:
        """Load a workflow."""
        self._workflow = workflow
        self._load_providers()

        if workflow:
            self._status_field.stringValue = "Ready"
        else:
            self._status_field.stringValue = "No workflow selected"

        logger.debug(f"WorkflowInspector loaded: {workflow}")

    def clear(self) -> None:
        """Clear the inspector."""
        self._workflow = None
        self._status_field.stringValue = "No workflow selected"

    def refresh_providers(self):
        """Reload providers from database."""
        self._load_providers()

    @property
    def selected_provider(self) -> Provider | None:
        """Get currently selected provider."""
        idx = self._provider_popup.indexOfSelectedItem()
        if idx >= 0 and idx < len(self._providers):
            return self._providers[idx]
        return None

    @property
    def selected_model(self) -> Model | None:
        """Get currently selected model."""
        idx = self._model_popup.indexOfSelectedItem()
        if idx >= 0 and idx < len(self._models):
            return self._models[idx]
        return None
