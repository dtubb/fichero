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
            
            # Use collection-specific helper - shows back button on both mobile and desktop
            title_text = self.collection_name if self.collection_name else "Collection"
            self.back_button, self.title_label = self.add_collection_back_button_with_title(
                title_text=title_text,
                on_back=self._on_back_navigation,
                on_title_click=self._on_title_navigation
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
        """Update breadcrumb display and title to show parent directory navigation"""
        try:
            # Store the current path for back navigation logic
            self._current_path = current_path
            
            # Update back button state based on current path (back button now exists on both mobile and desktop)
            if hasattr(self, 'back_button') and self.back_button is not None:
                logger.info(f"🔙 DEBUG: Back button exists, current_path='{current_path}', is_mobile={self.is_mobile}")
                if current_path:
                    # In a subfolder - show/enable back button to go up hierarchy
                    self.back_button.enabled = True
                    if not self.is_mobile:
                        self.back_button.style.visibility = "visible"  # Show on desktop when in folder
                        logger.info(f"🔙 DEBUG: Desktop back button set to VISIBLE (hierarchy), enabled={self.back_button.enabled}")
                    logger.debug(f"🔙 Back button enabled (in subfolder: {current_path})")
                else:
                    # At collection root - different behavior for mobile vs desktop
                    if self.is_mobile:
                        self.back_button.enabled = True  # Mobile: back to library
                        logger.info("🔙 Back button enabled for mobile (back to library)")
                    else:
                        self.back_button.style.visibility = "hidden"  # Desktop: hide back button at root
                        logger.info(f"🔙 DEBUG: Desktop back button set to HIDDEN (root), enabled={self.back_button.enabled}")
                        logger.info("🔙 Back button hidden for desktop (at collection root - no library navigation)")
                        
                        # Update title to show collection name when at root on desktop
                        if hasattr(self, 'title_label') and self.title_label is not None:
                            self.title_label.text = collection_name or "Collection"
                            self._desktop_title_set = True
            else:
                # Should not happen with new collection method
                logger.warning("🔙 No back button found - this should not happen with collection toolbar")
            
            # Update title to show parent directory (what you can navigate back to)
            if hasattr(self, 'title_label') and self.title_label is not None:
                if current_path:
                    # In a subfolder - title shows parent directory
                    path_parts = current_path.split('/')
                    if len(path_parts) > 1:
                        # In nested folder - show immediate parent folder
                        parent_folder = path_parts[-2]
                        self.title_label.text = parent_folder
                    else:
                        # In top-level folder - show collection name  
                        self.title_label.text = collection_name
                    
                    # For desktop: update title alignment to left when in hierarchy
                    if not self.is_mobile and hasattr(self.title_label, 'style'):
                        self._update_desktop_title_alignment(in_hierarchy=True)
                else:
                    # At collection root - different behavior for mobile vs desktop
                    if self.is_mobile:
                        # Mobile: back button goes to library, so title shows "Library"
                        self.title_label.text = "Library"
                    else:
                        # Desktop: title shows collection name and should be centered at root
                        if not hasattr(self, '_desktop_title_set'):
                            self.title_label.text = collection_name or "Collection"
                        self._update_desktop_title_alignment(in_hierarchy=False)
                logger.debug(f"🏷️ Updated title to: {self.title_label.text}")
            
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
            
            # If we have a current path (in subfolder), always go up one level
            if hasattr(self, '_current_path') and self._current_path:
                logger.info("Back navigation: going up one folder level")
                if self.on_navigate_back:
                    self.on_navigate_back()
                else:
                    logger.warning("on_navigate_back callback is None")
            else:
                # At root level - different behavior for mobile vs desktop
                if self.is_mobile:
                    # Mobile: go back to library
                    logger.info("Back navigation (mobile): going back to library")
                    if self.on_back_to_library:
                        logger.info("🔙 Calling on_back_to_library callback")
                        self.on_back_to_library()
                    else:
                        logger.warning("on_back_to_library callback is None")
                else:
                    # Desktop: do nothing (button should be disabled at root)
                    logger.info("Back navigation (desktop): at root level, button should be disabled")
        except Exception as e:
            logger.error(f"Failed to handle back navigation: {e}")
    
    def _on_title_navigation(self, widget):
        """Handle title click navigation - navigate to the parent shown in title"""
        try:
            logger.info("🏷️ Title clicked for navigation")
            logger.info(f"🏷️ Current path: {getattr(self, '_current_path', 'None')}")
            
            # Title shows parent directory, so clicking it should navigate there
            # This is the same as back navigation
            self._on_back_navigation(widget)
            
        except Exception as e:
            logger.error(f"Failed to handle title navigation: {e}")
    
    def _on_back_to_library(self, widget):
        """Handle back to library navigation"""
        try:
            logger.info("Back to library requested from toolbar")
            if self.navigation_callbacks and self.navigation_callbacks['on_back_to_library']:
                self.navigation_callbacks['on_back_to_library']()
        except Exception as e:
            logger.error(f"Failed to handle back to library: {e}")
    
    def _update_desktop_title_alignment(self, in_hierarchy: bool):
        """Update desktop title alignment based on navigation context"""
        if self.is_mobile or not hasattr(self, 'title_label'):
            return
        
        try:
            if in_hierarchy:
                # In hierarchy - left-align title next to back button
                self.title_label.style.text_align = "left"
                # Note: Position is controlled by parent container, this affects text within label
                logger.debug("🏷️ Desktop title set to left-aligned (hierarchy)")
            else:
                # At collection root - center-align title
                self.title_label.style.text_align = "center"
                logger.debug("🏷️ Desktop title set to center-aligned (root)")
        except Exception as e:
            logger.error(f"Failed to update desktop title alignment: {e}")

    
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