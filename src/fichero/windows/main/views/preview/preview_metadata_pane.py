"""
PreviewMetadataPane - Dedicated pane for displaying transcriptions and metadata

Handles:
- Transcription text display
- Catalog metadata
- Processing step results
- Custom layout for text content
"""

import logging
from typing import Optional, Dict, Any, List
import json

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

from fichero.shared.views.base_view import BaseView

# Import internationalization function
try:
    from fichero.shared.utils.i18n import _
except ImportError:
    def _(text):
        return text

logger = logging.getLogger(__name__)


class PreviewMetadataPane(BaseView):
    """
    Dedicated pane for transcription and metadata preview

    Shows transcriptions, catalog data, and processing metadata
    in a clean, readable format.
    """

    def __init__(self, app, is_mobile: bool = False, library_manager=None):
        """Initialize the metadata preview pane"""
        logger.info("PreviewMetadataPane.__init__ starting")

        # Store dependencies
        self.library_manager = library_manager
        self.is_mobile = is_mobile

        # Current state
        self.current_item_id: Optional[str] = None

        # UI components (will be created in _create_content)
        # Note: Using BaseView's scroll_container and content_container

        # Call parent init
        super().__init__(app, is_mobile)

        logger.info("PreviewMetadataPane initialization complete")

    def _create_content(self):
        """Create the metadata preview content"""
        # Use BaseView's content_container (already inside scroll container)
        # Add initial placeholder
        placeholder = toga.Label(
            "No item selected",
            style=Pack(
                text_align='center',
                margin=20,
                font_size=14,
                color='#666',
                font_family='system'
            )
        )
        self.content_container.add(placeholder)

    async def load_item(self, item_id: str, output_data: dict = None):
        """Load metadata and transcriptions for the given item from library"""
        logger.info(f"Loading metadata for item {item_id} from library")
        self.current_item_id = item_id

        try:
            if not self.library_manager:
                logger.warning("No library manager available")
                self._show_error("No library manager available")
                return

            # Get item data from library
            item_data = await self.library_manager.get_item(item_id)
            if not item_data:
                logger.warning(f"No item data found for item {item_id}")
                self._show_error("No item found")
                return

            # Clear existing content
            self._clear_content()

            # Build content sections from library data
            self._add_item_header(item_id)
            await self._add_library_transcriptions(item_id)
            await self._add_library_catalog_data(item_id)
            self._add_library_metadata(item_data)

            logger.info(f"Loaded library metadata for item {item_id}")

        except Exception as e:
            logger.error(f"Failed to load metadata for item {item_id}: {e}")
            self._show_error(f"Error loading metadata: {e}")

    def _clear_content(self):
        """Clear all content from the pane"""
        # Remove all children from content container
        while len(self.content_container.children) > 0:
            self.content_container.remove(self.content_container.children[0])

    def _add_item_header(self, item_id: str):
        """Add header with item information"""
        header = toga.Label(
            f"Item: {item_id}",
            style=Pack(
                font_weight='bold',
                font_size=14,
                margin_bottom=15,
                color='#333',
                font_family='system'
            )
        )
        self.content_container.add(header)





    def _show_error(self, message: str):
        """Show error message"""
        self._clear_content()
        error_label = toga.Label(
            f"Error: {message}",
            style=Pack(
                text_align='center',
                margin=20,
                color='#d32f2f',
                font_family='system'
            )
        )
        self.content_container.add(error_label)

    def clear(self):
        """Clear the metadata preview"""
        self.current_item_id = None
        self._clear_content()
        placeholder = toga.Label(
            "No item selected",
            style=Pack(
                text_align='center',
                margin=20,
                font_size=14,
                color='#666',
                font_family='system'
            )
        )
        self.content_container.add(placeholder)
        logger.debug("Metadata pane cleared")

    async def _add_library_transcriptions(self, item_id: str):
        """Add transcriptions from library"""
        try:
            # Get transcriptions from library
            transcriptions = await self.library_manager.get_item_transcriptions(item_id)

            if not transcriptions:
                return

            # Add transcription section
            section_header = toga.Label(
                "Transcriptions",
                style=Pack(
                    font_weight='bold',
                    font_size=14,
                    margin_bottom=10,
                    color='#555',
                    font_family='system'
                )
            )
            self.content_container.add(section_header)

            for transcription in transcriptions:
                # Transcription text
                text_content = toga.MultilineTextInput(
                    value=transcription,
                    readonly=True,
                    style=Pack(
                        height=150,
                        margin_bottom=15,
                        background_color='#f9f9f9',
                        font_family='monospace',
                        font_size=14
                    )
                )
                self.content_container.add(text_content)

        except Exception as e:
            logger.error(f"Error loading transcriptions: {e}")

    async def _add_library_catalog_data(self, item_id: str):
        """Add catalog data from library"""
        try:
            # Get catalog data from library manager
            catalog_data = await self.library_manager.get_item_catalog_data(item_id)

            if not catalog_data:
                return

            # Add catalog section
            section_header = toga.Label(
                "Catalog Data",
                style=Pack(
                    font_weight='bold',
                    font_size=14,
                    margin_bottom=10,
                    margin_top=15,
                    color='#555',
                    font_family='system'
                )
            )
            self.content_container.add(section_header)

            # Display catalog data
            if isinstance(catalog_data, dict):
                formatted = json.dumps(catalog_data, indent=2, ensure_ascii=False)
            else:
                formatted = str(catalog_data)

            catalog_text = toga.MultilineTextInput(
                value=formatted,
                readonly=True,
                style=Pack(
                    height=200,
                    margin_bottom=15,
                    background_color='#f9f9f9',
                    font_family='SF Mono',
                    font_size=14
                )
            )
            self.content_container.add(catalog_text)

        except Exception as e:
            logger.error(f"Error loading catalog data: {e}")

    def _add_library_metadata(self, item_data):
        """Add metadata from library"""
        try:
            # Add metadata section
            section_header = toga.Label(
                "Item Metadata",
                style=Pack(
                    font_weight='bold',
                    font_size=14,
                    margin_bottom=10,
                    margin_top=15,
                    color='#555',
                    font_family='system'
                )
            )
            self.content_container.add(section_header)

            # Show key metadata fields
            metadata_fields = []

            if hasattr(item_data, 'name'):
                metadata_fields.append(f"Name: {item_data.name}")
            elif isinstance(item_data, dict) and 'name' in item_data:
                metadata_fields.append(f"Name: {item_data['name']}")

            if hasattr(item_data, 'type'):
                metadata_fields.append(f"Type: {item_data.type}")
            elif isinstance(item_data, dict) and 'type' in item_data:
                metadata_fields.append(f"Type: {item_data['type']}")

            if hasattr(item_data, 'original_path'):
                from pathlib import Path
                metadata_fields.append(f"File: {Path(item_data.original_path).name}")
            elif hasattr(item_data, 'file_path'):
                from pathlib import Path
                metadata_fields.append(f"File: {Path(item_data.file_path).name}")
            elif isinstance(item_data, dict) and 'original_path' in item_data:
                from pathlib import Path
                metadata_fields.append(f"File: {Path(item_data['original_path']).name}")

            if metadata_fields:
                metadata_text = "\n".join(metadata_fields)
                metadata_display = toga.MultilineTextInput(
                    value=metadata_text,
                    readonly=True,
                    style=Pack(
                        height=100,
                        margin_bottom=15,
                        background_color='#f9f9f9',
                        font_family='monospace',
                        font_size=14
                    )
                )
                self.content_container.add(metadata_display)

        except Exception as e:
            logger.error(f"Error displaying metadata: {e}")

    def get_scroll_state(self) -> dict:
        """
        Get current scroll position.

        Returns:
            Dict with scroll_y (vertical scroll position) or empty dict if unavailable
        """
        if not self.scroll_container:
            return {}

        try:
            # Toga ScrollContainer uses vertical_position property
            scroll_y = getattr(self.scroll_container, 'vertical_position', 0)
            return {'scroll_y': scroll_y}
        except Exception as e:
            logger.debug(f"Could not get scroll state: {e}")
            return {}

    def restore_scroll_state(self, state: dict):
        """
        Restore scroll position.

        Args:
            state: Dict with scroll_y
        """
        if not self.scroll_container or not state:
            return

        try:
            scroll_y = state.get('scroll_y', 0)
            if scroll_y > 0:
                # Toga ScrollContainer uses vertical_position property
                if hasattr(self.scroll_container, 'vertical_position'):
                    self.scroll_container.vertical_position = scroll_y
                    logger.debug(f"Restored scroll position: scroll_y={scroll_y}")
        except Exception as e:
            logger.warning(f"Could not restore scroll state: {e}")

    def reset_scroll(self):
        """Reset scroll position to top (called when changing items)."""
        if not self.scroll_container:
            return

        try:
            if hasattr(self.scroll_container, 'vertical_position'):
                self.scroll_container.vertical_position = 0
                logger.debug("Reset scroll position to top")
        except Exception as e:
            logger.debug(f"Could not reset scroll: {e}")