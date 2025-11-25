"""
PreviewView - Unified preview interface for tests and components

Provides a unified interface that matches test expectations while integrating
with the new library metadata system. This class bridges the old PreviewView
interface with the new direct metadata loading approach.
"""

import logging
import tempfile
from typing import Optional, Dict, Any
from pathlib import Path

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

from fichero.shared.views.base_view import BaseView
from .preview_image_pane import PreviewImagePane
from .preview_metadata_pane import PreviewMetadataPane

# Import internationalization function
try:
    from fichero.shared.utils.i18n import _
except ImportError:
    def _(text):
        return text

logger = logging.getLogger(__name__)


class PreviewView(BaseView):
    """
    Unified preview view that combines image and metadata panes

    Provides compatibility with existing tests while using the new
    library metadata system for direct data loading.
    """

    def __init__(self, app, is_mobile: bool = False, library_manager=None):
        """Initialize the preview view"""
        logger.info("🔍 PreviewView.__init__ starting")

        # Store dependencies
        self.library_manager = library_manager
        self.is_mobile = is_mobile

        # Current state
        self.current_item_id: Optional[str] = None

        # Create child panes
        self.image_pane = PreviewImagePane(app, is_mobile, library_manager)
        self.metadata_pane = PreviewMetadataPane(app, is_mobile, library_manager)

        # Call parent init
        super().__init__(app, is_mobile)

        logger.info("✅ PreviewView initialization complete")

    def _create_content(self):
        """Create the preview content with both panes"""
        if self.is_mobile:
            # Mobile: Stack vertically
            self.content_container.add(self.image_pane.widget)
            self.content_container.add(self.metadata_pane.widget)
        else:
            # Desktop: Side by side
            preview_box = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=1
                )
            )
            preview_box.add(self.image_pane.widget)
            preview_box.add(self.metadata_pane.widget)
            self.content_container.add(preview_box)

    async def load_item(self, item_id: str, output_data: dict = None):
        """Load preview data for the given item"""
        logger.info(f"🔍 Loading preview for item {item_id}")
        self.current_item_id = item_id

        # Load into both panes
        await self.image_pane.load_item(item_id, output_data)
        await self.metadata_pane.load_item(item_id, output_data)

    async def _get_transcription_text(self, item_id: str, output_data: dict = None) -> Optional[str]:
        """
        Get transcription text for an item and return as temp file path

        This method queries the library metadata system directly by item_id,
        ignoring the output_data parameter for backward compatibility.

        Returns:
            str: Path to temporary file containing transcription text
            None: If no transcription found
        """
        logger.info(f"🔍 Getting transcription text for item {item_id}")

        try:
            if not self.library_manager:
                logger.warning("No library manager available")
                return None

            # Get storage from library manager
            storage = self.library_manager.storage
            if not storage:
                logger.warning("No storage available from library manager")
                return None

            # Query extracted metadata directly by item_id
            metadata_records = storage.get_extracted_metadata_by_item(
                item_id=item_id,
                schema_type='transcription',
                key='text'
            )

            if not metadata_records:
                logger.info(f"No transcription metadata found for item {item_id}")
                return None

            # Use the first result (newest version by default)
            metadata = metadata_records[0]
            transcription_text = metadata.value

            if not transcription_text or not transcription_text.strip():
                logger.info(f"Empty transcription text for item {item_id}")
                return None

            # Create temporary file with transcription content
            temp_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.txt',
                delete=False,
                encoding='utf-8'
            )

            temp_file.write(transcription_text)
            temp_file.close()

            logger.info(f"✅ Created temp transcription file: {temp_file.name}")
            return temp_file.name

        except Exception as e:
            logger.error(f"Error getting transcription text for item {item_id}: {e}")
            return None

    def clear(self):
        """Clear the preview"""
        self.current_item_id = None
        self.image_pane.clear()
        self.metadata_pane.clear()
        logger.debug("🔍 Preview cleared")