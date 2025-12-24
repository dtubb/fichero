"""
TagFieldWidget - macOS-style tag/pill display for metadata values

DEPRECATED: Use TokenFieldWidget from fichero.shared.widgets.token_field instead.
This module is kept for backwards compatibility.

Displays values as clickable pale blue rounded pills (like macOS Finder tags).
Tags can be clicked to trigger a search or other action.

Features:
- Pale blue (#E8F4FD) rounded pill background
- Dark text (#1A73E8) for contrast
- Click handler for search integration
- Wrapping flow layout for multiple tags
- Edit mode with semicolon-separated input
"""

import logging
from typing import Optional, List, Callable

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN, CENTER

logger = logging.getLogger(__name__)

# Tag colors (macOS-inspired pale blue)
TAG_BACKGROUND = '#E8F4FD'  # Pale blue background
TAG_TEXT_COLOR = '#1A73E8'  # Darker blue text
TAG_BORDER_COLOR = '#B8D4F0'  # Subtle border
TAG_HOVER_BG = '#D0E8FA'  # Slightly darker on hover


class TagFieldWidget:
    """
    A widget that displays values as clickable tag pills.

    Usage:
        tag_field = TagFieldWidget(
            values=["1931", "Istmina", "Antonio Asprilla"],
            on_tag_click=lambda tag: search_for(tag),
            editable=True
        )
        container.add(tag_field.container)
    """

    def __init__(
        self,
        values: List[str] = None,
        on_tag_click: Callable[[str], None] = None,
        editable: bool = False,
        on_change: Callable[[List[str]], None] = None,
        placeholder: str = "No values",
        max_width: int = None
    ):
        """
        Initialize tag field widget.

        Args:
            values: List of tag values to display
            on_tag_click: Callback when a tag is clicked (receives tag text)
            editable: If True, shows edit button to modify tags
            on_change: Callback when tags are modified (receives new list)
            placeholder: Text to show when no values
            max_width: Maximum width for the container (for wrapping)
        """
        self.values = values or []
        self.on_tag_click = on_tag_click
        self.editable = editable
        self.on_change = on_change
        self.placeholder = placeholder
        self.max_width = max_width

        # State
        self._is_editing = False
        self._edit_input: Optional[toga.TextInput] = None

        # Build UI
        self._create_ui()
        self._refresh_tags()

    def _create_ui(self):
        """Create the widget UI structure."""
        # Main container - uses COLUMN for wrapping rows of tags
        self.container = toga.Box(style=Pack(
            direction=COLUMN,
            flex=1
        ))

        # Tags display area - wrapping flow of tag pills
        self.tags_box = toga.Box(style=Pack(
            direction=ROW,
            flex=1
        ))
        self.container.add(self.tags_box)

        # Edit input (hidden by default)
        if self.editable:
            self._edit_input = toga.TextInput(
                placeholder="Enter values separated by semicolons",
                on_confirm=self._on_edit_confirm,
                style=Pack(flex=1, visibility='hidden', height=0)
            )
            self.container.add(self._edit_input)

    def _refresh_tags(self):
        """Rebuild the tag pills display."""
        self.tags_box.clear()

        if not self.values:
            # Show placeholder
            placeholder_label = toga.Label(
                self.placeholder,
                style=Pack(
                    color='#999',
                    font_size=9,
                    margin=(2, 4)
                )
            )
            self.tags_box.add(placeholder_label)
            return

        # Create a tag pill for each value
        for value in self.values:
            if value and str(value).strip():
                tag = self._create_tag_pill(str(value).strip())
                self.tags_box.add(tag)

    def _create_tag_pill(self, text: str) -> toga.Box:
        """Create a single tag pill widget styled like macOS Finder tags.

        Uses a pale blue background box with a clickable button inside.
        The button text provides the tag content.
        """
        # Outer container - pale blue pill background
        pill = toga.Box(style=Pack(
            direction=ROW,
            background_color=TAG_BACKGROUND,
            margin=(2, 4, 2, 0),
            padding=(1, 6, 1, 6),  # Padding inside pill
            align_items=CENTER
        ))

        # Clickable button with the tag text
        # Note: On macOS, buttons have their own chrome, so we keep it minimal
        tag_button = toga.Button(
            text,
            on_press=lambda w, t=text: self._handle_tag_click(t),
            style=Pack(
                font_size=10,
                height=20,
                padding=0,
                margin=0
            )
        )
        pill.add(tag_button)

        return pill

    def _handle_tag_click(self, tag_text: str):
        """Handle click on a tag."""
        logger.debug(f"Tag clicked: {tag_text}")
        if self.on_tag_click:
            self.on_tag_click(tag_text)

    def _on_edit_confirm(self, widget):
        """Handle edit input confirmation."""
        if self._edit_input:
            # Parse semicolon-separated values
            raw_text = self._edit_input.value or ""
            new_values = [v.strip() for v in raw_text.split(';') if v.strip()]

            self.values = new_values
            self._refresh_tags()

            # Hide edit input
            self._is_editing = False
            self._edit_input.style.visibility = 'hidden'
            self._edit_input.style.height = 0

            # Notify change
            if self.on_change:
                self.on_change(self.values)

    def start_editing(self):
        """Enter edit mode."""
        if not self.editable or not self._edit_input:
            return

        self._is_editing = True
        # Populate with current values as semicolon list
        self._edit_input.value = '; '.join(self.values)
        self._edit_input.style.visibility = 'visible'
        self._edit_input.style.height = 28
        self._edit_input.focus()

    def set_values(self, values: List[str]):
        """Update the displayed values."""
        self.values = values or []
        self._refresh_tags()

    def get_values(self) -> List[str]:
        """Get current values."""
        return self.values.copy()


class TagDisplayRow:
    """
    A single row combining a label and tag field for Inspector-style display.

    Layout: [Label:] [Tag1] [Tag2] [Tag3]
    """

    def __init__(
        self,
        label: str,
        values: List[str] = None,
        on_tag_click: Callable[[str], None] = None,
        label_width: int = 80
    ):
        """
        Initialize a tag display row.

        Args:
            label: Label text (e.g., "Location", "People")
            values: List of tag values
            on_tag_click: Callback when tag is clicked
            label_width: Width of the label column
        """
        self.label = label
        self.values = values or []
        self.on_tag_click = on_tag_click
        self.label_width = label_width

        self._create_ui()

    def _create_ui(self):
        """Create the row UI."""
        self.container = toga.Box(style=Pack(
            direction=ROW,
            margin_bottom=4,
            align_items='start'
        ))

        # Label (right-aligned like Inspector)
        label_widget = toga.Label(
            f"{self.label}:",
            style=Pack(
                width=self.label_width,
                text_align='right',
                margin_right=8,
                font_size=9,
                color='#666'
            )
        )
        self.container.add(label_widget)

        # Tag field
        self.tag_field = TagFieldWidget(
            values=self.values,
            on_tag_click=self.on_tag_click,
            placeholder="—"
        )
        self.container.add(self.tag_field.container)

    def set_values(self, values: List[str]):
        """Update tag values."""
        self.values = values or []
        self.tag_field.set_values(self.values)


def parse_metadata_value(value) -> List[str]:
    """
    Parse a metadata value into a list of tags.

    Handles:
    - Single string: "value" -> ["value"]
    - JSON array: ["a", "b"] -> ["a", "b"]
    - Semicolon list: "a; b; c" -> ["a", "b", "c"]
    - Comma list: "a, b, c" -> ["a", "b", "c"]
    """
    if value is None:
        return []

    if isinstance(value, list):
        return [str(v).strip() for v in value if v]

    value_str = str(value).strip()

    if not value_str:
        return []

    # Try semicolon split first
    if ';' in value_str:
        return [v.strip() for v in value_str.split(';') if v.strip()]

    # Try comma split (but only if it looks like a list, not a sentence)
    if ',' in value_str and len(value_str) < 200:
        parts = [v.strip() for v in value_str.split(',') if v.strip()]
        # Only use comma split if parts are short (likely a list, not prose)
        if all(len(p) < 50 for p in parts):
            return parts

    # Single value
    return [value_str]
