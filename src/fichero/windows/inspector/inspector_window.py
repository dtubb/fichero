"""
Inspector Window - Desktop Window Implementation

Preview-style tabbed inspector that displays metadata about the currently selected item.
"""

import logging
import asyncio
from typing import Optional, Dict, Any
import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
from toga.colors import TRANSPARENT

from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation

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
        self.iiif_container: Optional[toga.Box] = None  # New IIIF tab
        self.workflows_container: Optional[toga.Box] = None  # New Workflows tab

        # Subscribe to pane focus events to follow focused pane
        subscribe_to_navigation("PANE_FOCUS_CHANGED", self._on_pane_focus_changed)

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
            # Save state BEFORE closing (weak ref will be invalid after)
            if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
                self.app.window_state_tracker.save_window_state("inspector")
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

    def update_metadata(self, metadata, selection_type: str = None):
        """Update the metadata and refresh display if visible

        Args:
            metadata: The metadata (dict or string - dict is preferred)
            selection_type: Type of selection (e.g., "COLLECTION", "ITEM", "FOLDER")
        """
        try:
            logger.info(f"🔍 Inspector.update_metadata called: type={selection_type}, is_visible={self.is_visible}")

            self.current_selection_type = selection_type

            # Accept either dict (new preferred format) or string (legacy format)
            if isinstance(metadata, dict):
                logger.info(f"✅ Received metadata as dict with {len(metadata)} top-level keys: {list(metadata.keys())}")
                self.current_metadata = metadata
            else:
                # Legacy: parse text metadata into dict
                logger.debug(f"📝 Received metadata as text, parsing... (first 200 chars): {str(metadata)[:200]}")
                self.current_metadata = self._parse_metadata_text(str(metadata))
                logger.info(f"Parsed metadata sections: {list(self.current_metadata.keys())}")

            # If inspector has a container (for mobile or desktop), update the display
            # Works for both desktop window and mobile modal view
            if self.option_container:
                logger.info("Inspector container exists, rebuilding tabs...")
                self._rebuild_tabs()
                logger.info(f"Tabs rebuilt. Current tab count: {len(self.option_container.content)}")
            else:
                logger.info(f"Inspector container not created yet (window={self.window is not None}, container={self.option_container is not None})")
        except Exception as e:
            logger.error(f"Failed to update metadata: {e}", exc_info=True)

    def _on_pane_focus_changed(self, event):
        """Handle pane focus change events - update inspector with focused pane's metadata"""
        try:
            pane = event.data.get('pane')
            if not pane:
                logger.warning("PANE_FOCUS_CHANGED event missing 'pane' data")
                return

            # Only update if inspector is visible
            if not self.is_visible:
                logger.debug("Inspector not visible, skipping pane focus update")
                return

            # Get the item_id and step_index from the pane
            item_id = getattr(pane, 'current_item_id', None)
            step_index = getattr(pane, 'current_step_index', None)

            if not item_id:
                logger.debug("Focused pane has no current item, clearing inspector")
                self.update_metadata({}, selection_type='PANE')
                return

            logger.info(f"🔍 Pane focus changed to item {item_id}, step {step_index}")

            # Fetch metadata from library manager asynchronously
            asyncio.create_task(self._fetch_and_update_pane_metadata(item_id, step_index))

        except Exception as e:
            logger.error(f"Error handling pane focus change: {e}", exc_info=True)

    async def _fetch_and_update_pane_metadata(self, item_id: str, step_index: Optional[int]):
        """Fetch metadata for the focused pane's item and update inspector"""
        try:
            # Get library manager from app
            if not hasattr(self.app, 'library_manager') or not self.app.library_manager:
                logger.warning("Library manager not available")
                return

            library_manager = self.app.library_manager

            # Fetch item metadata
            item = await library_manager.get_item(item_id)
            if not item:
                logger.warning(f"Item {item_id} not found in library")
                return

            # Build metadata dict with item info
            metadata = {
                'id': item.id,
                'name': item.name or '(unnamed)',
                'path': str(item.path) if item.path else '',
                'type': item.type,
                'collection_id': item.collection_id,
            }

            # Add custom metadata if available
            if hasattr(item, 'metadata') and item.metadata:
                metadata.update(item.metadata)

            # Add step information if available
            if step_index is not None:
                metadata['current_step'] = step_index

            logger.info(f"✅ Fetched metadata for item {item_id} from focused pane")
            self.update_metadata(metadata, selection_type='ITEM')

        except Exception as e:
            logger.error(f"Error fetching pane metadata: {e}", exc_info=True)

    def _parse_metadata_text(self, text: str) -> Dict[str, Any]:
        """Parse the text metadata into a dictionary

        This is a temporary solution until views pass structured data.
        Handles multi-line values and nested metadata.
        """
        metadata = {}
        current_section = None
        current_key = None
        accumulated_value = []

        for line in text.split('\n'):
            stripped = line.strip()

            if not stripped:
                continue

            # Section headers (=== SECTION NAME ===)
            if stripped.startswith('===') and stripped.endswith('==='):
                # Save any accumulated value before starting new section
                if current_section and current_key and accumulated_value:
                    metadata[current_section][current_key] = '\n'.join(accumulated_value)
                    accumulated_value = []
                    current_key = None

                current_section = stripped.strip('= ').lower().replace(' ', '_')
                metadata[current_section] = {}

            # Key-value pairs or sub-items
            elif ':' in stripped and current_section:
                # Save previous key's accumulated value
                if current_key and accumulated_value:
                    metadata[current_section][current_key] = '\n'.join(accumulated_value)
                    accumulated_value = []

                key, value = stripped.split(':', 1)
                key = key.strip()
                value = value.strip()

                # Check if this is a sub-header (like "Canvas Metadata:" or "Manifest Metadata:")
                if not value and (key.endswith('Metadata') or key.endswith('metadata')):
                    # This is a sub-header, store as key with empty value for now
                    current_key = key
                    metadata[current_section][key] = ''
                else:
                    # Regular key-value
                    current_key = key
                    if value:
                        metadata[current_section][key] = value
                    else:
                        accumulated_value = []

            # Indented lines (sub-items under a key like Canvas Metadata)
            elif stripped and current_section and current_key:
                accumulated_value.append(stripped)

        # Save any final accumulated value
        if current_section and current_key and accumulated_value:
            metadata[current_section][current_key] = '\n'.join(accumulated_value)

        return metadata

    def _rebuild_tabs(self):
        """Update tab content based on current selection type

        Tabs are fixed and never deleted/recreated - we just update their content
        """
        if not self.general_container or not self.storage_container or not self.details_container or not self.iiif_container or not self.workflows_container:
            logger.warning("Tab containers not initialized")
            return

        # Clear current content from all containers
        self.general_container.clear()
        self.storage_container.clear()
        self.details_container.clear()
        self.iiif_container.clear()
        self.workflows_container.clear()

        # Update content based on selection type
        if self.current_selection_type == "COLLECTION":
            self._update_collection_content()
        elif self.current_selection_type == "FOLDER":
            self._update_folder_content()
        elif self.current_selection_type == "ITEM":
            self._update_item_content()
        elif self.current_selection_type == "STEP":
            self._update_step_content()
        else:
            self._update_no_selection_content()

    def _update_collection_content(self):
        """Update tab content for collection selection - supports both text and dict formats"""
        # Check if using text format (nested sections) or dict format (flat keys)
        has_text_sections = 'collection_metadata' in self.current_metadata or 'storage' in self.current_metadata or 'dates' in self.current_metadata

        if has_text_sections:
            # Legacy text format with nested sections
            name = self.current_metadata.get('collection_metadata', {}).get('Name', 'Unknown')
            coll_id = self.current_metadata.get('collection_metadata', {}).get('ID', 'N/A')
            coll_type = self.current_metadata.get('storage', {}).get('Location', 'Unknown')
            created = self.current_metadata.get('dates', {}).get('Created', 'N/A')
            modified = self.current_metadata.get('dates', {}).get('Modified', 'N/A')
            description = self.current_metadata.get('description', {}).get('DESCRIPTION', '')
        else:
            # New dict format with flat keys (from Collection.to_dict())
            name = self.current_metadata.get('name', 'Unknown')
            coll_id = self.current_metadata.get('id', 'N/A')
            coll_type = self.current_metadata.get('type', 'Unknown')
            created = self.current_metadata.get('created_at', 'N/A')
            modified = self.current_metadata.get('updated_at', 'N/A')
            description = self.current_metadata.get('metadata', {}).get('description', '')

        # General tab - basic info
        general_rows = [
            ("🔍 Inspector ID:", f"{id(self)}"),  # Debug: show instance ID
            ("", ""),
            ("Collection name:", name),
            ("Collection ID:", coll_id),
            ("", ""),
            ("Collection type:", coll_type),
            ("", ""),
            ("Created:", created),
            ("Modified:", modified),
        ]

        # Add description in General if available
        if description and description != 'Unknown':
            general_rows.append(("", ""))
            general_rows.append(("Description:", description))

        self._add_rows_to_container(self.general_container, general_rows)

        # Storage tab - ALL storage/path information
        if has_text_sections:
            # Legacy text format
            storage_metadata = self.current_metadata.get('storage', {})
            storage_type = storage_metadata.get('Location', 'Unknown')
            source_path = storage_metadata.get('Source', '')
            local_path = storage_metadata.get('Workspace', '')
        else:
            # New dict format
            storage_type = coll_type  # Already got this above
            source_path = self.current_metadata.get('source_path', '')
            local_path = self.current_metadata.get('local_path', '')

        storage_rows = [
            ("Storage type:", storage_type),
            ("", ""),
        ]

        # Show ALL paths
        if source_path:
            storage_rows.append(("Source path:", source_path))
        if local_path:
            storage_rows.append(("Workspace path:", local_path))

        self._add_rows_to_container(self.storage_container, storage_rows)

        # Details tab - item breakdown and processing info
        # Note: Collection.to_dict() doesn't include item counts - those come from the UI layer
        # For now, only show this section if we have text format data
        if has_text_sections:
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
        else:
            # New dict format - no item counts in Collection.to_dict()
            self._add_text_to_container(self.details_container, "Collection statistics not available")

        # Update Workflows tab - show processing status
        self._update_workflows_content()

    def _update_folder_content(self):
        """Update tab content for folder selection - show folder metadata"""
        # When metadata is sent as dict (new format), use it directly
        # When sent as text (legacy), it's in 'folder_metadata' section
        if 'folder_metadata' in self.current_metadata:
            # Legacy text format
            folder_data = self.current_metadata.get('folder_metadata', {})
        else:
            # New dict format - use current_metadata directly
            folder_data = self.current_metadata

        logger.info(f"📂 _update_folder_content: folder_data has {len(folder_data)} fields: {list(folder_data.keys())}")

        # General tab - folder info
        general_rows = [
            ("Folder name:", folder_data.get('name', folder_data.get('Name', folder_data.get('Folder', 'Unknown')))),
        ]

        if 'id' in folder_data or 'ID' in folder_data:
            folder_id = folder_data.get('id') or folder_data.get('ID')
            general_rows.append(("Folder ID:", folder_id))

        if 'type' in folder_data or 'Type' in folder_data:
            folder_type = folder_data.get('type') or folder_data.get('Type')
            general_rows.append(("Type:", folder_type))

        # Add IIIF-related general info here
        if 'page_range' in folder_data or 'Page Range' in folder_data:
            page_range = folder_data.get('page_range') or folder_data.get('Page Range')
            general_rows.append(("Page Range:", page_range))

        if 'archive_id' in folder_data or 'Archive ID' in folder_data or 'Archive Id' in folder_data:
            archive_id = folder_data.get('archive_id') or folder_data.get('Archive ID') or folder_data.get('Archive Id')
            if archive_id:
                general_rows.append(("Archive ID:", archive_id))

        general_rows.append(("", ""))

        # Dates if available
        if 'Created' in folder_data:
            general_rows.append(("Created:", folder_data['Created']))
        if 'Modified' in folder_data:
            general_rows.append(("Modified:", folder_data['Modified']))

        self._add_rows_to_container(self.general_container, general_rows)

        # Storage tab - paths
        storage_rows = []

        if 'Path' in folder_data:
            storage_rows.append(("Path:", folder_data['Path']))

        if 'Source' in folder_data:
            storage_rows.append(("Source:", folder_data['Source']))

        if 'Parent ID' in folder_data:
            storage_rows.append(("", ""))
            storage_rows.append(("Parent ID:", folder_data['Parent ID']))

        if storage_rows:
            self._add_rows_to_container(self.storage_container, storage_rows)
        else:
            self._add_text_to_container(self.storage_container, "No storage information")

        # Details tab - contents and other metadata
        contents_metadata = self.current_metadata.get('contents', {})
        details_rows = []

        if 'Total Items' in contents_metadata:
            total = contents_metadata['Total Items']
            details_rows.append(("Total items:", total))

            if total != '0':
                details_rows.append(("", ""))
                # Show item breakdown
                for key, value in contents_metadata.items():
                    if key != 'Total Items':
                        # Remove emoji prefixes for cleaner display
                        clean_key = key.replace('📁 ', '').replace('🔗 ', '').replace('🌐 ', '')
                        details_rows.append((f"{clean_key}:", value))

        # Add any other folder metadata not already shown
        # Exclude fields shown in General tab and IIIF-specific fields
        excluded_keys = [
            # General tab fields
            'name', 'Name', 'Folder', 'id', 'ID', 'type', 'Type', 'page_range', 'Page Range',
            'archive_id', 'Archive ID', 'Archive Id', 'Created', 'Modified',
            # Storage tab fields
            'Path', 'Source', 'Parent ID',
            # IIIF tab fields (will be shown in IIIF tab)
            'manifest_url', 'manifest_label', 'manifest_id', 'manifest_metadata', 'iiif_metadata',
            'logo', 'thumbnail', 'description', 'attribution', 'license',
            'canvas_id', 'canvas_label', 'canvas_width', 'canvas_height', 'canvas_metadata',
            'image_url', 'page_url', 'collection_label', 'manifest_position', 'relative_path'
        ]

        for key, value in folder_data.items():
            if key not in excluded_keys:
                # Format snake_case as Title Case for display
                if '_' in key:
                    display_key = ' '.join(word.capitalize() for word in key.split('_'))
                else:
                    display_key = key
                details_rows.append((f"{display_key}:", str(value)))

        if details_rows:
            self._add_rows_to_container(self.details_container, details_rows)
        else:
            self._add_text_to_container(self.details_container, "Empty folder")

        # IIIF tab - show if folder has IIIF metadata
        self._update_iiif_content()

        # Workflows tab - show processing status if available
        self._update_workflows_content()

    def _update_item_content(self):
        """Update tab content for item selection - show EVERYTHING"""
        # NEW: Metadata comes as dict directly from library_service (same as folders)
        item_data = self.current_metadata

        logger.info(f"📄 _update_item_content: item_data has {len(item_data)} fields: {list(item_data.keys())}")

        # General tab - basic item info
        general_rows = [
            ("🔍 Inspector ID:", f"{id(self)}"),  # Debug: show instance ID
            ("", ""),
            ("Name:", item_data.get('name', item_data.get('title', 'Unknown'))),
        ]

        if 'type' in item_data:
            general_rows.append(("Type:", item_data['type']))
        if 'id' in item_data:
            general_rows.append(("ID:", item_data['id']))

        # Add IIIF-related general info
        if 'archive_id' in item_data and item_data['archive_id']:
            general_rows.append(("Archive ID:", item_data['archive_id']))
        if 'collection_label' in item_data and item_data['collection_label']:
            general_rows.append(("Collection:", item_data['collection_label']))

        self._add_rows_to_container(self.general_container, general_rows)

        # Storage tab - paths and location
        storage_rows = []
        if 'file_path' in item_data or 'path' in item_data or 'source_path' in item_data:
            if 'file_path' in item_data:
                storage_rows.append(("File Path:", item_data['file_path']))
            if 'path' in item_data:
                storage_rows.append(("Path:", item_data['path']))
            if 'source_path' in item_data:
                storage_rows.append(("Source Path:", item_data['source_path']))
            if 'storage_type' in item_data:
                storage_rows.append(("Storage Type:", item_data['storage_type']))

        if storage_rows:
            self._add_rows_to_container(self.storage_container, storage_rows)
        else:
            self._add_text_to_container(self.storage_container, "No storage information")

        # Details tab - show other metadata (size, dates, etc.)
        details_rows = []

        # Skip IIIF fields and basic fields already shown
        skip_fields = ['id', 'name', 'title', 'type', 'file_path', 'path', 'source_path', 'storage_type',
                       'manifest_url', 'manifest_label', 'manifest_id', 'archive_id', 'canvas_id', 'image_url',
                       'description', 'attribution', 'license', 'logo', 'thumbnail', 'iiif_metadata',
                       'manifest_metadata', 'collection_label', 'canvas_metadata', 'canvas_label',
                       'canvas_width', 'canvas_height', 'page_range', 'metadata']  # Skip raw metadata dict

        for key, value in item_data.items():
            if key not in skip_fields and value:
                # Format key nicely
                nice_key = key.replace('_', ' ').title()
                details_rows.append((f"{nice_key}:", str(value)))

        if details_rows:
            self._add_rows_to_container(self.details_container, details_rows)
        else:
            self._add_text_to_container(self.details_container, "No additional details")

        # IIIF tab - show IIIF-specific metadata if available (shared with folders)
        self._update_iiif_content()

        # Workflows tab - show processing status if available
        self._update_workflows_content()

    def _update_iiif_content(self):
        """Update IIIF tab content - show structured IIIF metadata"""
        logger.info(f"🔍 _update_iiif_content: current_metadata has {len(self.current_metadata)} keys: {list(self.current_metadata.keys())}")

        # Detect format: TEXT (has sections like 'iiif_metadata', 'item_metadata') vs DICT (has direct fields)
        # TEXT format: keys are section names like 'item_metadata', 'iiif_metadata', 'folder_metadata'
        # DICT format: keys are actual metadata fields like 'manifest_url', 'archive_id', etc.

        text_format_sections = ['item_metadata', 'folder_metadata', 'collection_metadata', 'contents', 'storage', 'dates']
        has_text_sections = any(k in self.current_metadata for k in text_format_sections)

        if has_text_sections:
            # LEGACY TEXT FORMAT: Look for iiif_metadata or additional_metadata sections
            logger.info(f"📝 Using LEGACY text format (has sections), looking for IIIF sections...")
            iiif_metadata = None
            additional_metadata = None

            for section_name, section_data in self.current_metadata.items():
                if 'iiif' in section_name.lower():
                    iiif_metadata = section_data
                    logger.info(f"✅ Found IIIF section '{section_name}'")
                elif 'additional' in section_name.lower():
                    additional_metadata = section_data
                    logger.info(f"✅ Found Additional section '{section_name}'")

            # Combine both sections if they exist
            combined_metadata = {}
            if iiif_metadata and isinstance(iiif_metadata, dict):
                combined_metadata.update(iiif_metadata)
            if additional_metadata and isinstance(additional_metadata, dict):
                combined_metadata.update(additional_metadata)
        else:
            # NEW DICT FORMAT: Use current_metadata directly (snake_case keys from database)
            logger.info(f"✅ Using NEW dict format with direct fields (no sections)")
            combined_metadata = self.current_metadata.copy()

            # If there's a nested 'metadata' dict, merge its fields into combined_metadata
            if 'metadata' in self.current_metadata and isinstance(self.current_metadata['metadata'], dict):
                logger.info(f"📦 Found nested metadata dict with {len(self.current_metadata['metadata'])} fields, merging...")
                combined_metadata.update(self.current_metadata['metadata'])

        logger.info(f"📊 Combined IIIF metadata has {len(combined_metadata)} fields: {list(combined_metadata.keys())[:10]}")

        if not combined_metadata:
            logger.warning("⚠️ No IIIF metadata found to display")
            self._add_text_to_container(self.iiif_container, "No IIIF metadata")
            return

        # Build structured rows for IIIF metadata
        iiif_rows = []

        # Manifest information (check both snake_case and Title Case)
        if 'manifest_label' in combined_metadata or 'Manifest Label' in combined_metadata:
            label = combined_metadata.get('manifest_label') or combined_metadata.get('Manifest Label')
            if label:
                iiif_rows.append(("Manifest Label:", label))
        if 'manifest_url' in combined_metadata or 'Manifest URL' in combined_metadata or 'Manifest Url' in combined_metadata:
            url = combined_metadata.get('manifest_url') or combined_metadata.get('Manifest URL') or combined_metadata.get('Manifest Url')
            if url:
                iiif_rows.append(("Manifest URL:", url))
        if 'manifest_id' in combined_metadata or 'Manifest Id' in combined_metadata or 'Manifest ID' in combined_metadata:
            mid = combined_metadata.get('manifest_id') or combined_metadata.get('Manifest Id') or combined_metadata.get('Manifest ID')
            if mid:
                iiif_rows.append(("Manifest ID:", mid))

        # Page/folder specific info (snake_case and Title Case)
        if 'page_range' in combined_metadata or 'Page Range' in combined_metadata:
            page_range = combined_metadata.get('page_range') or combined_metadata.get('Page Range')
            if page_range:
                iiif_rows.append(("Page Range:", page_range))
        if 'archive_id' in combined_metadata or 'Archive Id' in combined_metadata or 'Archive ID' in combined_metadata:
            archive_id = combined_metadata.get('archive_id') or combined_metadata.get('Archive Id') or combined_metadata.get('Archive ID')
            if archive_id:
                iiif_rows.append(("Archive ID:", archive_id))

        # Image information
        if 'Image URL' in combined_metadata or 'Image Url' in combined_metadata:
            image_url = combined_metadata.get('Image URL') or combined_metadata.get('Image Url')
            iiif_rows.append(("Image URL:", image_url))
        if 'Canvas' in combined_metadata or 'Canvas Id' in combined_metadata or 'Canvas ID' in combined_metadata:
            canvas = combined_metadata.get('Canvas') or combined_metadata.get('Canvas Id') or combined_metadata.get('Canvas ID')
            iiif_rows.append(("Canvas:", canvas))
        if 'Dimensions' in combined_metadata:
            iiif_rows.append(("Dimensions:", combined_metadata['Dimensions']))

        # Collection info
        if 'Collection' in combined_metadata:
            iiif_rows.append(("Collection:", combined_metadata['Collection']))

        # Description and attribution
        if 'Description' in combined_metadata:
            iiif_rows.append(("", ""))  # Spacer
            iiif_rows.append(("Description:", combined_metadata['Description']))
        if 'Attribution' in combined_metadata:
            if not iiif_rows or iiif_rows[-1] != ("", ""):
                iiif_rows.append(("", ""))  # Spacer
            iiif_rows.append(("Attribution:", combined_metadata['Attribution']))
        if 'License' in combined_metadata:
            iiif_rows.append(("License:", combined_metadata['License']))

        # Logo and thumbnail (check both snake_case and Title Case)
        if 'logo' in combined_metadata or 'Logo' in combined_metadata:
            logo = combined_metadata.get('logo') or combined_metadata.get('Logo')
            if logo:
                iiif_rows.append(("", ""))  # Spacer
                iiif_rows.append(("Logo:", logo))
        if 'thumbnail' in combined_metadata or 'Thumbnail' in combined_metadata:
            thumbnail = combined_metadata.get('thumbnail') or combined_metadata.get('Thumbnail')
            if thumbnail:
                iiif_rows.append(("Thumbnail:", thumbnail))

        # Additional IIIF fields from database (snake_case)
        if 'canvas_id' in combined_metadata:
            iiif_rows.append(("Canvas ID:", combined_metadata['canvas_id']))
        if 'canvas_label' in combined_metadata:
            iiif_rows.append(("Canvas Label:", combined_metadata['canvas_label']))
        if 'canvas_width' in combined_metadata and 'canvas_height' in combined_metadata:
            dims = f"{combined_metadata['canvas_width']} x {combined_metadata['canvas_height']}"
            iiif_rows.append(("Canvas Dimensions:", dims))
        if 'image_url' in combined_metadata:
            iiif_rows.append(("Image URL:", combined_metadata['image_url']))
        if 'page_url' in combined_metadata:
            iiif_rows.append(("Page URL:", combined_metadata['page_url']))
        if 'collection_label' in combined_metadata:
            iiif_rows.append(("Collection Label:", combined_metadata['collection_label']))

        # Canvas Metadata section
        if 'Canvas Metadata' in combined_metadata:
            iiif_rows.append(("", ""))  # Spacer
            iiif_rows.append(("Canvas Metadata:", ""))
            canvas_meta_text = combined_metadata['Canvas Metadata']
            if canvas_meta_text:
                iiif_rows.append(("", canvas_meta_text))

        # IIIF metadata array (snake_case from database) - MOST IMPORTANT!
        # Check both iiif_metadata (used by folders) and manifest_metadata (used by items)
        metadata_array = None
        if 'iiif_metadata' in combined_metadata and isinstance(combined_metadata['iiif_metadata'], list):
            metadata_array = combined_metadata['iiif_metadata']
        elif 'manifest_metadata' in combined_metadata and isinstance(combined_metadata['manifest_metadata'], list):
            metadata_array = combined_metadata['manifest_metadata']

        if metadata_array:
            iiif_rows.append(("", ""))  # Spacer
            iiif_rows.append(("IIIF Metadata:", ""))
            for meta in metadata_array:
                if isinstance(meta, dict):
                    label = meta.get('label', '')
                    value = meta.get('value', '')
                    if label and value:
                        iiif_rows.append((f"  {label}:", value))

        # Manifest Metadata or IIIF Metadata section (Title Case from legacy text format)
        elif 'Manifest Metadata' in combined_metadata:
            iiif_rows.append(("", ""))  # Spacer
            iiif_rows.append(("Manifest Metadata:", ""))
            manifest_meta_text = combined_metadata['Manifest Metadata']
            if manifest_meta_text:
                iiif_rows.append(("", manifest_meta_text))
        elif 'Iiif Metadata' in combined_metadata or 'Iiif_Metadata' in combined_metadata:
            iiif_rows.append(("", ""))  # Spacer
            iiif_rows.append(("IIIF Metadata:", ""))
            iiif_meta_text = combined_metadata.get('Iiif Metadata') or combined_metadata.get('Iiif_Metadata')
            if iiif_meta_text:
                iiif_rows.append(("", str(iiif_meta_text)))

        # Add all remaining IIIF-related fields not explicitly handled
        # Exclude basic item/folder fields that aren't IIIF-specific
        handled_keys = [
            # snake_case (from database)
            'manifest_label', 'manifest_url', 'manifest_id', 'page_range', 'archive_id',
            'iiif_metadata', 'manifest_metadata', 'logo', 'thumbnail', 'description', 'attribution', 'license',
            'canvas_id', 'canvas_label', 'canvas_width', 'canvas_height', 'canvas_metadata',
            'image_url', 'page_url', 'collection_label', 'manifest_position',
            # Title Case (from legacy text format)
            'Manifest Label', 'Manifest URL', 'Manifest Url', 'Manifest', 'Manifest Id', 'Manifest ID',
            'Page Range', 'Archive Id', 'Archive ID', 'Image URL', 'Image Url', 'Canvas', 'Canvas Id',
            'Canvas ID', 'Dimensions', 'Collection', 'Description', 'Attribution', 'License', 'Logo',
            'Thumbnail', 'Canvas Metadata', 'Manifest Metadata', 'Iiif Metadata', 'Iiif_Metadata'
        ]

        # Exclude basic non-IIIF fields
        basic_fields = ['id', 'name', 'title', 'type', 'is_folder', 'path', 'file_path', 'source',
                       'relative_path', 'storage_type', 'source_path', 'local_path']

        for key, value in combined_metadata.items():
            if key not in handled_keys and key not in basic_fields:
                # Only add if it looks IIIF-related (contains iiif, manifest, canvas, etc.)
                key_lower = key.lower()
                if any(term in key_lower for term in ['iiif', 'manifest', 'canvas', 'image', 'collection']):
                    # Format snake_case as Title Case for display
                    if '_' in key:
                        display_key = ' '.join(word.capitalize() for word in key.split('_'))
                    else:
                        display_key = key
                    iiif_rows.append((f"{display_key}:", str(value)))

        logger.info(f"🎨 Built {len(iiif_rows)} IIIF rows to display")
        if iiif_rows:
            logger.info(f"   First few rows: {iiif_rows[:3]}")
            self._add_rows_to_container(self.iiif_container, iiif_rows)
            logger.info(f"✅ Added {len(iiif_rows)} rows to IIIF container")
        else:
            logger.warning("⚠️ No IIIF rows built, showing 'No IIIF metadata' message")
            self._add_text_to_container(self.iiif_container, "No IIIF metadata")

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
        self._add_text_to_container(self.iiif_container, "No IIIF metadata")
        self._add_text_to_container(self.workflows_container, "No workflows")

    def _update_workflows_content(self):
        """Update Workflows tab - show processing workflows for collections, items, and folders"""
        try:
            # For ITEMS and FOLDERS: Query processing history from library database
            if self.current_selection_type in ("ITEM", "FOLDER"):
                item_id = self.current_metadata.get('id')

                if not item_id:
                    self._add_text_to_container(self.workflows_container, "No item ID available")
                    return

                # Get processing history from library database
                if not hasattr(self.app, 'library_manager') or not self.app.library_manager:
                    self._add_text_to_container(self.workflows_container, "Library manager not available")
                    return

                try:
                    # Query database for ALL workflow runs for this item
                    processing_history = self.app.library_manager.storage.get_processing_history(item_id)

                    if not processing_history:
                        self._add_text_to_container(self.workflows_container, "No workflow processing for this item")
                        return

                    # Display all workflow runs (already sorted newest first by the query)
                    for i, result in enumerate(processing_history):
                        if i > 0:
                            # Add divider between runs
                            self._add_workflow_divider(self.workflows_container)

                        # Display this workflow run
                        self._add_workflow_result(self.workflows_container, result)

                except Exception as e:
                    logger.error(f"Failed to get processing history: {e}")
                    self._add_text_to_container(self.workflows_container, f"Error loading workflow history: {str(e)}")

                return

            # For COLLECTIONS: Show collection-level workflow status
            if self.current_selection_type != "COLLECTION":
                self._add_text_to_container(self.workflows_container, "No workflows")
                return

            # Get collection path from metadata
            # For internal collections, local_path is NULL - compute from collection ID
            local_path = self.current_metadata.get('local_path')
            collection_id = self.current_metadata.get('id')

            # Import required modules
            from pathlib import Path
            import asyncio

            # Get the app's bridge to access workflow status
            if not hasattr(self.app, 'library_integration_bridge') or not self.app.library_integration_bridge:
                self._add_text_to_container(self.workflows_container, "Director integration not available")
                return

            # Compute collection path
            if local_path:
                collection_path = Path(local_path)
            elif collection_id:
                # Internal collection - compute from library path
                if hasattr(self.app, 'library_manager') and self.app.library_manager:
                    collection_path = self.app.library_manager.library_path / "collections" / collection_id
                else:
                    self._add_text_to_container(self.workflows_container, "Library manager not available")
                    return
            else:
                self._add_text_to_container(self.workflows_container, "Collection path not available")
                return

            if not collection_path.exists():
                self._add_text_to_container(self.workflows_container, f"Collection path not found: {collection_path}")
                return

            # Get processing status from bridge (async call)
            try:
                loop = asyncio.get_event_loop()
                status = loop.run_until_complete(
                    self.app.library_integration_bridge.get_collection_processing_status(collection_path)
                )
            except RuntimeError:
                # No event loop - create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                status = loop.run_until_complete(
                    self.app.library_integration_bridge.get_collection_processing_status(collection_path)
                )

            if not status or 'steps_status' not in status:
                self._add_text_to_container(self.workflows_container, "No workflow status available")
                return

            # Build rows for workflow status
            workflow_rows = [
                ("Total files:", str(status.get('total_files', 0))),
                ("Available steps:", str(len(status.get('available_steps', [])))),
                ("", ""),  # Spacer
            ]

            # Add each step's status
            for step_name, step_status in status['steps_status'].items():
                status_text = step_status['status']
                if status_text == 'completed':
                    status_text = "Completed"
                elif status_text == 'pending':
                    status_text = "Pending"

                file_count = step_status['file_count']
                workflow_rows.append((f"{step_name}:", f"{status_text} ({file_count} files)"))

            self._add_rows_to_container(self.workflows_container, workflow_rows)

        except Exception as e:
            logger.error(f"Failed to update workflows content: {e}")
            self._add_text_to_container(self.workflows_container, f"Error loading workflows: {str(e)}")

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
                row = toga.Box(style=Pack(direction=ROW, margin_bottom=3, align_items='start'))

                # Label (right-aligned, fixed width)
                label_widget = toga.Label(
                    label,
                    style=Pack(
                        width=110,
                        text_align='right',
                        margin_right=8,
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
                            margin=2,
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
            style=Pack(margin=20, text_align='center', font_size=8)
        )
        container.add(label)

    def _add_running_workflow_status(self, container, workflow_name: str, status: str, progress: float):
        """
        Add running workflow status display at the top of Workflows tab

        Args:
            container: The container to add to
            workflow_name: Name of the workflow being run
            status: Status (pending/running)
            progress: Progress percentage (0-100)
        """
        # Status header with spinning indicator
        status_text = f"⏳ {workflow_name} - {status.capitalize()}"
        if progress > 0:
            status_text += f" ({progress:.0f}%)"

        header = toga.Label(
            status_text,
            style=Pack(
                font_size=10,
                font_weight='bold',
                margin_bottom=5
            )
        )
        container.add(header)

        # Progress bar (simple text representation)
        if progress > 0:
            bar_width = 40
            filled = int((progress / 100) * bar_width)
            empty = bar_width - filled
            progress_bar = '[' + '█' * filled + '░' * empty + ']'

            progress_label = toga.Label(
                progress_bar,
                style=Pack(
                    font_family='monospace',
                    font_size=8,
                    margin_bottom=5
                )
            )
            container.add(progress_label)

    def _add_workflow_divider(self, container):
        """Add a divider between workflow runs"""
        divider = toga.Box(
            style=Pack(
                height=1,
                background_color='#CCCCCC',
                margin_top=10,
                margin_bottom=10
            )
        )
        container.add(divider)

    def _add_workflow_result(self, container, result):
        """Add a ProcessingResult entry with Show in Finder button

        Args:
            container: The container to add to
            result: ProcessingResult object from database with fields:
                - workflow: str
                - status: str (success/failed/partial)
                - started_at: datetime
                - completed_at: datetime
                - output_paths: List[str]
                - processing_time: float (optional)
                - metadata: dict (optional)
        """
        from pathlib import Path
        import subprocess

        # Format timestamp
        if result.completed_at:
            timestamp = result.completed_at.strftime("%Y-%m-%d %H:%M")
        elif result.started_at:
            timestamp = result.started_at.strftime("%Y-%m-%d %H:%M") + " (in progress)"
        else:
            timestamp = "Unknown time"

        # Status emoji
        status_emoji = {
            "success": "✅",
            "failed": "❌",
            "partial": "⚠️"
        }.get(result.status, "❓")

        # Workflow name, status, and timestamp
        header = toga.Label(
            f"{status_emoji} {result.workflow} - {timestamp}",
            style=Pack(
                font_size=9,
                font_weight='bold',
                margin_bottom=5
            )
        )
        container.add(header)

        # Processing time if available
        if result.processing_time:
            time_label = toga.Label(
                f"Processing time: {result.processing_time:.1f}s",
                style=Pack(
                    font_size=8,
                    margin_bottom=3
                )
            )
            container.add(time_label)

        # Add "Show in Finder" button for each output path
        if result.output_paths:
            for output_path in result.output_paths:
                def make_open_handler(path):
                    """Create a handler for this specific path"""
                    def open_in_finder(widget):
                        """Open the output path in Finder"""
                        try:
                            p = Path(path)
                            if p.exists():
                                subprocess.run(['open', str(p)], check=True)
                                logger.info(f"Opened in Finder: {p}")
                            else:
                                logger.warning(f"Output path does not exist: {p}")
                        except Exception as e:
                            logger.error(f"Failed to open in Finder: {e}")
                    return open_in_finder

                # Show truncated path
                path_display = str(output_path)
                if len(path_display) > 60:
                    path_display = "..." + path_display[-57:]

                path_label = toga.Label(
                    path_display,
                    style=Pack(
                        font_size=8,
                        margin_bottom=2
                    )
                )
                container.add(path_label)

                button = toga.Button(
                    "Show in Finder",
                    on_press=make_open_handler(output_path),
                    style=Pack(
                        width=120,
                        font_size=8,
                        margin_bottom=8
                    )
                )
                container.add(button)
        else:
            # No outputs available
            no_output_label = toga.Label(
                "No output files",
                style=Pack(
                    font_size=8,
                    margin_bottom=5
                )
            )
            container.add(no_output_label)

        # Add delete button for this workflow result
        def delete_workflow(widget):
            """Delete this workflow result from library (DB + filesystem)"""
            try:
                # Ask library to delete this processing result
                success = self.app.library_manager.delete_processing_result(result.id)
                if success:
                    logger.info(f"Deleted workflow result {result.id}")
                    # Clear and refresh the entire workflows container
                    self.workflows_container.clear()
                    self._update_workflows_content()
                else:
                    logger.error(f"Failed to delete workflow result {result.id}")
            except Exception as e:
                logger.error(f"Error deleting workflow: {e}")

        delete_button = toga.Button(
            "Delete Workflow",
            on_press=delete_workflow,
            style=Pack(
                width=120,
                font_size=8,
                margin_bottom=10
            )
        )
        container.add(delete_button)

    def _add_output_path_button(self, container, output_path: str):
        """Add just a button to open output path in Finder

        Args:
            container: The container to add to
            output_path: Path to open
        """
        from pathlib import Path
        import subprocess

        def open_in_finder(widget):
            """Open the output path in Finder"""
            try:
                path = Path(output_path)
                if path.exists():
                    subprocess.run(['open', str(path)], check=True)
                    logger.info(f"Opened in Finder: {path}")
                else:
                    logger.warning(f"Output path does not exist: {path}")
            except Exception as e:
                logger.error(f"Failed to open in Finder: {e}")

        button = toga.Button(
            "Show in Finder",
            on_press=open_in_finder,
            style=Pack(
                width=120,
                font_size=8,
                margin_top=5
            )
        )
        container.add(button)

    def _create_info_rows(self, rows):
        """Create a Preview-style two-column layout for info rows

        Args:
            rows: List of (label, value) tuples
        """
        container = toga.Box(style=Pack(direction=COLUMN, margin=10))

        for label, value in rows:
            if not label and not value:
                # Spacer
                container.add(toga.Box(style=Pack(height=10)))
            else:
                row = toga.Box(style=Pack(direction=ROW, margin_bottom=5))

                # Label (right-aligned)
                label_widget = toga.Label(
                    label,
                    style=Pack(
                        width=140,
                        text_align='right',
                        margin_right=10,
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
            style=Pack(direction=COLUMN, flex=1, margin=10),
            children=[text_widget]
        )

        return box

    def create_content(self):
        """Create inspector content (for use in modal views on mobile)"""
        # Create the content structure if it doesn't exist
        if not self.option_container:
            self._create_content_structure()

            # If metadata was already set (before container was created), rebuild tabs now
            if self.current_metadata:
                logger.info("Rebuilding tabs with pre-existing metadata after container creation")
                self._rebuild_tabs()

        return self.option_container

    def _create_content_structure(self):
        """Create the content structure (OptionContainer with tabs)"""
        # Create OptionContainer for tabs (it has its own native background)
        # Add small margins on all sides
        self.option_container = toga.OptionContainer(
            style=Pack(flex=1, margin=10)
        )

        # Create fixed containers for each tab - use TRANSPARENT background
        self.general_container = toga.Box(
            style=Pack(direction=COLUMN, margin=10, background_color=TRANSPARENT)
        )
        self.storage_container = toga.Box(
            style=Pack(direction=COLUMN, margin=10, background_color=TRANSPARENT)
        )
        self.details_container = toga.Box(
            style=Pack(direction=COLUMN, margin=10, background_color=TRANSPARENT)
        )
        self.iiif_container = toga.Box(
            style=Pack(direction=COLUMN, margin=10, background_color=TRANSPARENT)
        )
        self.workflows_container = toga.Box(
            style=Pack(direction=COLUMN, margin=10, background_color=TRANSPARENT)
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
        iiif_scroll = toga.ScrollContainer(
            content=self.iiif_container,
            style=Pack(flex=1, background_color=TRANSPARENT),
            horizontal=False  # Disable horizontal scroll
        )
        workflows_scroll = toga.ScrollContainer(
            content=self.workflows_container,
            style=Pack(flex=1, background_color=TRANSPARENT),
            horizontal=False  # Disable horizontal scroll
        )

        # Add fixed tabs (these never change)
        self.option_container.content.append("General", general_scroll)
        self.option_container.content.append("Storage", storage_scroll)
        self.option_container.content.append("Details", details_scroll)
        self.option_container.content.append("IIIF", iiif_scroll)
        self.option_container.content.append("Workflows", workflows_scroll)

        # Initial state - no selection
        self._update_no_selection_content()

    def _create_window(self):
        """Create the inspector window with fixed tabs"""
        try:
            # Create the content structure first
            self._create_content_structure()

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

            # Register with window state tracker for position/size persistence
            if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
                self.app.window_state_tracker.register_window("inspector", self.window, restore=True)

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
