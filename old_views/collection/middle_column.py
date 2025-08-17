"""
Middle Column - Current Level List Component

Shared list component that shows the current navigation level.
Used as center column on desktop and main view on mobile.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import asyncio
import logging
from typing import Optional

from .base_components import BaseComponent, HeaderComponent, SharedDisplayMethods
from fichero.windows.main.views.collection_view_shared import SharedItemRenderer

logger = logging.getLogger(__name__)


class CurrentLevelColumn(BaseComponent):
    """Current level list component - shared between desktop and mobile"""
    
    def __init__(self, presenter, include_header=True, width=None):
        super().__init__(presenter)
        self.include_header = include_header
        self.width = width
        self.display_methods = SharedDisplayMethods(presenter)
        
        # UI components
        self.header = None
        self.current_level_list = None
        
        self._create_ui()
    
    def _create_ui(self):
        """Create current level list UI"""
        # Main container
        style = Pack(direction=COLUMN, flex=1, margin=10)
        if self.width:
            style.width = self.width
        self.container = toga.Box(style=style)
        
        # Optional header (for desktop center column)
        if self.include_header:
            self.header = HeaderComponent(self.presenter)
            self.container.add(self.header.container)
        
        # Current level list
        self.current_level_list = toga.DetailedList(
            data=[],
            on_select=self._on_item_select,
            style=Pack(flex=1)
        )
        self.container.add(self.current_level_list)
    
    def _on_item_select(self, widget, **kwargs):
        """Handle item selection"""
        self.handle_item_selection(widget, **kwargs)
    
    # BaseComponent interface implementations
    def update_collections(self, collections):
        """Update display when collections are loaded"""
        try:
            list_items = self.display_methods.format_collections_for_display(collections)
            self.display_methods.update_list_data(self.current_level_list, list_items)
        except Exception as e:
            logger.error(f"Failed to update collections: {e}")
    
    def update_navigation(self, current_item, breadcrumb_path):
        """Update display when navigation changes"""
        try:
            # Update header if present
            if self.header:
                self.header.update_header(current_item, breadcrumb_path)
            
            # Update current level list
            if self.should_load_collections(breadcrumb_path, current_item):
                # We're at collections list - need to load collections
                self.current_level_list.data = []
                asyncio.create_task(self.presenter.nav_logic.load_collections())
            else:
                # We're in a hierarchy - show current items
                self._update_navigation_items()
            
        except Exception as e:
            logger.error(f"Failed to update current level navigation: {e}")
    
    def _update_navigation_items(self):
        """Update navigation items from current state"""
        try:
            items = self.presenter.get_current_items()
            list_items = self.display_methods.format_items_for_display(items)
            self.display_methods.update_list_data(self.current_level_list, list_items)
        except Exception as e:
            logger.error(f"Failed to update navigation items: {e}")


class MobileCurrentLevelView(CurrentLevelColumn):
    """Mobile-specific current level view with mobile-optimized header"""
    
    def __init__(self, presenter):
        super().__init__(presenter, include_header=False)  # Custom mobile header
        
        # Custom mobile header
        self._create_mobile_header()
    
    def _create_mobile_header(self):
        """Create mobile-optimized header"""
        # Insert header at the beginning
        header_container = toga.Box(style=Pack(direction=ROW, margin=10))
        
        # Back button (initially hidden)
        self.back_button = self.create_back_button()
        # Override the back button handler to use mobile navigation if available
        self.back_button.on_press = self._handle_mobile_back
        header_container.add(self.back_button)
        
        # Breadcrumb title (dynamic)
        self.title_label = self.create_breadcrumb_label()
        header_container.add(self.title_label)
        
        # Add collection button
        add_btn = self.create_add_button()
        add_btn.style.margin_left = 10
        header_container.add(add_btn)
        
        # Insert at the beginning of container
        self.container.insert(0, header_container)
    
    def _handle_mobile_back(self, widget):
        """Handle back navigation for mobile with stack support"""
        # Check if our parent has mobile navigation
        for ui_display in self.presenter.ui_displays:
            if hasattr(ui_display, 'handle_back_navigation') and hasattr(ui_display, 'view_stack'):
                # Use mobile collection view's back navigation
                ui_display.handle_back_navigation()
                return
        
        # Fall back to standard navigation
        self.presenter.handle_back_navigation()
    
    def update_navigation(self, current_item, breadcrumb_path):
        """Update mobile navigation display"""
        try:
            # Update breadcrumb title
            self.title_label.text = self.format_breadcrumb_text(breadcrumb_path)
            
            # Show/hide back button
            if self.should_show_back_button(breadcrumb_path, current_item):
                self.back_button.style.visibility = "visible"
            else:
                self.back_button.style.visibility = "hidden"
            
            # Update current level list
            if self.should_load_collections(breadcrumb_path, current_item):
                # We're at collections list - need to load collections
                self.current_level_list.data = []
                asyncio.create_task(self.presenter.nav_logic.load_collections())
            else:
                # We're in a hierarchy - show current items
                self._update_navigation_items()
            
        except Exception as e:
            logger.error(f"Failed to update mobile navigation: {e}") 