"""
FieldSelectorDialog

Simple dialog for selecting which metadata fields to display.
Shows fields grouped by category with checkboxes.
"""

import logging
from typing import List, Callable, Dict

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

logger = logging.getLogger(__name__)

# Category display names
CATEGORY_LABELS = {
    "catalogue": "Catalogue",
    "transcription": "Transcription",
    "external_iiif": "External Source",
    "file_info": "File Info",
    "discovered": "Discovered",  # Dynamic fields from processing tools
}


class FieldSelectorDialog:
    """
    Dialog for selecting visible metadata fields.

    Shows fields grouped by category (schema_type) with checkboxes.
    """

    DIALOG_WIDTH = 300
    DIALOG_HEIGHT = 450

    def __init__(
        self,
        app,
        available_fields: List['FieldInfo'],
        selected_fields: List[str],
        on_selection_changed: Callable[[List[str]], None],
        parent_window=None
    ):
        """
        Initialize field selector dialog.

        Args:
            app: Toga application instance
            available_fields: List of FieldInfo for all available fields
            selected_fields: List of currently selected field keys
            on_selection_changed: Callback with new field list on Done
            parent_window: Optional parent window
        """
        self.app = app
        self.all_fields = available_fields
        self.selected_keys = set(selected_fields)
        self.on_selection_changed = on_selection_changed
        self.parent_window = parent_window

        # Group fields by category
        self.fields_by_category: Dict[str, List] = {}
        for field in available_fields:
            category = field.schema_type
            if category not in self.fields_by_category:
                self.fields_by_category[category] = []
            self.fields_by_category[category].append(field)

        # Checkbox widgets (keyed by field key)
        self.checkboxes = {}

        # Build UI
        self._build_ui()
        self.window = None

    def _build_ui(self):
        """Build the dialog UI."""
        # Main container
        self.content = toga.Box(style=Pack(
            direction=COLUMN,
            margin=15
        ))

        # Title
        title = toga.Label(
            "Show Fields",
            style=Pack(
                font_weight="bold",
                font_size=12,
                margin_bottom=10
            )
        )
        self.content.add(title)

        # Scrollable area for checkboxes
        scroll_content = toga.Box(style=Pack(
            direction=COLUMN,
            flex=1
        ))

        # Add fields grouped by category
        category_order = ["catalogue", "transcription", "external_iiif", "file_info", "discovered"]

        for category in category_order:
            if category not in self.fields_by_category:
                continue

            fields = self.fields_by_category[category]
            if not fields:
                continue

            # Category header
            category_label = CATEGORY_LABELS.get(category, category.title())
            header = toga.Label(
                category_label,
                style=Pack(
                    font_weight="bold",
                    font_size=10,
                    color="#666",
                    margin_top=8,
                    margin_bottom=4
                )
            )
            scroll_content.add(header)

            # Checkboxes for this category
            for field in fields:
                checkbox = toga.Switch(
                    field.label,
                    value=field.key in self.selected_keys,
                    style=Pack(margin=(1, 0, 1, 10))
                )
                self.checkboxes[field.key] = checkbox
                scroll_content.add(checkbox)

        # Wrap in scroll container
        scroll_container = toga.ScrollContainer(
            content=scroll_content,
            style=Pack(flex=1)
        )
        self.content.add(scroll_container)

        # Bottom buttons: Cancel and Done
        button_box = toga.Box(style=Pack(
            direction=ROW,
            margin_top=10
        ))

        # Spacer
        spacer = toga.Box(style=Pack(flex=1))
        button_box.add(spacer)

        cancel_btn = toga.Button(
            "Cancel",
            on_press=self._on_cancel,
            style=Pack(width=70, height=28, margin_right=8)
        )
        button_box.add(cancel_btn)

        done_btn = toga.Button(
            "Done",
            on_press=self._on_done,
            style=Pack(width=70, height=28)
        )
        button_box.add(done_btn)

        self.content.add(button_box)

    def _on_cancel(self, widget):
        """Close dialog without applying changes."""
        if self.window:
            self.window.close()
        logger.debug("Field selector cancelled")

    def _on_done(self, widget):
        """Apply changes and close dialog."""
        # Collect checked fields (in original order)
        selected = [
            field.key
            for field in self.all_fields
            if self.checkboxes[field.key].value
        ]

        # Call callback with selected fields
        self.on_selection_changed(selected)

        if self.window:
            self.window.close()
        logger.debug(f"Field selector applied: {selected}")

    def show(self):
        """Show the dialog."""
        self.window = toga.Window(
            title="Show Fields",
            size=(self.DIALOG_WIDTH, self.DIALOG_HEIGHT)
        )
        self.window.content = self.content
        self.window.show()
        logger.debug("Field selector dialog shown")

    def close(self):
        """Close the dialog."""
        if self.window:
            self.window.close()
            self.window = None
