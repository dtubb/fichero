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
    
    def __init__(self, app, collection_name: str = "", is_mobile: bool = None):
        """Initialize collection top toolbar"""
        super().__init__(app, collection_name, is_mobile)
        
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
            # Call parent to set up basic structure
            super()._create_toolbar()
            
            # Use smart helper - automatically handles mobile vs desktop
            title_text = self.collection_name if self.collection_name else "Collection"
            self.back_button, self.title_label = self.add_back_button_with_title(
                title_text=title_text,
                on_back=self._on_back_navigation,
                on_title_click=self._on_title_pressed
            )
            
            logger.info("Collection top toolbar created using smart base methods")
            
        except Exception as e:
            logger.error(f"Failed to create collection toolbar content: {e}")
    
    def _on_title_pressed(self, widget):
        """Handle title button press (mobile only)"""
        logger.debug("Collection title pressed")
        # Could show collection info, folder navigation, or context menu
        pass

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
    
    def update_breadcrumbs(self, collection_name: str, current_path: str = ""):
        """Update breadcrumb display - disabled since title label was removed"""
        try:
            # Store the current path for back navigation logic
            self._current_path = current_path
            
            # Update back button state based on current path
            if current_path:
                # In a subfolder - enable back button to go up
                if hasattr(self, 'back_button'):
                    self.back_button.enabled = True
            else:
                # At collection root - on mobile, enable back to library; on desktop, disable
                if hasattr(self, 'back_button'):
                    if self.is_mobile:
                        self.back_button.enabled = True  # Mobile: back to library
                        logger.info("🔙 Back button enabled for mobile (back to library)")
                    else:
                        self.back_button.enabled = False  # Desktop: no back at root level
                        logger.info("🔙 Back button disabled for desktop (at root level)")
            
            # Note: breadcrumb display removed as requested - title should be in main toolbar
            logger.debug(f"Updated navigation state - collection: {collection_name}, path: {current_path}")
        except Exception as e:
            logger.error(f"Failed to update navigation state: {e}")
    
    def _on_breadcrumb_click(self, path: str):
        """Handle breadcrumb click"""
        logger.debug(f"Breadcrumb clicked: {path}")
        if self.on_navigate_to_path:
            self.on_navigate_to_path(path)
    
    def _on_back_navigation(self, widget):
        """Smart back navigation - goes to parent folder or library"""
        try:
            logger.info("🔙 Back button pressed in collection view")
            logger.info(f"🔙 Current path: {getattr(self, '_current_path', 'None')}")
            logger.info(f"🔙 on_back_to_library callback: {self.on_back_to_library is not None}")
            logger.info(f"🔙 on_navigate_back callback: {self.on_navigate_back is not None}")
            
            # If we have a current path (in subfolder), go up one level
            if hasattr(self, '_current_path') and self._current_path:
                logger.info("Back navigation: going up one folder level")
                if self.on_navigate_back:
                    self.on_navigate_back()
                else:
                    logger.warning("on_navigate_back callback is None")
            else:
                # If at root level, go back to library
                logger.info("Back navigation: going back to library")
                if self.on_back_to_library:
                    logger.info("🔙 Calling on_back_to_library callback")
                    self.on_back_to_library()
                else:
                    logger.warning("on_back_to_library callback is None")
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