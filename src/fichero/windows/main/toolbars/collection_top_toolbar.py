"""
Collection Top Toolbar for Fichero

Top toolbar for collection view with hierarchical navigation and breadcrumbs.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable, List

from fichero.windows.main.toolbars.top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class CollectionTopToolbar(TopToolbar):
    """Top toolbar for collection view with hierarchical navigation"""
    
    def __init__(self, app, collection_name: str = "", is_mobile: bool = False):
        """Initialize collection top toolbar"""
        super().__init__(app, is_mobile)
        
        # Collection context
        self.collection_name = collection_name
        self.current_path = ""
        self.path_history: List[str] = []
        
        # Navigation callbacks
        self.on_back_to_library: Optional[Callable] = None
        self.on_add_folder: Optional[Callable] = None
        self.on_add_file: Optional[Callable] = None
        self.on_navigate_back: Optional[Callable] = None
        self.on_navigate_to_path: Optional[Callable[[str], None]] = None
        
        # UI components
        self.breadcrumb_container = None
        self.back_btn = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the collection top toolbar content with proper navigation"""
        try:
            # Single back button (left) - handles both library and folder navigation
            self.back_button = self.create_icon_button(
                button_id="back_navigation",
                icon="chevron.left@10x",
                on_press=self._on_back_navigation,
                tooltip="Back"
            )
            self.add_to_left(self.back_button)
            
            # Breadcrumb display (center)
            self.breadcrumb_label = toga.Label(
                "",
                style=Pack(
                    flex=1,
                    margin=(5, 10),
                    font_size=14,
                    font_weight="bold"
                )
            )
            self.add_to_center(self.breadcrumb_label)
            
            # Add folder button (right)
            add_folder_btn = self.create_icon_button(
                button_id="add_folder",
                icon="add_folder",
                on_press=self._on_add_folder,
                tooltip="Add Folder"
            )
            self.add_to_right(add_folder_btn)
            
            # Add file button (right)
            add_file_btn = self.create_icon_button(
                button_id="add_file",
                icon="add_file",
                on_press=self._on_add_file,
                tooltip="Add File"
            )
            self.add_to_right(add_file_btn)
            
            # Initialize breadcrumbs
            self.update_breadcrumbs("", "")
            
            logger.info("Collection top toolbar created successfully with single back button")
            
        except Exception as e:
            logger.error(f"Failed to create collection toolbar content: {e}")
            # Fallback to basic toolbar
            super()._create_toolbar()

    def _create_breadcrumb_button(self, text: str, path: str = "", is_current: bool = False):
        """Create a breadcrumb button"""
        if is_current:
            # Current location - just a label
            return toga.Label(
                text,
                style=Pack(
                    margin=(0, 5),
                    font_weight="bold",
                    color="#0066cc"
                )
            )
        else:
            # Clickable breadcrumb
            btn = toga.Button(
                text,
                on_press=lambda widget, p=path: self._on_breadcrumb_click(p),
                style=Pack(
                    margin=(0, 5),
                    background_color="transparent",
                    color="#666666"
                )
            )
            return btn
    
    def update_breadcrumbs(self, collection_name: str, current_path: str):
        """Update the breadcrumb display"""
        try:
            if current_path:
                breadcrumb_text = f"{collection_name} / {current_path.replace('/', ' / ')}"
                if hasattr(self, 'back_button'):
                    self.back_button.enabled = True
            else:
                breadcrumb_text = collection_name
                if hasattr(self, 'back_button'):
                    self.back_button.enabled = False
            
            self.breadcrumb_label.text = breadcrumb_text
            logger.debug(f"Updated breadcrumbs: {breadcrumb_text}")
        except Exception as e:
            logger.error(f"Failed to update breadcrumbs: {e}")
    
    def _on_breadcrumb_click(self, path: str):
        """Handle breadcrumb click"""
        logger.debug(f"Breadcrumb clicked: {path}")
        if self.on_navigate_to_path:
            self.on_navigate_to_path(path)
    
    def _on_back_navigation(self, widget):
        """Smart back navigation - goes to parent folder or library"""
        try:
            # If we have a current path (in subfolder), go up one level
            if hasattr(self, '_current_path') and self._current_path:
                logger.info("Back navigation: going up one folder level")
                if self.on_navigate_back:
                    self.on_navigate_back()
            else:
                # If at root level, go back to library
                logger.info("Back navigation: going back to library")
                if self.on_back_to_library:
                    self.on_back_to_library()
        except Exception as e:
            logger.error(f"Failed to handle back navigation: {e}")
    
    def _on_back_to_library(self, widget):
        """Handle back to library navigation"""
        try:
            logger.info("Back to library requested from toolbar")
            if self.navigation_callbacks and self.navigation_callbacks['on_back_to_library']:
                self.navigation_callbacks['on_back_to_library']()
        except Exception as e:
            logger.error(f"Failed to handle back to library: {e}")
    
    def _on_add_folder(self, widget):
        """Handle add folder action"""
        try:
            logger.info("Add folder requested from toolbar")
            if self.navigation_callbacks and self.navigation_callbacks['on_add_folder']:
                self.navigation_callbacks['on_add_folder']()
        except Exception as e:
            logger.error(f"Failed to handle add folder: {e}")
    
    def _on_add_file(self, widget):
        """Handle add file action"""
        try:
            logger.info("Add file requested from toolbar")
            if self.navigation_callbacks and self.navigation_callbacks['on_add_file']:
                self.navigation_callbacks['on_add_file']()
        except Exception as e:
            logger.error(f"Failed to handle add file: {e}")
    
    def update_navigation_state(self, current_path: str, path_history: List[str]):
        """Update the navigation state from the collection view"""
        self.current_path = current_path
        self.path_history = path_history.copy()
        self._update_breadcrumbs()
    
    def set_collection_context(self, collection_name: str):
        """Set the collection context"""
        self.collection_name = collection_name
        self._update_breadcrumbs()
    
    def set_current_path(self, path: str):
        """Set the current path for smart back navigation"""
        self._current_path = path
        
    def register_navigation_callbacks(self, 
                                    on_back_to_library: Optional[Callable] = None,
                                    on_navigate_back: Optional[Callable] = None,
                                    on_navigate_to_path: Optional[Callable] = None,
                                    on_add_folder: Optional[Callable] = None,
                                    on_add_file: Optional[Callable] = None):
        """Register navigation callbacks"""
        try:
            self.on_back_to_library = on_back_to_library
            self.on_navigate_back = on_navigate_back  
            self.on_navigate_to_path = on_navigate_to_path
            self.on_add_folder = on_add_folder
            self.on_add_file = on_add_file
            
            logger.info("Navigation callbacks registered successfully")
        except Exception as e:
            logger.error(f"Failed to register navigation callbacks: {e}") 