"""
Document List Component for Main Window

Handles the DetailedList widget for displaying documents.
"""

import toga
from toga.style import Pack
from typing import List, Dict, Any, Optional


class DocumentListComponent:
    """Document list component using Toga DetailedList"""
    
    def __init__(self, on_select=None, on_primary_action=None, on_secondary_action=None):
        """Initialize document list component with callback handlers"""
        self.on_select = on_select
        self.on_primary_action = on_primary_action
        self.on_secondary_action = on_secondary_action
        self.document_list = None
        self.container = None
        self.documents_data = []
        self.filtered_data = []
    
    def create(self):
        """Create the document list UI"""
        list_container = toga.Box(
            style=Pack(
                direction=toga.constants.COLUMN,
                flex=1
            )
        )
        
        # Create detailed list
        self.document_list = toga.DetailedList(
            data=[],
            accessors=('title', 'subtitle', 'icon'),
            on_select=self._on_document_select,
            on_primary_action=self._on_document_open,
            on_secondary_action=self._on_document_show_info,
            primary_action="Open",
            secondary_action="Info",
            style=Pack(flex=1)
        )
        
        list_container.add(self.document_list)
        
        self.container = list_container
        return list_container
    
    def _on_document_select(self, widget, row):
        """Handle document selection"""
        if self.on_select and row and row.data:
            self.on_select(widget, row)
    
    def _on_document_open(self, widget, row):
        """Handle document open action"""
        if self.on_primary_action and row and row.data:
            self.on_primary_action(widget, row)
    
    def _on_document_show_info(self, widget, row):
        """Handle document info action"""
        if self.on_secondary_action and row and row.data:
            self.on_secondary_action(widget, row)
    
    def set_data(self, documents: List[Dict[str, Any]]):
        """Set the document data"""
        self.documents_data = documents
        self.filtered_data = documents.copy()
        if self.document_list:
            self.document_list.data = self.filtered_data
    
    def apply_filters(self, search_text: str = "", filter_value: str = "All Documents"):
        """Apply search and filter to document list"""
        filtered = []
        
        for doc in self.documents_data:
            # Apply search filter
            if search_text and search_text.lower() not in doc['title'].lower():
                continue
            
            # Apply status filter
            if filter_value != "All Documents":
                doc_status = doc['data']['status']
                if filter_value == "Processed" and doc_status != "Processed":
                    continue
                elif filter_value == "In Progress" and doc_status != "In Progress":
                    continue
                elif filter_value == "Failed" and doc_status != "Failed":
                    continue
            
            filtered.append(doc)
        
        # Update list
        self.filtered_data = filtered
        if self.document_list:
            self.document_list.data = filtered
        
        return len(filtered)
    
    @property
    def selected_document(self):
        """Get the currently selected document"""
        if self.document_list and self.document_list.selection:
            return self.document_list.selection.data
        return None 