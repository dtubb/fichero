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

    def _create_view_structure(self):
        """
        Override BaseView's structure to use OptionContainer as root.

        OptionContainer MUST be the root container (cannot be nested in Box)
        because it's a special Toga widget that manages its own layout.
        """
        try:
            # Create content first (creates tab_container as OptionContainer)
            self._create_content()

            # Use OptionContainer directly as the main container
            # (OptionContainer cannot be added to a Box - it must be the root)
            self.container = self.tab_container

            logger.debug("AdjustView structure created (OptionContainer as root)")

        except Exception as e:
            logger.error(f"Failed to create AdjustView structure: {e}")
            import traceback
            traceback.print_exc()
            # Create fallback container
            self.container = toga.Box(style=Pack(direction=COLUMN))
            self.tab_container = None

    def _create_content(self):
        """Create tabbed metadata display"""
        # Create tabs (OptionContainer handles its own layout and scrolling)
        # OptionContainer will be used as the root container
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

        # Add tabs to OptionContainer using .content.append() (correct Toga API)
        self.tab_container.content.append("Info", self.info_box)
        self.tab_container.content.append("Transcription", self.transcription_box)
        self.tab_container.content.append("Metadata", self.metadata_box)
        self.tab_container.content.append("JSON", self.json_box)

        logger.debug("Metadata panel created with 4 tabs")

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
            await self._load_json_tab(item, output_data)

            logger.info("Item details loaded")

        except Exception as e:
            logger.error(f"Failed to load item details: {e}")
            import traceback
            traceback.print_exc()

    async def _load_info_tab(self, item):
        """Load file info tab"""
        try:
            # Clear existing content
            self.info_box.content.clear()

            info_container = toga.Box(style=Pack(direction=COLUMN, margin=10))

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
        """Load transcription tab by querying ExtractedMetadata directly with item_id

        This method queries the metadata system directly without needing manifest files.
        The database is the source of truth for all transcriptions.

        Args:
            item_id: ID of the item
            output_data: DEPRECATED - kept for backward compatibility but ignored
        """
        try:
            # Direct query - no manifest lookups needed!
            metadata_entries = self.library_manager.storage.get_extracted_metadata_by_item(
                item_id=item_id,
                schema_type='transcription',
                key='text'
            )

            if metadata_entries:
                transcription_text = metadata_entries[0].value  # Newest first from query
                logger.debug(f"Loaded transcription from ExtractedMetadata ({len(transcription_text)} chars)")
            else:
                transcription_text = "No transcription available"
                logger.debug(f"No transcription found for item {item_id}")

            # Update text input
            if self.transcription_box:
                self.transcription_box.value = transcription_text

        except Exception as e:
            logger.error(f"Failed to load transcription: {e}")
            if self.transcription_box:
                self.transcription_box.value = f"Error loading transcription: {e}"

    async def _load_metadata_tab(self, item_id: str, output_data: Optional[Dict] = None):
        """Load metadata tab by querying ExtractedMetadata directly with item_id

        This method queries the metadata system directly without needing manifest files.
        Shows all metadata for the item, grouped by schema type.

        Args:
            item_id: ID of the item
            output_data: DEPRECATED - kept for backward compatibility but ignored
        """
        try:
            # Clear existing content
            self.metadata_box.content.clear()

            metadata_container = toga.Box(style=Pack(direction=COLUMN, margin=10))

            # Direct query - get ALL metadata for this item
            metadata_entries = self.library_manager.storage.get_extracted_metadata_by_item(
                item_id=item_id
            )

            if metadata_entries:
                # Group by source_label first (processing step), then by schema_type
                metadata_by_source = {}
                for entry in metadata_entries:
                    source = entry.source_label
                    if source not in metadata_by_source:
                        metadata_by_source[source] = {}

                    schema = entry.schema_type
                    if schema not in metadata_by_source[source]:
                        metadata_by_source[source][schema] = []
                    metadata_by_source[source][schema].append(entry)

                # Display by source
                for source, schemas in metadata_by_source.items():
                    # Add source header
                    self._add_info_row(metadata_container, "Source", source)

                    # Priority schemas: transcription, catalogue, translation
                    priority_schemas = ['transcription', 'catalogue', 'translation']

                    # Show priority schemas first
                    for schema in priority_schemas:
                        if schema in schemas:
                            if len(schemas) > 1:
                                # Add schema header if multiple schemas
                                self._add_info_row(metadata_container, "Schema", schema.title())

                            for entry in schemas[schema]:
                                if entry.value:  # Only show non-empty values
                                    label = entry.key.replace('_', ' ').title()
                                    self._add_info_row(metadata_container, label, entry.value)

                    # Show remaining schemas
                    for schema, entries in schemas.items():
                        if schema not in priority_schemas:
                            if len(schemas) > 1:
                                self._add_info_row(metadata_container, "Schema", schema.title())

                            for entry in entries:
                                if entry.value:
                                    label = entry.key.replace('_', ' ').title()
                                    self._add_info_row(metadata_container, label, entry.value)

                logger.debug(f"Loaded {len(metadata_entries)} metadata entries from ExtractedMetadata")
            else:
                self._add_placeholder(metadata_container, "No metadata available yet")

            self.metadata_box.content = metadata_container

        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            import traceback
            traceback.print_exc()
            self.metadata_box.content.clear()
            self._add_placeholder(self.metadata_box.content, f"Error loading metadata: {e}")

    async def _load_json_tab(self, item, output_data: Optional[Dict] = None):
        """Load JSON tab - shows raw processing output JSON files

        Args:
            item: The item to display
            output_data: Optional pre-fetched output data
        """
        try:
            import json
            json_text = ""

            # Try to get processing output JSON first
            if not output_data:
                output_data = await self.library_manager.get_item_output_data(item.id)

            if output_data and output_data.get('has_outputs'):
                steps = output_data.get('processing_steps', [])
                # Find latest JSON output (prefer catalogue, then transcribe, then any JSON)
                for step in reversed(steps):
                    if step.file_path and step.file_path.exists() and step.file_path.suffix.lower() == '.json':
                        json_text = step.file_path.read_text()
                        logger.debug(f"Showing JSON from: {step.tool_name}")
                        break

            # Fallback to item metadata if no processing outputs
            if not json_text:
                item_dict = {
                    'id': item.id,
                    'name': item.name,
                    'type': item.type.value if hasattr(item.type, 'value') else str(item.type),
                    'metadata': item.metadata,
                    'created_at': item.created_at.isoformat() if item.created_at else None,
                    'updated_at': item.updated_at.isoformat() if item.updated_at else None,
                }
                json_text = json.dumps(item_dict, indent=2, ensure_ascii=False)
                logger.debug("Showing item metadata (no processing outputs)")

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
