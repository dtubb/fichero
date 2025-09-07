"""
Collection Bottom Toolbar for Fichero

Bottom toolbar for collection view with file actions and collection management.
Shows different buttons based on what's selected (collections, folders, files).
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable, List, Dict, Any

from fichero.windows.main.toolbars.bottom_toolbar import BottomToolbar

logger = logging.getLogger(__name__)


class CollectionBottomToolbar(BottomToolbar):
    """
    Bottom toolbar for collection view with context-sensitive actions
    
    Shows different actions based on selection:
    - No selection: Collection management
    - Files selected: File actions (preview, process, etc.)  
    - Folders selected: Folder actions
    """
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize collection bottom toolbar"""
        super().__init__(app, is_mobile)
        
        # Selection context
        self.selected_items: List[Dict] = []
        self.selection_type: str = "none"  # none, files, folders, mixed
        
        # Collection-specific callbacks
        self.on_collection_settings: Optional[Callable] = None
        self.on_process_files: Optional[Callable] = None
        self.on_preview_file: Optional[Callable] = None
        self.on_add_to_collection: Optional[Callable] = None
        self.on_export_selection: Optional[Callable] = None
        self.on_delete_selection: Optional[Callable] = None
        self.on_edit_metadata: Optional[Callable] = None
        
        # UI components (will be created dynamically)
        self.action_buttons: Dict[str, toga.Button] = {}
        self.selection_label: Optional[toga.Label] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the collection bottom toolbar with default state"""
        try:
            # Start with default collection management mode
            self._create_default_actions()
            
            logger.info("Collection bottom toolbar created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create collection bottom toolbar: {e}")
    
    def _create_default_actions(self):
        """Create default collection management actions"""
        try:
            # Clear existing content
            self._clear_toolbar()
            
            # Keep toolbar completely empty - no buttons or labels needed
            
        except Exception as e:
            logger.error(f"Failed to create default actions: {e}")
    
    def _create_file_actions(self):
        """Create file-specific actions when files are selected - only working buttons"""
        try:
            # Clear existing buttons (keep selection label)
            self._clear_action_buttons()
            
            # Preview button (center) - THIS WORKS through the preview callback system
            preview_btn = self.create_icon_button(
                button_id="preview_file",
                icon="magnifyingglass",
                on_press=self._on_preview_file_clicked,
                tooltip="Preview File"
            )
            self.add_to_center(preview_btn)
            self.action_buttons["preview_file"] = preview_btn
            
            # Collection settings (right) - Keep for consistency with default view
            settings_btn = self.create_icon_button(
                button_id="collection_settings",
                icon="collection_settings",
                on_press=self._on_collection_settings_clicked,
                tooltip="Collection Settings"
            )
            self.add_to_right(settings_btn)
            self.action_buttons["collection_settings"] = settings_btn
            
        except Exception as e:
            logger.error(f"Failed to create file actions: {e}")
    
    def _create_folder_actions(self):
        """Create folder-specific actions when folders are selected - only working buttons"""
        try:
            # Clear existing buttons (keep selection label)
            self._clear_action_buttons()
            
            # For folders, just show collection settings
            settings_btn = self.create_icon_button(
                button_id="collection_settings",
                icon="collection_settings",
                on_press=self._on_collection_settings_clicked,
                tooltip="Collection Settings"
            )
            self.add_to_right(settings_btn)
            self.action_buttons["collection_settings"] = settings_btn
            
        except Exception as e:
            logger.error(f"Failed to create folder actions: {e}")
    
    def _clear_toolbar(self):
        """Clear all toolbar content"""
        try:
            # Clear content areas
            if hasattr(self, 'left_content'):
                for child in list(self.left_content.children):
                    self.left_content.remove(child)
            if hasattr(self, 'content'):
                for child in list(self.content.children):
                    if child not in [self.left_content, self.right_content]:
                        self.content.remove(child)
            if hasattr(self, 'right_content'):
                for child in list(self.right_content.children):
                    self.right_content.remove(child)
            
            # Clear references
            self.action_buttons.clear()
            self.selection_label = None
            
        except Exception as e:
            logger.error(f"Failed to clear toolbar: {e}")
    
    def _clear_action_buttons(self):
        """Clear action buttons but keep selection label"""
        try:
            # Clear center and right content
            if hasattr(self, 'content'):
                for child in list(self.content.children):
                    if child not in [self.left_content, self.right_content]:
                        self.content.remove(child)
            if hasattr(self, 'right_content'):
                for child in list(self.right_content.children):
                    self.right_content.remove(child)
            
            # Clear button references (but keep selection label)
            self.action_buttons.clear()
            
        except Exception as e:
            logger.error(f"Failed to clear action buttons: {e}")
    
    def update_selection(self, selected_items: List[Dict]):
        """
        Update toolbar based on current selection
        
        Args:
            selected_items: List of selected item dictionaries
        """
        try:
            self.selected_items = selected_items
            
            # Determine selection type
            if not selected_items:
                self.selection_type = "none"
            else:
                # Analyze selection to determine type
                file_count = sum(1 for item in selected_items if item.get('type') == 'file')
                folder_count = sum(1 for item in selected_items if item.get('type') == 'folder')
                
                if file_count > 0 and folder_count == 0:
                    self.selection_type = "files"
                elif folder_count > 0 and file_count == 0:
                    self.selection_type = "folders"
                elif file_count > 0 and folder_count > 0:
                    self.selection_type = "mixed"
                else:
                    self.selection_type = "none"
            
            # Update UI based on selection
            self._update_toolbar_for_selection()
            
            logger.debug(f"Updated selection: {len(selected_items)} items ({self.selection_type})")
            
        except Exception as e:
            logger.error(f"Failed to update selection: {e}")
    
    def _update_toolbar_for_selection(self):
        """Update toolbar layout based on current selection type"""
        try:
            # Update selection label
            if self.selection_label:
                if self.selection_type == "none":
                    self.selection_label.text = "Ready"
                else:
                    count = len(self.selected_items)
                    item_text = "item" if count == 1 else "items"
                    self.selection_label.text = f"{count} {item_text} selected"
            
            # Update actions based on selection type
            if self.selection_type == "none":
                self._create_default_actions()
            elif self.selection_type == "files":
                self._create_file_actions()
            elif self.selection_type == "folders":
                self._create_folder_actions()
            elif self.selection_type == "mixed":
                # For mixed selection, show general actions
                self._create_file_actions()  # Use file actions as they're more comprehensive
            
        except Exception as e:
            logger.error(f"Failed to update toolbar for selection: {e}")
    
    # Event handlers
    def _on_collection_settings_clicked(self, widget):
        """Handle collection settings button click"""
        logger.debug("Collection settings clicked")
        if self.on_collection_settings:
            self.on_collection_settings()
    
    def _on_process_files_clicked(self, widget):
        """Handle process files button click"""
        logger.debug("Process files clicked")
        if self.on_process_files:
            self.on_process_files(self.selected_items)
    
    def _on_preview_file_clicked(self, widget):
        """Handle preview file button click"""
        logger.debug("Preview file clicked")
        if self.on_preview_file and self.selected_items:
            # Preview the first selected file
            first_file = next((item for item in self.selected_items if item.get('type') == 'file'), None)
            if first_file:
                self.on_preview_file(first_file)
    
    def _on_add_to_collection_clicked(self, widget):
        """Handle add to collection button click"""
        logger.debug("Add to collection clicked")
        if self.on_add_to_collection:
            self.on_add_to_collection(self.selected_items)
    
    def _on_export_selection_clicked(self, widget):
        """Handle export selection button click"""
        logger.debug("Export selection clicked")
        if self.on_export_selection:
            self.on_export_selection(self.selected_items)
    
    def _on_delete_selection_clicked(self, widget):
        """Handle delete selection button click"""
        logger.debug("Delete selection clicked")
        if self.on_delete_selection:
            self.on_delete_selection(self.selected_items)
    
    def _on_edit_metadata_clicked(self, widget):
        """Handle edit metadata button click"""
        logger.debug("Edit metadata clicked")
        if self.on_edit_metadata:
            self.on_edit_metadata(self.selected_items)
    
    def register_callbacks(self, 
                         on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_collection_settings: Optional[Callable] = None,
                         on_process_files: Optional[Callable] = None,
                         on_preview_file: Optional[Callable] = None,
                         on_add_to_collection: Optional[Callable] = None,
                         on_export_selection: Optional[Callable] = None,
                         on_delete_selection: Optional[Callable] = None,
                         on_edit_metadata: Optional[Callable] = None):
        """Register callbacks for collection bottom toolbar actions"""
        super().register_callbacks(on_settings, on_about, on_help)
        
        self.on_collection_settings = on_collection_settings
        self.on_process_files = on_process_files
        self.on_preview_file = on_preview_file
        self.on_add_to_collection = on_add_to_collection
        self.on_export_selection = on_export_selection
        self.on_delete_selection = on_delete_selection
        self.on_edit_metadata = on_edit_metadata
        
        logger.debug("Collection bottom toolbar callbacks registered")
    
    def update_status(self, status_text: str):
        """Update the status information"""
        if self.selection_label:
            self.selection_label.text = status_text 