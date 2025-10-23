"""
Inspector Window - Desktop Window Implementation

Preview-style tabbed inspector that displays metadata about the currently selected item.
"""

import logging
from typing import Optional, Dict, Any
import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
from toga.colors import TRANSPARENT

logger = logging.getLogger(__name__)


class InspectorWindow:
    """Desktop inspector window that displays metadata for the current selection"""

    def __init__(self, app):
        """Initialize the inspector window"""
        self.app = app
        self.window: Optional[toga.Window] = None
        self.is_visible = False
        self.option_container: Optional[toga.OptionContainer] = None

        # Store the current selection data
        self.current_selection_type: str = None  # "COLLECTION", "ITEM", "FOLDER"
        self.current_metadata: Dict[str, Any] = {}

        # Fixed tab content containers (these get updated, not recreated)
        self.general_container: Optional[toga.Box] = None
        self.storage_container: Optional[toga.Box] = None
        self.details_container: Optional[toga.Box] = None

        logger.info("InspectorWindow initialized")

    def show(self):
        """Show the inspector window"""
        if self.window is None:
            self._create_window()

        if not self.is_visible:
            self.window.show()
            self.is_visible = True

            # Update content with current selection
            self.refresh()

            logger.info("Inspector window shown")

    def hide(self):
        """Hide the inspector window"""
        if self.window and self.is_visible:
            self.window.hide()
            self.is_visible = False
            logger.info("Inspector window hidden")

    def close(self):
        """Close the inspector window"""
        if self.window:
            self.window.close()
            self.window = None
            self.option_container = None
            self.is_visible = False
            logger.info("Inspector window closed")

    def refresh(self):
        """Refresh the inspector content with current selection"""
        try:
            if not self.option_container:
                return

            # Rebuild tabs based on current selection type and metadata
            self._rebuild_tabs()

            logger.debug("Inspector content refreshed")

        except Exception as e:
            logger.error(f"Failed to refresh inspector: {e}")

    def update_metadata(self, metadata: str, selection_type: str = None):
        """Update the metadata and refresh display if visible

        Args:
            metadata: The metadata string (will be parsed if from old format)
            selection_type: Type of selection (e.g., "COLLECTION", "ITEM")
        """
        try:
            logger.info(f"🔍 Inspector.update_metadata called: type={selection_type}, is_visible={self.is_visible}")
            logger.debug(f"Metadata text: {metadata[:200]}...")  # First 200 chars

            self.current_selection_type = selection_type

            # For now, parse the text metadata into dict
            # TODO: Views should pass structured data instead of text
            self.current_metadata = self._parse_metadata_text(metadata)
            logger.info(f"Parsed metadata sections: {list(self.current_metadata.keys())}")

            # If inspector is visible, update the display immediately
            if self.is_visible and self.option_container:
                logger.info("Inspector is visible, rebuilding tabs...")
                self._rebuild_tabs()
                logger.info(f"Tabs rebuilt. Current tab count: {len(self.option_container.content)}")
            else:
                logger.info(f"Inspector not visible or no container (visible={self.is_visible}, container={self.option_container is not None})")
        except Exception as e:
            logger.error(f"Failed to update metadata: {e}", exc_info=True)

    def _parse_metadata_text(self, text: str) -> Dict[str, Any]:
        """Parse the text metadata into a dictionary

        This is a temporary solution until views pass structured data
        """
        metadata = {}
        current_section = None

        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Section headers
            if line.startswith('===') and line.endswith('==='):
                current_section = line.strip('= ').lower().replace(' ', '_')
                metadata[current_section] = {}
            # Key-value pairs
            elif ':' in line and current_section:
                key, value = line.split(':', 1)
                metadata[current_section][key.strip()] = value.strip()

        return metadata

    def _rebuild_tabs(self):
        """Update tab content based on current selection type

        Tabs are fixed and never deleted/recreated - we just update their content
        """
        if not self.general_container or not self.storage_container or not self.details_container:
            logger.warning("Tab containers not initialized")
            return

        # Clear current content from all containers
        self.general_container.clear()
        self.storage_container.clear()
        self.details_container.clear()

        # Update content based on selection type
        if self.current_selection_type == "COLLECTION":
            self._update_collection_content()
        elif self.current_selection_type == "ITEM":
            self._update_item_content()
        elif self.current_selection_type == "STEP":
            self._update_step_content()
        else:
            self._update_no_selection_content()

    def _update_collection_content(self):
        """Update tab content for collection selection - show EVERYTHING"""
        # General tab - basic info
        general_rows = [
            ("Collection name:", self.current_metadata.get('collection_metadata', {}).get('Name', 'Unknown')),
            ("Collection ID:", self.current_metadata.get('collection_metadata', {}).get('ID', 'N/A')),
            ("", ""),
            ("Collection type:", self.current_metadata.get('storage', {}).get('Location', 'Unknown')),
            ("", ""),
            ("Created:", self.current_metadata.get('dates', {}).get('Created', 'N/A')),
            ("Modified:", self.current_metadata.get('dates', {}).get('Modified', 'N/A')),
        ]

        # Add description in General if available
        description = self.current_metadata.get('description', {}).get('DESCRIPTION', '')
        if description and description != 'Unknown':
            general_rows.append(("", ""))
            general_rows.append(("Description:", description))

        self._add_rows_to_container(self.general_container, general_rows)

        # Storage tab - ALL storage/path information
        storage_metadata = self.current_metadata.get('storage', {})

        storage_rows = [
            ("Storage type:", storage_metadata.get('Location', 'Unknown')),
            ("", ""),
        ]

        # Show ALL paths
        if 'Source' in storage_metadata and storage_metadata.get('Source'):
            storage_rows.append(("Source path:", storage_metadata.get('Source', '')))

        if 'Workspace' in storage_metadata and storage_metadata.get('Workspace'):
            storage_rows.append(("Workspace path:", storage_metadata.get('Workspace', '')))

        # Show any other metadata we might have
        contents_metadata = self.current_metadata.get('contents', {})
        total_items = contents_metadata.get('Total Items', '0')

        if total_items != '0':
            storage_rows.append(("", ""))
            storage_rows.append(("Total items:", total_items))

        self._add_rows_to_container(self.storage_container, storage_rows)

        # Details tab - item breakdown and processing info
        contents_metadata = self.current_metadata.get('contents', {})
        details_rows = []

        # Item breakdown (no emojis)
        total = contents_metadata.get('Total Items', '0')
        if total != '0':
            details_rows.append(("Total items:", total))
            details_rows.append(("", ""))

            # Extract emoji keys and show without emoji
            if '📁 Copied' in contents_metadata:
                details_rows.append(("Copied:", contents_metadata.get('📁 Copied', '0')))
            if '🔗 Linked' in contents_metadata:
                details_rows.append(("Linked:", contents_metadata.get('🔗 Linked', '0')))
            if '🌐 URLs' in contents_metadata:
                details_rows.append(("URLs:", contents_metadata.get('🌐 URLs', '0')))
        else:
            details_rows.append(("Items:", "No items"))

        # TODO: Add processing information when available
        # details_rows.append(("", ""))
        # details_rows.append(("Processing status:", "..."))
        # details_rows.append(("Completed:", "..."))
        # details_rows.append(("Pending:", "..."))

        self._add_rows_to_container(self.details_container, details_rows)

    def _update_item_content(self):
        """Update tab content for item selection - show EVERYTHING"""
        # Parse all available metadata from the text format
        # The metadata comes as a text dump, so we'll display it all

        # General tab - basic item info
        general_rows = []
        if 'item_metadata' in self.current_metadata or 'file_metadata' in self.current_metadata:
            # Try to extract what we can
            for section_name, section_data in self.current_metadata.items():
                if isinstance(section_data, dict):
                    for key, value in section_data.items():
                        general_rows.append((f"{key}:", str(value)))
        else:
            # Fallback: show raw metadata
            general_rows.append(("Info:", "Item selected"))

        if general_rows:
            self._add_rows_to_container(self.general_container, general_rows)
        else:
            self._add_text_to_container(self.general_container, "Item information")

        # Storage tab - paths and location
        storage_rows = []
        for section_name, section_data in self.current_metadata.items():
            if isinstance(section_data, dict) and ('path' in str(section_data).lower() or 'location' in str(section_data).lower()):
                for key, value in section_data.items():
                    if 'path' in key.lower() or 'location' in key.lower():
                        storage_rows.append((f"{key}:", str(value)))

        if storage_rows:
            self._add_rows_to_container(self.storage_container, storage_rows)
        else:
            self._add_text_to_container(self.storage_container, "Storage info")

        # Details tab - everything else
        details_text = ""
        for section_name, section_data in self.current_metadata.items():
            details_text += f"=== {section_name.upper()} ===\n"
            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    details_text += f"{key}: {value}\n"
            else:
                details_text += f"{section_data}\n"
            details_text += "\n"

        if details_text:
            self._add_text_to_container(self.details_container, details_text.strip())
        else:
            self._add_text_to_container(self.details_container, "No additional details")

    def _update_step_content(self):
        """Update tab content for workflow step selection"""
        # General tab - step info
        step_metadata = self.current_metadata.get('step_metadata', {})
        general_rows = [
            ("Tool name:", step_metadata.get('Tool Name', 'Unknown')),
            ("Step number:", step_metadata.get('Step Number', 'N/A')),
            ("Status:", step_metadata.get('Status', 'N/A')),
        ]
        self._add_rows_to_container(self.general_container, general_rows)

        # Storage tab - file information
        files_metadata = self.current_metadata.get('files', {})
        storage_rows = [
            ("File count:", files_metadata.get('File Count', '0')),
        ]
        if 'First File' in files_metadata:
            storage_rows.append(("First file:", files_metadata.get('First File', '')))
        self._add_rows_to_container(self.storage_container, storage_rows)

        # Details tab - timing information
        timing_metadata = self.current_metadata.get('timing', {})
        details_rows = []
        if 'Start Time' in timing_metadata:
            details_rows.append(("Start time:", timing_metadata.get('Start Time', '')))
        if 'End Time' in timing_metadata:
            details_rows.append(("End time:", timing_metadata.get('End Time', '')))
        if 'Duration' in timing_metadata:
            details_rows.append(("Duration:", timing_metadata.get('Duration', '')))

        if details_rows:
            self._add_rows_to_container(self.details_container, details_rows)
        else:
            self._add_text_to_container(self.details_container, "No timing information")

    def _update_no_selection_content(self):
        """Update tab content when nothing is selected"""
        self._add_text_to_container(self.general_container, "No selection")
        self._add_text_to_container(self.storage_container, "No selection")
        self._add_text_to_container(self.details_container, "No selection")

    def _add_rows_to_container(self, container, rows):
        """Add Preview-style rows to a container

        Always use two-column layout: label on left, value on right
        For long values, use multiline text box that grows as needed
        """
        for label, value in rows:
            if not label and not value:
                # Spacer
                container.add(toga.Box(style=Pack(height=8)))
            else:
                value_str = str(value)

                # Create horizontal row for label + value
                row = toga.Box(style=Pack(direction=ROW, padding_bottom=3, alignment='top'))

                # Label (right-aligned, fixed width)
                label_widget = toga.Label(
                    label,
                    style=Pack(
                        width=110,
                        text_align='right',
                        padding_right=8,
                        font_size=8
                    )
                )

                # Value side (uses multiline for long text, label for short)
                # Collection IDs (UUIDs) are ~36 chars, so use 30 as threshold
                if len(value_str) > 30:
                    # Long value: multiline text box that wraps
                    # Calculate height based on content length
                    # Assume ~165px available width (300px window - 110px label - margins)
                    chars_per_line = 22  # Conservative estimate at 8pt font
                    estimated_lines = (len(value_str) + chars_per_line - 1) // chars_per_line
                    estimated_lines = max(2, min(10, estimated_lines))  # Between 2-10 lines
                    text_height = estimated_lines * 16  # 16px per line for comfortable spacing

                    value_widget = toga.MultilineTextInput(
                        value=value_str,
                        readonly=True,
                        style=Pack(
                            flex=1,
                            height=text_height,
                            font_size=8,
                            padding=2,
                            background_color=TRANSPARENT  # Transparent background
                        )
                    )
                else:
                    # Short value: simple label
                    value_widget = toga.Label(
                        value_str,
                        style=Pack(
                            flex=1,
                            text_align='left',
                            font_size=8
                        )
                    )

                row.add(label_widget)
                row.add(value_widget)
                container.add(row)

    def _add_text_to_container(self, container, text):
        """Add simple text to a container"""
        label = toga.Label(
            text,
            style=Pack(padding=20, text_align='center', font_size=8)
        )
        container.add(label)

    def _create_info_rows(self, rows):
        """Create a Preview-style two-column layout for info rows

        Args:
            rows: List of (label, value) tuples
        """
        container = toga.Box(style=Pack(direction=COLUMN, padding=10))

        for label, value in rows:
            if not label and not value:
                # Spacer
                container.add(toga.Box(style=Pack(height=10)))
            else:
                row = toga.Box(style=Pack(direction=ROW, padding_bottom=5))

                # Label (right-aligned)
                label_widget = toga.Label(
                    label,
                    style=Pack(
                        width=140,
                        text_align='right',
                        padding_right=10,
                        font_size=9
                    )
                )

                # Value (left-aligned)
                value_widget = toga.Label(
                    value,
                    style=Pack(
                        flex=1,
                        text_align='left',
                        font_size=9
                    )
                )

                row.add(label_widget)
                row.add(value_widget)
                container.add(row)

        # Wrap in ScrollContainer
        scroll = toga.ScrollContainer(
            content=container,
            style=Pack(flex=1)
        )

        return scroll

    def _create_multiline_text(self, text):
        """Create a multiline text widget (fallback for unparsed data)"""
        text_widget = toga.MultilineTextInput(
            value=text,
            readonly=True,
            style=Pack(flex=1, font_family='monospace', font_size=9)
        )

        box = toga.Box(
            style=Pack(direction=COLUMN, flex=1, padding=10),
            children=[text_widget]
        )

        return box

    def _create_window(self):
        """Create the inspector window with fixed tabs"""
        try:
            # Create OptionContainer for tabs (it has its own native background)
            # Add small margins on all sides
            self.option_container = toga.OptionContainer(
                style=Pack(flex=1, padding=10)
            )

            # Create fixed containers for each tab - use TRANSPARENT background
            self.general_container = toga.Box(
                style=Pack(direction=COLUMN, padding=10, background_color=TRANSPARENT)
            )
            self.storage_container = toga.Box(
                style=Pack(direction=COLUMN, padding=10, background_color=TRANSPARENT)
            )
            self.details_container = toga.Box(
                style=Pack(direction=COLUMN, padding=10, background_color=TRANSPARENT)
            )

            # Wrap each in a ScrollContainer with TRANSPARENT background
            general_scroll = toga.ScrollContainer(
                content=self.general_container,
                style=Pack(flex=1, background_color=TRANSPARENT),
                horizontal=False  # Disable horizontal scroll
            )
            storage_scroll = toga.ScrollContainer(
                content=self.storage_container,
                style=Pack(flex=1, background_color=TRANSPARENT),
                horizontal=False  # Disable horizontal scroll
            )
            details_scroll = toga.ScrollContainer(
                content=self.details_container,
                style=Pack(flex=1, background_color=TRANSPARENT),
                horizontal=False  # Disable horizontal scroll
            )

            # Add fixed tabs (these never change)
            self.option_container.content.append("General", general_scroll)
            self.option_container.content.append("Storage", storage_scroll)
            self.option_container.content.append("Details", details_scroll)

            # Initial state - no selection
            self._update_no_selection_content()

            # Create main container
            container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1
                ),
                children=[self.option_container]
            )

            # Create window (match Preview inspector size)
            self.window = toga.Window(
                title="Inspector",
                size=(300, 500),  # Smaller, more compact like Preview
                resizable=True,
                content=container
            )

            # Position window on right side of screen
            self._position_window()

            logger.info("Inspector window created successfully with fixed tabs")

        except Exception as e:
            logger.error(f"Failed to create inspector window: {e}")
            raise

    def _position_window(self):
        """Position the window on the right side of the screen"""
        try:
            # Get the primary screen dimensions
            screen = self.app.screens[0]  # Primary screen
            screen_width = screen.size.width
            screen_height = screen.size.height

            # Position on right side with some margin
            window_width = self.window.size.width
            window_height = self.window.size.height

            x = screen_width - window_width - 20  # 20px margin from right
            y = 100  # 100px from top

            # Set the position
            self.window.position = (x, y)
        except Exception:
            # If positioning fails, just use default position
            pass
