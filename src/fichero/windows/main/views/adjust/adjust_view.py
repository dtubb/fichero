"""
AdjustView - SIMPLIFIED for Metadata Display

Shows metadata, transcriptions, and file info for the currently selected item.
No longer manages workflow tools - just displays processing outputs as text.

Architecture:
- Tabbed interface: Info | Transcription | Metadata | JSON
- Read-only display of outputs
- Copy/export functionality
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from pathlib import Path

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

from fichero.shared.views.base_view import BaseView

logger = logging.getLogger(__name__)


class AdjustView(BaseView):
    """
    SIMPLIFIED Metadata/Output Display Panel.

    Shows:
    - File info (name, size, dimensions, etc.)
    - Transcription (if available)
    - Metadata (if extracted)
    - Raw JSON outputs
    """

    def __init__(self, app, is_mobile: bool = False):
        """Initialize simplified metadata panel"""
        logger.info("Initializing AdjustView (SIMPLIFIED - metadata display)")

        # Current item
        self.current_item_id: Optional[str] = None
        self.library_manager = None  # Set by main_window

        # UI components
        self.tab_container = None
        self.info_box = None
        self.transcription_box = None
        self.metadata_box = None
        self.json_box = None

        # Call parent init
        super().__init__(app, is_mobile)

        logger.info("AdjustView (SIMPLIFIED) initialized")

    def _create_content(self):
        """Create tabbed metadata display"""
        # CRITICAL FIX: OptionContainer must NOT be inside a ScrollContainer
        # Remove the BaseView's ScrollContainer and add tabs directly to main container
        # BaseView creates: container -> scroll_container -> content_container
        # We need: container -> tab_container (OptionContainer manages its own scrolling per tab)

        # Remove scroll container from parent (it was added by BaseView)
        if self.scroll_container and self.scroll_container in self.container.children:
            self.container.remove(self.scroll_container)
            logger.debug("Removed ScrollContainer - OptionContainer manages its own scrolling")

        # Create tabs directly (no wrapper box needed - OptionContainer handles its own layout)
        self.tab_container = toga.OptionContainer(
            style=Pack(flex=1)
        )

        # Tab 1: File Info - Box with ScrollContainer for content
        info_content = toga.Box(style=Pack(direction=COLUMN, margin=10))
        self._add_placeholder(info_content, "Select an item to view its information")
        self.info_box = toga.ScrollContainer(
            content=info_content,
            style=Pack(flex=1)
        )

        # Tab 2: Transcription - Direct MultilineTextInput (has built-in scrolling)
        self.transcription_box = toga.MultilineTextInput(
            readonly=True,
            style=Pack(flex=1, font_family='monospace', font_size=12)
        )

        # Tab 3: Metadata - Box with ScrollContainer for content
        metadata_content = toga.Box(style=Pack(direction=COLUMN, margin=10))
        self._add_placeholder(metadata_content, "No metadata available")
        self.metadata_box = toga.ScrollContainer(
            content=metadata_content,
            style=Pack(flex=1)
        )

        # Tab 4: JSON - Direct MultilineTextInput (has built-in scrolling)
        self.json_box = toga.MultilineTextInput(
            readonly=True,
            style=Pack(flex=1, font_family='monospace', font_size=11)
        )

        # Add tabs to container
        self.tab_container.add("Info", self.info_box)
        self.tab_container.add("Transcription", self.transcription_box)
        self.tab_container.add("Metadata", self.metadata_box)
        self.tab_container.add("JSON", self.json_box)

        # Add OptionContainer directly to main container (bypassing scroll_container)
        self.container.add(self.tab_container)

        logger.debug("Metadata panel created with 4 tabs (OptionContainer manages own scrolling)")

    def _add_placeholder(self, container: toga.Box, text: str):
        """Add placeholder text to a container"""
        label = toga.Label(
            text,
            style=Pack(margin=20, color='#999', font_size=12)
        )
        container.add(label)

    def set_library_manager(self, library_manager):
        """Set library manager reference"""
        self.library_manager = library_manager
        logger.debug("Library manager set in AdjustView")

    async def load_item(self, item_id: str, output_data: Optional[Dict] = None):
        """
        Load and display item details.

        Shows:
        - File info (name, path, size, etc.)
        - Latest transcription (if available)
        - Extracted metadata (if available)
        - Raw JSON data

        Args:
            item_id: ID of the item to load
            output_data: Optional pre-fetched output data (prevents re-querying library_manager)
        """
        # ALWAYS reload - no deduplication to ensure content updates properly
        logger.info(f"Loading item details: {item_id} (forced reload)")

        try:
            self.current_item_id = item_id

            if not self.library_manager:
                logger.warning("No library manager available")
                return

            # Get item
            item = self.library_manager.storage.get_item(item_id)
            if not item:
                logger.warning(f"Item not found: {item_id}")
                return

            # Load each tab with cached output_data
            await self._load_info_tab(item)
            await self._load_transcription_tab(item_id, output_data)
            await self._load_metadata_tab(item_id, output_data)
            await self._load_json_tab(item)

            logger.info("✅ Item details loaded")

        except Exception as e:
            logger.error(f"Failed to load item details: {e}")
            import traceback
            traceback.print_exc()

    async def _load_info_tab(self, item):
        """Load file info tab"""
        try:
            # Clear existing content
            self.info_box.content.clear()

            info_container = toga.Box(style=Pack(direction=COLUMN, padding=10))

            # File name
            file_path = item.metadata.get('local_path') or item.metadata.get('file_path', '')
            if file_path:
                file_name = Path(file_path).name
                self._add_info_row(info_container, "File", file_name)

            # Item name
            self._add_info_row(info_container, "Name", item.name)

            # Type
            item_type = item.metadata.get('type', 'Unknown')
            self._add_info_row(info_container, "Type", item_type)

            # Path
            if file_path:
                self._add_info_row(info_container, "Path", str(file_path))

            # File size
            if file_path and Path(file_path).exists():
                size_bytes = Path(file_path).stat().st_size
                size_mb = size_bytes / (1024 * 1024)
                self._add_info_row(info_container, "Size", f"{size_mb:.2f} MB")

            # Created date
            created = item.created_at
            if created:
                self._add_info_row(info_container, "Added", created.strftime("%Y-%m-%d %H:%M"))

            # Collection
            if hasattr(item, 'collection_id'):
                collection = self.library_manager.storage.get_collection(item.collection_id)
                if collection:
                    self._add_info_row(info_container, "Collection", collection.name)

            self.info_box.content = info_container

        except Exception as e:
            logger.error(f"Failed to load info tab: {e}")

    def _add_info_row(self, container: toga.Box, label: str, value: str):
        """Add a label-value row to info display"""
        row = toga.Box(style=Pack(direction=COLUMN, margin_bottom=10))

        label_widget = toga.Label(
            label + ":",
            style=Pack(font_weight='bold', font_size=11, color='#666')
        )
        row.add(label_widget)

        value_widget = toga.Label(
            str(value),
            style=Pack(font_size=12, margin_top=2)
        )
        row.add(value_widget)

        container.add(row)

    async def _load_transcription_tab(self, item_id: str, output_data: Optional[Dict] = None):
        """Load transcription tab - shows latest transcription output

        Args:
            item_id: ID of the item
            output_data: Optional pre-fetched output data (prevents re-querying library_manager)
        """
        try:
            # REFACTORED: Use cached output_data if available
            if not output_data:
                logger.debug("⚠️ No cached output_data provided for transcription tab, fetching from library_manager")
                output_data = await self.library_manager.get_item_output_data(item_id)
            else:
                logger.debug("✅ Using cached output_data for transcription tab (no database query)")

            transcription_text = ""

            if output_data and output_data.get('has_outputs'):
                # Find transcription step
                steps = output_data.get('processing_steps', [])
                for step in reversed(steps):  # Check newest first
                    if 'transcribe' in step.tool_name.lower():
                        # Read transcription file
                        file_path = step.file_path
                        if file_path and file_path.exists():
                            if file_path.suffix.lower() == '.json':
                                # Parse JSON transcription
                                import json
                                data = json.loads(file_path.read_text())
                                if isinstance(data, dict) and 'transcription' in data:
                                    transcription_text = data['transcription']
                                elif isinstance(data, str):
                                    transcription_text = data
                                else:
                                    transcription_text = json.dumps(data, indent=2)
                            else:
                                # Plain text
                                transcription_text = file_path.read_text()
                            break

            if not transcription_text:
                transcription_text = "No transcription available yet.\n\nTranscription will appear here after processing."

            # Update text input
            if isinstance(self.transcription_box, toga.MultilineTextInput):
                self.transcription_box.value = transcription_text

        except Exception as e:
            logger.error(f"Failed to load transcription: {e}")
            if isinstance(self.transcription_box, toga.MultilineTextInput):
                self.transcription_box.value = f"Error loading transcription: {e}"

    async def _load_metadata_tab(self, item_id: str, output_data: Optional[Dict] = None):
        """Load metadata tab - shows extracted metadata

        Args:
            item_id: ID of the item
            output_data: Optional pre-fetched output data (prevents re-querying library_manager)
        """
        try:
            # Clear existing content
            self.metadata_box.content.clear()

            metadata_container = toga.Box(style=Pack(direction=COLUMN, padding=10))

            # REFACTORED: Use cached output_data if available
            if not output_data:
                logger.debug("⚠️ No cached output_data provided for metadata tab, fetching from library_manager")
                output_data = await self.library_manager.get_item_output_data(item_id)
            else:
                logger.debug("✅ Using cached output_data for metadata tab (no database query)")

            metadata_found = False

            if output_data and output_data.get('has_outputs'):
                # Find metadata extraction step
                steps = output_data.get('processing_steps', [])
                for step in reversed(steps):  # Check newest first
                    if 'metadata' in step.tool_name.lower() or 'extract' in step.tool_name.lower():
                        # Read metadata file
                        file_path = step.file_path
                        if file_path and file_path.exists():
                            import json
                            data = json.loads(file_path.read_text())

                            # Display metadata fields
                            for key, value in data.items():
                                self._add_info_row(metadata_container, key.replace('_', ' ').title(), str(value))

                            metadata_found = True
                            break

            if not metadata_found:
                self._add_placeholder(metadata_container, "No metadata extracted yet.\n\nMetadata will appear here after processing.")

            self.metadata_box.content = metadata_container

        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            self.metadata_box.content.clear()
            self._add_placeholder(self.metadata_box.content, f"Error loading metadata: {e}")

    async def _load_json_tab(self, item):
        """Load JSON tab - shows raw item data"""
        try:
            import json

            # Get item as dict
            item_dict = {
                'id': item.id,
                'name': item.name,
                'type': item.type.value if hasattr(item.type, 'value') else str(item.type),
                'metadata': item.metadata,
                'created_at': item.created_at.isoformat() if item.created_at else None,
                'updated_at': item.updated_at.isoformat() if item.updated_at else None,
            }

            # Format as pretty JSON
            json_text = json.dumps(item_dict, indent=2, ensure_ascii=False)

            # Update text input
            if isinstance(self.json_box, toga.MultilineTextInput):
                self.json_box.value = json_text

        except Exception as e:
            logger.error(f"Failed to load JSON: {e}")
            if isinstance(self.json_box, toga.MultilineTextInput):
                self.json_box.value = f"Error loading JSON: {e}"

    def clear(self):
        """Clear all content"""
        self.current_item_id = None

        # Clear info tab
        if self.info_box and self.info_box.content:
            self.info_box.content.clear()
            self._add_placeholder(self.info_box.content, "Select an item to view its information")

        # Clear transcription
        if isinstance(self.transcription_box, toga.MultilineTextInput):
            self.transcription_box.value = "No item selected"

        # Clear metadata
        if self.metadata_box and self.metadata_box.content:
            self.metadata_box.content.clear()
            self._add_placeholder(self.metadata_box.content, "No metadata available")

        # Clear JSON
        if isinstance(self.json_box, toga.MultilineTextInput):
            self.json_box.value = ""

        logger.debug("Cleared all metadata panels")
