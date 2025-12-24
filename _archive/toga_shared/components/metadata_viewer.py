"""
MetadataViewer Component

Reusable metadata display component inspired by inspector pattern.
Displays key-value pairs with support for nested dictionaries.
"""

import toga
from toga.style import Pack
from typing import Dict, Any, Optional


class MetadataViewer:
    """
    Reusable metadata viewer component for displaying structured metadata.

    Follows inspector pattern:
    - Update without recreating widgets via set_metadata()
    - Return toga.Box for composition
    - Self-contained and reusable

    Example usage:
        viewer = MetadataViewer("Step Information")
        viewer.set_metadata({
            'Step Name': 'prepare_images',
            'File Type': 'image',
            'Processing Details': {
                'Time': '1.23s',
                'Status': 'completed'
            }
        })
        container.add(viewer.as_box())
    """

    def __init__(self, title: str = "Metadata"):
        """
        Initialize metadata viewer.

        Args:
            title: Title displayed at top of viewer
        """
        self.title = title
        self._metadata: Dict[str, Any] = {}
        self._container = None
        self._build_ui()

    def _build_ui(self):
        """Build the UI components"""
        # Title label
        self._title_label = toga.Label(
            self.title,
            style=Pack(
                font_size=14,
                font_weight='bold',
                margin_bottom=10
            )
        )

        # Scrollable content container
        self._content_box = toga.Box(
            style=Pack(
                direction='column',
                margin=0
            )
        )

        # Main container with title and scrollable content
        self._container = toga.Box(
            style=Pack(
                direction='column',
                margin=10,
                flex=1
            )
        )
        self._container.add(self._title_label)

        # Add scroll container for content
        self._scroll_container = toga.ScrollContainer(
            content=self._content_box,
            style=Pack(flex=1)
        )
        self._container.add(self._scroll_container)

    def set_metadata(self, metadata: Dict[str, Any]):
        """
        Load metadata to display.

        Args:
            metadata: Dictionary of metadata key-value pairs
        """
        self._metadata = metadata or {}
        self._refresh_display()

    def clear(self):
        """Clear all metadata"""
        self._metadata = {}
        self._refresh_display()

    def as_box(self) -> toga.Box:
        """Return the component as a Toga Box for embedding"""
        return self._container

    def _refresh_display(self):
        """Refresh the metadata display without recreating widgets"""
        # Clear existing content
        self._content_box.clear()

        if not self._metadata:
            # Show empty state
            empty_label = toga.Label(
                "No metadata available",
                style=Pack(
                    color='#999999',
                    font_style='italic',
                    margin=10
                )
            )
            self._content_box.add(empty_label)
            return

        # Render metadata
        self._render_metadata(self._content_box, self._metadata, level=0)

    def _render_metadata(self, container: toga.Box, data: Any, level: int = 0):
        """
        Recursively render metadata with proper formatting.

        Args:
            container: Container to add widgets to
            data: Metadata to render (dict, list, or primitive)
            level: Nesting level for indentation
        """
        if isinstance(data, dict):
            for key, value in data.items():
                self._render_key_value(container, key, value, level)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._render_key_value(container, f"[{i}]", item, level)
        else:
            # Primitive value
            self._render_primitive(container, data, level)

    def _render_key_value(self, container: toga.Box, key: str, value: Any, level: int):
        """
        Render a single key-value pair.

        Args:
            container: Container to add widgets to
            key: Metadata key
            value: Metadata value
            level: Nesting level for indentation
        """
        indent = level * 20

        if isinstance(value, dict):
            # Section header for nested dict
            section_box = toga.Box(
                style=Pack(
                    direction='column',
                    margin_left=indent,
                    margin_top=10 if level == 0 else 5
                )
            )

            # Section title
            section_label = toga.Label(
                str(key),
                style=Pack(
                    font_weight='bold',
                    font_size=12,
                    margin_bottom=5
                )
            )
            section_box.add(section_label)

            # Render nested content
            nested_box = toga.Box(style=Pack(direction='column', margin_left=10))
            self._render_metadata(nested_box, value, level + 1)
            section_box.add(nested_box)

            container.add(section_box)

        elif isinstance(value, list):
            # List section
            list_box = toga.Box(
                style=Pack(
                    direction='column',
                    margin_left=indent,
                    margin_top=5
                )
            )

            # List title
            list_label = toga.Label(
                f"{key}:",
                style=Pack(
                    font_weight='bold',
                    font_size=11,
                    margin_bottom=3
                )
            )
            list_box.add(list_label)

            # Render list items
            for i, item in enumerate(value):
                item_box = toga.Box(
                    style=Pack(
                        direction='row',
                        margin_left=10,
                        margin_top=2
                    )
                )

                bullet = toga.Label(
                    "•",
                    style=Pack(margin_right=5)
                )
                item_text = toga.Label(
                    self._format_value(item),
                    style=Pack(flex=1)
                )

                item_box.add(bullet)
                item_box.add(item_text)
                list_box.add(item_box)

            container.add(list_box)

        else:
            # Simple key-value pair
            row_box = toga.Box(
                style=Pack(
                    direction='row',
                    margin_left=indent,
                    margin_top=3
                )
            )

            key_label = toga.Label(
                f"{key}:",
                style=Pack(
                    font_weight='bold',
                    font_size=11,
                    width=150
                )
            )

            value_label = toga.Label(
                self._format_value(value),
                style=Pack(
                    flex=1,
                    font_size=11
                )
            )

            row_box.add(key_label)
            row_box.add(value_label)
            container.add(row_box)

    def _render_primitive(self, container: toga.Box, value: Any, level: int):
        """
        Render a primitive value directly.

        Args:
            container: Container to add widgets to
            value: Primitive value to render
            level: Nesting level for indentation
        """
        indent = level * 20
        value_label = toga.Label(
            self._format_value(value),
            style=Pack(
                margin_left=indent,
                margin_top=3,
                font_size=11
            )
        )
        container.add(value_label)

    def _format_value(self, value: Any) -> str:
        """
        Format a value for display.

        Args:
            value: Value to format

        Returns:
            Formatted string representation
        """
        if value is None:
            return "(None)"
        elif isinstance(value, bool):
            return "Yes" if value else "No"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            # Truncate very long strings
            max_length = 100
            if len(value) > max_length:
                return value[:max_length] + "..."
            return value
        else:
            # Fallback for other types
            return str(value)
