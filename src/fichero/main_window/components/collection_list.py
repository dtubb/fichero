"""
Collection List Component for Main Window

Handles the DetailedList widget for displaying collections.
"""

import toga
from toga.style import Pack
from typing import List, Dict, Any, Optional

import gettext


class CollectionListComponent:
    """Collection list component using Toga DetailedList"""
    
    def __init__(self, on_select=None, on_primary_action=None, on_secondary_action=None):
        """Initialize collection list component with callback handlers"""
        self.on_select = on_select
        self.on_primary_action = on_primary_action
        self.on_secondary_action = on_secondary_action
        self.collection_list = None
        self.container = None
        self.collections_data = []
        self.filtered_data = []
    
    def create(self):
        """Create the collection list UI"""
        # Create detailed list directly without container margins
        self.collection_list = toga.DetailedList(
            data=[],
            accessors=('title', 'subtitle', 'icon'),
            on_select=self._on_collection_select,
            on_primary_action=self._on_collection_open,
            on_secondary_action=self._on_collection_show_info,
            primary_action=_("main_window_action_open"),
            secondary_action=_("main_window_action_info"),
            style=Pack(flex=1)
        )
        
        return self.collection_list
    
    def _on_collection_select(self, widget):
        """Handle collection selection"""
        if self.on_select and self.collection_list.selection:
            self.on_select(widget, self.collection_list.selection)
    
    def _on_collection_open(self, widget):
        """Handle collection open action"""
        if self.on_primary_action and self.collection_list.selection:
            self.on_primary_action(widget, self.collection_list.selection)
    
    def _on_collection_show_info(self, widget):
        """Handle collection info action"""
        if self.on_secondary_action and self.collection_list.selection:
            self.on_secondary_action(widget, self.collection_list.selection)
    
    def set_data(self, collections: List[Dict[str, Any]]):
        """Set the collection data"""
        self.collections_data = collections
        self.filtered_data = collections.copy()
        if self.collection_list:
            self.collection_list.data = self.filtered_data
    
    def apply_filters(self, search_text: str = "", filter_value: str = None):
        """Apply search and filter to collection list"""
        if filter_value is None:
            filter_value = _("main_window_filter_all")
            
        filtered = []
        
        for collection in self.collections_data:
            # Apply search filter
            if search_text and search_text.lower() not in collection['title'].lower():
                continue
            
            # Apply status filter
            if filter_value != _("main_window_filter_all"):
                collection_status = collection['data']['status']
                if filter_value == _("main_window_filter_processed") and collection_status != "Processed":
                    continue
                elif filter_value == _("main_window_filter_in_progress") and collection_status != "In Progress":
                    continue
                elif filter_value == _("main_window_filter_failed") and collection_status != "Failed":
                    continue
            
            filtered.append(collection)
        
        # Update list
        self.filtered_data = filtered
        if self.collection_list:
            self.collection_list.data = filtered
        
        return len(filtered)
    
    @property
    def selected_collection(self):
        """Get the currently selected collection"""
        if self.collection_list and self.collection_list.selection:
            return self.collection_list.selection.data
        return None 