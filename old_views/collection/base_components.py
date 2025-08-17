"""
Base Collection View Components

Shared base classes and utilities for collection view components.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import asyncio
import logging
from typing import Optional, Callable

from fichero.windows.main.views.collection_view_shared import SharedItemRenderer

logger = logging.getLogger(__name__)


class BaseComponent:
    """Base class for all collection view components"""
    
    def __init__(self, presenter):
        """Initialize base component with presenter"""
        self.presenter = presenter
        self.presenter.register_ui_display(self)
        self.container = None
        
    def create_add_button(self):
        """Create standardized Add button"""
        return toga.Button(
            "Add", 
            on_press=lambda w: asyncio.create_task(self.presenter.handle_add_collection())
        )
    
    def format_breadcrumb_text(self, breadcrumb_path):
        """Generate breadcrumb text from path - shows just the parent level"""
        if len(breadcrumb_path) > 1:
            # Show just the parent (previous level)
            return breadcrumb_path[-2].name  # Second to last item is the parent
        elif len(breadcrumb_path) == 1:
            # At collection level, parent is "Collections"
            return "Collections"
        else:
            return "Collections"
    
    def should_show_back_button(self, breadcrumb_path, current_item):
        """Determine if back button should be visible"""
        return len(breadcrumb_path) >= 1 or current_item is not None
    
    def should_load_collections(self, breadcrumb_path, current_item):
        """Determine if we should load collections (at root level)"""
        return len(breadcrumb_path) == 0 and not current_item
    
    def handle_item_selection(self, widget, **kwargs):
        """Unified item selection handler"""
        if widget.selection:
            self.presenter.handle_item_selection(widget.selection)
    
    def create_back_button(self, style_overrides=None):
        """Create standardized back button"""
        base_style = {"margin_right": 10}
        if style_overrides:
            base_style.update(style_overrides)
            
        button = toga.Button(
            "← Back",
            on_press=lambda w: self.presenter.handle_back_navigation(),
            style=Pack(**base_style)
        )
        button.style.visibility = "hidden"  # Initially hidden
        return button
    
    def create_breadcrumb_label(self, initial_text="Collections", style_overrides=None):
        """Create standardized breadcrumb label"""
        base_style = {"font_size": 10, "flex": 1}
        if style_overrides:
            base_style.update(style_overrides)
            
        return toga.Label(initial_text, style=Pack(**base_style))
    
    # Methods to override in subclasses
    def update_navigation(self, current_item, breadcrumb_path):
        """Override in subclasses to handle navigation updates"""
        pass
    
    def update_collections(self, collections):
        """Override in subclasses to handle collections updates"""
        pass


class SharedDisplayMethods:
    """Shared methods for list-based displays"""
    
    def __init__(self, presenter):
        self.presenter = presenter
        
    def format_collections_for_display(self, collections):
        """Format collections for display"""
        return [
            SharedItemRenderer.format_collection_for_display(collection)
            for collection in collections
        ]
    
    def format_items_for_display(self, items):
        """Format navigation items for display"""
        return [
            SharedItemRenderer.format_item_for_display(item)
            for item in items
        ]
    
    def update_list_data(self, list_widget, list_items):
        """Update a list widget with new data"""
        try:
            list_widget.data = list_items
        except Exception as e:
            logger.error(f"Failed to update list data: {e}")


class HeaderComponent:
    """Reusable header component with back button and breadcrumb"""
    
    def __init__(self, presenter, include_add_button=False):
        self.presenter = presenter
        self.container = toga.Box(style=Pack(direction=ROW, margin_bottom=10))
        
        # Back button
        self.back_button = toga.Button(
            "← Back",
            on_press=lambda w: self.presenter.handle_back_navigation(),
            style=Pack(margin_right=10)
        )
        self.back_button.style.visibility = "hidden"
        self.container.add(self.back_button)
        
        # Breadcrumb label
        self.breadcrumb_label = toga.Label(
            "Collections",
            style=Pack(font_size=10, flex=1)
        )
        self.container.add(self.breadcrumb_label)
        
        # Optional add button
        if include_add_button:
            add_btn = toga.Button(
                "Add", 
                on_press=lambda w: asyncio.create_task(self.presenter.handle_add_collection()),
                style=Pack(margin_left=10)
            )
            self.container.add(add_btn)
    
    def update_header(self, current_item, breadcrumb_path):
        """Update header based on navigation state"""
        # Update breadcrumb
        if len(breadcrumb_path) > 1:
            self.breadcrumb_label.text = breadcrumb_path[-2].name
        elif len(breadcrumb_path) == 1:
            self.breadcrumb_label.text = "Collections"
        else:
            self.breadcrumb_label.text = "Collections"
        
        # Show/hide back button
        if len(breadcrumb_path) >= 1 or current_item is not None:
            self.back_button.style.visibility = "visible"
        else:
            self.back_button.style.visibility = "hidden" 