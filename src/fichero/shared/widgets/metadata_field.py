"""
MetadataFieldWidget

A single editable metadata field with label and text input.
Used in the Preview Metadata Pane for editing catalogue fields.
Tinderbox-style: horizontal layout with label on left, value on right.
"""

import logging
from typing import Optional, Callable

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN

logger = logging.getLogger(__name__)


class MetadataFieldWidget:
    """
    Single editable metadata field: Label + TextInput in horizontal row.

    Structure:
    [Box: container (ROW)]
      [Label: field_label]  [TextInput: field_input]

    For multiline fields:
    [Box: container (COLUMN)]
      [Label: field_label]
      [MultilineTextInput: field_input]
    """

    LABEL_COLOR = "#666"
    LABEL_FONT_SIZE = 8
    LABEL_FONT_SIZE_MOBILE = 9
    LABEL_WIDTH = 70  # Fixed width for alignment
    LABEL_WIDTH_MOBILE = 90
    ROW_HEIGHT = 18
    ROW_HEIGHT_MOBILE = 26

    def __init__(
        self,
        field_key: str,
        label: str,
        value: str = "",
        editable: bool = True,
        multiline: bool = False,
        on_change: Optional[Callable[[str, str], None]] = None,
        is_mobile: bool = False
    ):
        """
        Initialize metadata field widget.

        Args:
            field_key: Unique key for this field (e.g., "title", "date")
            label: Display label
            value: Initial value
            editable: Whether field can be edited
            multiline: Whether to use multiline input
            on_change: Callback(field_key, new_value) when value changes
            is_mobile: Whether running on mobile (larger touch targets)
        """
        self.field_key = field_key
        self.on_change = on_change
        self._original_value = value
        self._is_dirty = False
        self.is_mobile = is_mobile
        self.multiline = multiline

        # Adjust sizes for mobile
        label_size = self.LABEL_FONT_SIZE_MOBILE if is_mobile else self.LABEL_FONT_SIZE
        label_width = self.LABEL_WIDTH_MOBILE if is_mobile else self.LABEL_WIDTH
        row_height = self.ROW_HEIGHT_MOBILE if is_mobile else self.ROW_HEIGHT

        # Multiline fields use vertical layout
        if multiline:
            self.container = toga.Box(style=Pack(
                direction=COLUMN,
                margin=(0, 2)
            ))

            self.field_label = toga.Label(
                label,
                style=Pack(
                    font_size=label_size,
                    color=self.LABEL_COLOR,
                    margin_bottom=2
                )
            )

            self.field_input = toga.MultilineTextInput(
                value=value,
                readonly=not editable,
                on_change=self._on_input_change,
                style=Pack(
                    height=60,
                    flex=1
                )
            )

            self.container.add(self.field_label)
            self.container.add(self.field_input)
        else:
            # Horizontal layout: [Label] [Value]
            self.container = toga.Box(style=Pack(
                direction=ROW,
                height=row_height,
                margin=(0, 2)
            ))

            # Label with fixed width for alignment
            self.field_label = toga.Label(
                label,
                style=Pack(
                    font_size=label_size,
                    color=self.LABEL_COLOR if editable else "#999",
                    width=label_width,
                    margin=(1, 2, 1, 0)
                )
            )

            # Input field
            self.field_input = toga.TextInput(
                value=value,
                readonly=not editable,
                on_change=self._on_input_change,
                style=Pack(
                    font_size=label_size,
                    flex=1,
                    height=row_height
                )
            )

            self.container.add(self.field_label)
            self.container.add(self.field_input)

        logger.debug(f"MetadataFieldWidget '{field_key}' created")

    def get_value(self) -> str:
        """Get current field value."""
        return self.field_input.value or ""

    def set_value(self, value: str):
        """
        Set field value.

        Args:
            value: New value (None is converted to empty string)
        """
        self.field_input.value = value or ""
        self._original_value = value or ""
        self._is_dirty = False

    def set_editable(self, editable: bool):
        """
        Set whether field is editable.

        Args:
            editable: True to allow editing, False for read-only
        """
        self.field_input.readonly = not editable
        # Update label color to indicate editability
        if not self.multiline:
            self.field_label.style.color = self.LABEL_COLOR if editable else "#999"

    @property
    def is_dirty(self) -> bool:
        """Check if value has been modified."""
        return self._is_dirty

    def reset_dirty(self):
        """Clear dirty flag and update original value to current."""
        self._original_value = self.get_value()
        self._is_dirty = False

    def revert(self):
        """Revert to original value."""
        self.field_input.value = self._original_value
        self._is_dirty = False

    def _on_input_change(self, widget):
        """Handle input value change."""
        current_value = widget.value or ""
        self._is_dirty = current_value != self._original_value

        if self.on_change:
            self.on_change(self.field_key, current_value)

    def set_label(self, label: str):
        """
        Update the field label.

        Args:
            label: New label text
        """
        self.field_label.text = label

    def focus(self):
        """Focus the input field."""
        try:
            self.field_input.focus()
        except Exception:
            pass  # Not all backends support focus
