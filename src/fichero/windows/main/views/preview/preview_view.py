"""
PreviewView - SIMPLIFIED VERSION

Shows the latest output for a selected item.
No step navigation, no processing history, just: show the image or show the metadata.

Architecture:
- LayoutManager: Manages split view layouts (already works)
- OutputPane: Displays content using universal renderers (already works)
- Simple API: load_item(item_id) → shows latest output
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from pathlib import Path

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

from fichero.shared.views.base_view import BaseView
from fichero.shared.commands.view_mixin import ViewCommandMixin
from fichero.shared.toolbars import ToolbarCoordinator, TopToolbar, BottomToolbar

# Simplified imports - only what we need
from .layout_manager import LayoutManager, LayoutType
from .output_pane import OutputPane
from fichero.library.renderers.renderer_registry import RendererRegistry

logger = logging.getLogger(__name__)


class PreviewView(BaseView, ViewCommandMixin):
    """
    SIMPLIFIED Preview view - shows latest output for selected item.

    No step navigation, no processing history tree.
    Just: Select item → Show latest image/metadata.
    """

    _commands_registered = False

    def __init__(self, app, is_mobile: bool = False, library_manager=None):
        """Initialize simplified preview view"""
        logger.info("🔧 PreviewView.__init__ starting (SIMPLIFIED VERSION)")

        # Store library manager
        self.library_manager = library_manager

        # Current item being displayed
        self.current_item_id: Optional[str] = None
        self.current_collection_items: List[Dict] = []  # For file navigation
        self.current_item_index: int = 0

        # Initialize renderer registry
        self.renderer_registry = RendererRegistry()

        # Initialize layout manager (handles split views)
        self.layout_manager = LayoutManager(library_manager, self.renderer_registry)

        # No event subscription - main_window calls load_item() directly
        logger.info("✅ PreviewView will be loaded directly from main_window")

        # UI components
        self.content_area = None

        # Create toolbar coordinator
        self.coordinator = ToolbarCoordinator(app, is_mobile=is_mobile)

        # Set view_id for command registration
        self.view_id = 'output'

        # Call parent init
        super().__init__(app, is_mobile)
        ViewCommandMixin.__init__(self)

        # Define and register commands
        self.define_commands()
        if not PreviewView._commands_registered:
            self.register_commands()
            PreviewView._commands_registered = True
            logger.debug("✅ PreviewView commands registered")

        # Set up toolbars
        self._setup_toolbars()

        logger.info("✅ PreviewView (SIMPLIFIED) initialization complete")

    def define_commands(self):
        """Define commands - only navigation and zoom, no step controls"""
        from fichero.shared.commands import FicheroCommand
        import toga

        go_group = toga.Group("Go", order=40)

        self.commands = {
            # ===== VIEW MENU - Zoom Commands =====
            'zoom_in': FicheroCommand(
                id=f'{self.view_id}.zoom_in',
                label=_("Zoom In"),
                action=self._on_zoom_in,
                shortcut=toga.Key.MOD_1 + toga.Key.PLUS,
                description=_("Zoom in on image"),
                group=toga.Group.VIEW,
                section=10,
                order=0,
                show_in_menu=True,
                context='normal'
            ),
            'zoom_out': FicheroCommand(
                id=f'{self.view_id}.zoom_out',
                label=_("Zoom Out"),
                action=self._on_zoom_out,
                shortcut=toga.Key.MOD_1 + toga.Key.MINUS,
                description=_("Zoom out on image"),
                group=toga.Group.VIEW,
                section=10,
                order=1,
                show_in_menu=True,
                context='normal'
            ),
            'zoom_fit': FicheroCommand(
                id=f'{self.view_id}.zoom_fit',
                label=_("Zoom to Fit"),
                action=self._on_zoom_fit,
                shortcut=toga.Key.MOD_1 + '9',
                description=_("Fit image to window"),
                group=toga.Group.VIEW,
                section=10,
                order=2,
                show_in_menu=True,
                context='normal'
            ),
            'actual_size': FicheroCommand(
                id=f'{self.view_id}.actual_size',
                label=_("Actual Size"),
                action=self._on_zoom_100,
                shortcut=toga.Key.MOD_1 + '0',
                description=_("Zoom to 100%"),
                group=toga.Group.VIEW,
                section=10,
                order=3,
                show_in_menu=True,
                context='normal'
            ),

            # ===== GO MENU - File Navigation Only (NO STEP NAVIGATION) =====
            'prev_file': FicheroCommand(
                id=f'{self.view_id}.prev_file',
                label=_("Previous File"),
                action=self._on_prev_file,
                shortcut=toga.Key.MOD_1 + toga.Key.UP,
                description=_("Navigate to previous file"),
                group=go_group,
                section=0,
                order=0,
                show_in_menu=True,
                context='normal'
            ),
            'next_file': FicheroCommand(
                id=f'{self.view_id}.next_file',
                label=_("Next File"),
                action=self._on_next_file,
                shortcut=toga.Key.MOD_1 + toga.Key.DOWN,
                description=_("Navigate to next file"),
                group=go_group,
                section=0,
                order=1,
                show_in_menu=True,
                context='normal'
            ),

            # ===== Basic toolbar tools =====
            'rotate_left': FicheroCommand(
                id=f'{self.view_id}.rotate_left',
                label=_("Rotate Left"),
                action=self._on_rotate_left,
                shortcut=toga.Key.MOD_1 + 'l',
                icon='resources/icons/toolbar/rotate.left@10x.png',
                description=_("Rotate image 90° counter-clockwise"),
                show_in_top_toolbar=True,
                context='normal'
            ),
            'rotate_right': FicheroCommand(
                id=f'{self.view_id}.rotate_right',
                label=_("Rotate Right"),
                action=self._on_rotate_right,
                shortcut=toga.Key.MOD_1 + 'r',
                icon='resources/icons/toolbar/rotate.right@10x.png',
                description=_("Rotate image 90° clockwise"),
                show_in_top_toolbar=True,
                context='normal'
            ),
        }

    def _create_content(self):
        """Create simplified preview content - just the layout manager"""
        self.content_area = toga.Box(style=Pack(direction=ROW, flex=1))

        # Add layout manager's container (output panes)
        self.content_area.add(self.layout_manager.get_container())

        # Add to content container (from BaseView)
        self.content_container.add(self.content_area)

    def _setup_toolbars(self):
        """Set up simplified toolbars - just file navigation"""
        # Top toolbar with file counter
        self.top_toolbar = TopToolbar(
            self.app,
            title=_("No file loaded"),
            auto_mobile_nav=True,
            is_mobile=self.is_mobile,
            coordinator=self.coordinator
        )

        # Bottom toolbar with just file navigation (NO STEP NAVIGATION)
        self.bottom_toolbar = BottomToolbar(
            self.app,
            is_mobile=self.is_mobile,
            coordinator=self.coordinator
        )

        # File navigation buttons
        self.prev_file_btn = self.bottom_toolbar.add_normal_mode_button(
            icon="resources/icons/toolbar/chevron.up@10x.png",
            on_press=lambda w: asyncio.create_task(self._on_prev_file(w)),
            position="left",
            label=_("Prev\nFile")
        )

        self.next_file_btn = self.bottom_toolbar.add_normal_mode_button(
            icon="resources/icons/toolbar/chevron.down@10x.png",
            on_press=lambda w: asyncio.create_task(self._on_next_file(w)),
            position="left",
            label=_("Next\nFile")
        )

        # Register toolbars with BaseView
        self.set_toolbars(top_toolbar=self.top_toolbar, bottom_toolbar=self.bottom_toolbar)

        # Initial state - disabled until content loaded
        self.prev_file_btn.enabled = False
        self.next_file_btn.enabled = False

    def get_container(self):
        """Return the main container for this view"""
        return self.container

    def show(self):
        """Show callback - called when view becomes active"""
        self.is_visible = True
        if hasattr(self, 'coordinator') and self.coordinator:
            self.coordinator.set_active_view('output')

    # ==================== PUBLIC API ====================

    async def _get_item_metadata_from_backend(self, item_id: str) -> Dict[str, Any]:
        """
        Query extracted_metadata table for ALL metadata for an item.

        Uses the new metadata backend system instead of item.metadata dict.

        Returns organized dict structure ready for JSON display:
        {
            "item_info": {...},
            "transcriptions": {"ai_qwen_v1": {...}},
            "catalogues": {...},
            "file_info": {...}
        }
        """
        try:
            # Get item basic info
            item = await self.library_manager.get_item(item_id)
            if not item:
                logger.warning(f"Item {item_id} not found")
                return {}

            # Build item info section
            metadata = {
                'item_info': {
                    'name': item.name,
                    'type': item.type,
                    'status': item.status,
                    'storage_type': item.storage_type,
                    'source_path': str(item.source_path) if item.source_path else None,
                    'local_path': str(item.local_path) if item.local_path else None,
                    'created_at': item.created_at.isoformat() if hasattr(item, 'created_at') and item.created_at else None,
                    'updated_at': item.updated_at.isoformat() if hasattr(item, 'updated_at') and item.updated_at else None,
                }
            }

            # Add custom metadata from item.metadata dict if present
            if hasattr(item, 'metadata') and item.metadata:
                metadata['item_info']['custom_metadata'] = item.metadata

            # Query processing outputs to get extracted metadata
            try:
                output_data = await self.library_manager.get_item_output_data(item_id)

                if output_data and output_data.get('processing_steps'):
                    # Iterate through processing steps to collect metadata
                    for step in output_data['processing_steps']:
                        # Each step may have a processing_output with extracted metadata
                        if hasattr(step, 'manifest_entry') and step.manifest_entry:
                            output_id = step.manifest_entry.get('processing_output_id')
                            if output_id:
                                # Get extracted metadata for this output
                                extracted = self.library_manager.storage.get_extracted_metadata(output_id)

                                for meta in extracted:
                                    # Group by schema_type (e.g., "transcription", "catalogue")
                                    schema_section = f"{meta.schema_type}s"  # e.g., "transcriptions"
                                    if schema_section not in metadata:
                                        metadata[schema_section] = {}

                                    # Create version key: "source_label_vN"
                                    version_key = f"{meta.source_label}_v{meta.version}"
                                    if version_key not in metadata[schema_section]:
                                        metadata[schema_section][version_key] = {}

                                    # Add field
                                    metadata[schema_section][version_key][meta.key] = meta.value

                                    # Add confidence if present
                                    if meta.confidence is not None:
                                        metadata[schema_section][version_key][f"{meta.key}_confidence"] = meta.confidence

                logger.info(f"✅ Extracted metadata from backend: {len(metadata)} sections")

            except Exception as e:
                logger.warning(f"Could not query extracted metadata: {e}")
                # Continue with just item_info

            return metadata

        except Exception as e:
            logger.error(f"Failed to get metadata from backend: {e}")
            import traceback
            traceback.print_exc()
            return {}

    async def _get_transcription_text(self, item_id: str, output_data: Optional[Dict] = None) -> Optional[Path]:
        """
        Get transcription text from extracted_metadata table.

        Queries for schema_type='transcription' and returns the text content.

        Args:
            item_id: ID of the item
            output_data: Optional pre-fetched output data (prevents re-querying library_manager)
        """
        import tempfile
        from pathlib import Path

        try:
            # Get item to access its processing outputs
            item = await self.library_manager.get_item(item_id)
            if not item:
                logger.warning(f"Item {item_id} not found")
                return None

            # REFACTORED: Use cached output_data if available
            if not output_data:
                logger.debug("⚠️ No cached output_data provided for transcription, fetching from library_manager")
                output_data = await self.library_manager.get_item_output_data(item_id)
            else:
                logger.debug("✅ Using cached output_data for transcription lookup (no database query)")

            if not output_data or not output_data.get('processing_steps'):
                logger.info(f"No processing outputs found for item {item_id}")
                return None

            # Look for transcription in extracted metadata
            transcription_text = None
            for step in output_data['processing_steps']:
                if hasattr(step, 'manifest_entry') and step.manifest_entry:
                    output_id = step.manifest_entry.get('processing_output_id')
                    if output_id:
                        # Get extracted metadata for this output
                        extracted = self.library_manager.storage.get_extracted_metadata(output_id)

                        # Find transcription schema_type
                        for meta in extracted:
                            if meta.schema_type == 'transcription' and meta.key == 'text':
                                transcription_text = meta.value
                                break

                        if transcription_text:
                            break

            if not transcription_text:
                logger.info(f"No transcription found for item {item_id}")
                return None

            # Create temp text file
            temp_file = Path(tempfile.gettempdir()) / f"transcription_{item_id}.txt"
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(transcription_text)

            logger.info(f"✅ Created transcription text file: {temp_file}")
            return temp_file

        except Exception as e:
            logger.error(f"Failed to get transcription text: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def load_item(self, item_id: str, output_data: Optional[Dict] = None):
        """
        Load item with DUAL-COLUMN layout: image on left, metadata on right.
        ALWAYS shows dual columns regardless of processing status.

        Args:
            item_id: ID of the item to load
            output_data: Optional pre-fetched output data (prevents re-querying library_manager)
        """
        # ALWAYS reload - no deduplication to ensure content updates properly
        logger.info(f"Loading item: {item_id} (forced reload)")

        try:
            self.current_item_id = item_id

            # Get item from library (use async API)
            item = await self.library_manager.get_item(item_id)
            if not item:
                logger.warning(f"Item not found: {item_id}")
                return

            # Update toolbar title
            file_index = self.current_item_index + 1
            total_files = len(self.current_collection_items)
            if total_files > 0:
                title = _("File {}/{}").format(file_index, total_files)
            else:
                title = _("File 1/1")

            if hasattr(self, 'top_toolbar') and self.top_toolbar:
                if hasattr(self.top_toolbar, 'title_label') and self.top_toolbar.title_label:
                    self.top_toolbar.title_label.text = title

            # Update file navigation buttons
            self.prev_file_btn.enabled = self.current_item_index > 0
            self.next_file_btn.enabled = self.current_item_index < len(self.current_collection_items) - 1

            # ALWAYS use dual-column layout
            logger.info(f"📊 Using dual-column preview: image on left, metadata on right")
            self.layout_manager.set_layout(LayoutType.DUAL_COMPARE)

            # LEFT PANE: Display the latest image (NO STEP ITERATION)
            left_pane = self.layout_manager.get_pane(0)
            if left_pane:
                try:
                    # Get latest output using cached data if available
                    latest_output = await self._get_latest_output(item_id, output_data)
                    if latest_output:
                        await left_pane.set_content(
                            file_path=latest_output['file_path'],
                            file_type=latest_output['file_type'],
                            context={
                                'step_name': latest_output['step_name'],
                                'tool_name': latest_output['tool_name']
                            }
                        )
                        logger.info(f"✅ Loaded latest output in left pane: {latest_output['step_name']}")
                    else:
                        logger.warning(f"⚠️ No output available for item {item_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to load content in left pane: {e}")
                    import traceback
                    traceback.print_exc()

            # RIGHT PANE: Display metadata/transcription - ALWAYS show content
            right_pane = self.layout_manager.get_pane(1)
            if right_pane:
                try:
                    # Get transcription using cached data if available
                    transcription_path = await self._get_transcription_text(item_id, output_data)
                    if transcription_path:
                        await right_pane.set_content(
                            file_path=transcription_path,
                            file_type='text',
                            context={'step_name': 'Transcription', 'tool_name': 'transcription'}
                        )
                        logger.info(f"✅ Loaded transcription in right pane")
                    else:
                        # No transcription available - show file metadata instead
                        logger.info(f"📝 No transcription available - showing metadata")

                        # Get item metadata from backend
                        metadata = await self._get_item_metadata_from_backend(item_id)

                        # Create temporary JSON file with metadata
                        import tempfile
                        import json
                        temp_file = Path(tempfile.gettempdir()) / f"metadata_{item_id}.json"
                        with open(temp_file, 'w', encoding='utf-8') as f:
                            json.dump(metadata, f, indent=2, ensure_ascii=False)

                        # Display metadata JSON in right pane
                        await right_pane.set_content(
                            file_path=temp_file,
                            file_type='json',
                            context={'step_name': 'Metadata', 'tool_name': 'metadata'}
                        )
                        logger.info(f"✅ Loaded metadata in right pane")
                except Exception as e:
                    logger.error(f"❌ Failed to load content in right pane: {e}")
                    import traceback
                    traceback.print_exc()

        except Exception as e:
            logger.error(f"Failed to load item: {e}")
            import traceback
            traceback.print_exc()

    async def _get_latest_output(self, item_id: str, output_data: Optional[Dict] = None) -> Optional[Dict]:
        """
        Get latest processing output for an item.
        Returns original file if no processing done yet.

        Args:
            item_id: ID of the item
            output_data: Optional pre-fetched output data (avoids re-querying library_manager)
        """
        try:
            # Use provided output_data if available, otherwise fetch
            if not output_data:
                logger.debug("⚠️ No cached output_data provided, fetching from library_manager")
                output_data = await self.library_manager.get_item_output_data(item_id)
            else:
                logger.debug("✅ Using cached output_data (no database query)")

            if output_data and output_data.get('has_outputs'):
                # Get last step
                steps = output_data.get('processing_steps', [])
                if steps:
                    last_step = steps[-1]
                    return {
                        'file_path': last_step.file_path,
                        'file_type': last_step.file_type,
                        'step_name': last_step.step_name,
                        'tool_name': last_step.tool_name
                    }

            # No processing outputs - return original file
            item = await self.library_manager.get_item(item_id)
            if item:
                # Use direct attributes, not metadata dict
                file_path = item.local_path or item.source_path
                if file_path:
                    return {
                        'file_path': file_path,
                        'file_type': 'image',  # Assume image for now
                        'step_name': 'Original',
                        'tool_name': 'original'
                    }

            return None

        except Exception as e:
            logger.error(f"Failed to get latest output: {e}")
            return None

    # ==================== FILE NAVIGATION ====================

    async def _on_prev_file(self, widget):
        """Navigate to previous file in collection"""
        if self.current_item_index > 0:
            self.current_item_index -= 1
            item = self.current_collection_items[self.current_item_index]
            item_id = item.get('id')
            if item_id:
                await self.load_item(item_id)

    async def _on_next_file(self, widget):
        """Navigate to next file in collection"""
        if self.current_item_index < len(self.current_collection_items) - 1:
            self.current_item_index += 1
            item = self.current_collection_items[self.current_item_index]
            item_id = item.get('id')
            if item_id:
                await self.load_item(item_id)

    # ==================== ZOOM HANDLERS ====================

    def _on_zoom_in(self, widget):
        """Zoom in on current pane"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.zoom_in()

    def _on_zoom_out(self, widget):
        """Zoom out on current pane"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.zoom_out()

    def _on_zoom_fit(self, widget):
        """Fit image to window"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.zoom_fit()

    def _on_zoom_100(self, widget):
        """Reset zoom to 100%"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.zoom_100()

    # ==================== ROTATION HANDLERS ====================

    def _on_rotate_left(self, widget):
        """Rotate image 90° counter-clockwise"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.rotate_left()

    def _on_rotate_right(self, widget):
        """Rotate image 90° clockwise"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.rotate_right()
