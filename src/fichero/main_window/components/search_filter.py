"""
Search and Filter Component for Main Window

Handles search input and status filtering for collections.
"""

import toga
from toga.style import Pack
from toga.constants import ROW

import gettext


class SearchFilterComponent:
    """Search and filter component"""
    
    def __init__(self, on_search_change=None, on_filter_change=None):
        """Initialize search/filter component with callback handlers"""
        self.on_search_change = on_search_change
        self.on_filter_change = on_filter_change
        self.search_input = None
        self.filter_dropdown = None
        self.container = None
    
    def create(self):
        """Create the search/filter UI"""
        search_container = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(0, 0, 10, 0)
            )
        )
        
        # Search input
        self.search_input = toga.TextInput(
            placeholder=_("main_window_search_placeholder"),
            on_change=self._on_search_change,
            style=Pack(flex=1, margin=(0, 10, 0, 0))
        )
        
        # Filter dropdown
        self.filter_dropdown = toga.Selection(
            items=[
                            _("main_window_filter_all"),
            _("main_window_filter_processed"),
            _("main_window_filter_in_progress"),
            _("main_window_filter_failed")
            ],
            on_change=self._on_filter_change,
            style=Pack(width=150)
        )
        
        search_container.add(self.search_input)
        search_container.add(self.filter_dropdown)
        
        self.container = search_container
        return search_container
    
    def _on_search_change(self, widget):
        """Handle search input changes"""
        if self.on_search_change:
            self.on_search_change(widget)
    
    def _on_filter_change(self, widget):
        """Handle filter dropdown changes"""
        if self.on_filter_change:
            self.on_filter_change(widget)
    
    @property
    def search_text(self):
        """Get current search text"""
        return self.search_input.value if self.search_input else ""
    
    @property
    def filter_value(self):
        """Get current filter value"""
        return self.filter_dropdown.value if self.filter_dropdown else _("main_window_filter_all") 