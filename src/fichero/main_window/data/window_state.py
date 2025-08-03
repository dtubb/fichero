"""
Window State Management

Manages the state of the main window including collections and filters.
"""

from typing import List, Optional
from fichero.main_window.data.collection_data import CollectionData


class WindowState:
    """Window state management"""
    
    def __init__(self):
        """Initialize window state"""
        self.collections: List[CollectionData] = []
        self.filtered_collections: List[CollectionData] = []
        self.search_text: str = ""
        self.filter_value: str = "All Collections"
        self.selected_collection: Optional[CollectionData] = None
    
    def set_collections(self, collections: List[CollectionData]):
        """Set the collection list"""
        self.collections = collections
        self.apply_filters()
    
    def set_search_text(self, search_text: str):
        """Set search text and apply filters"""
        self.search_text = search_text
        self.apply_filters()
    
    def set_filter_value(self, filter_value: str):
        """Set filter value and apply filters"""
        self.filter_value = filter_value
        self.apply_filters()
    
    def apply_filters(self):
        """Apply current search and filter to collections"""
        filtered = []
        
        for collection in self.collections:
            # Apply search filter
            if self.search_text and self.search_text.lower() not in collection.title.lower():
                continue
            
            # Apply status filter
            if self.filter_value != "All Collections":
                if self.filter_value == "Processed" and collection.status != "Processed":
                    continue
                elif self.filter_value == "In Progress" and collection.status != "In Progress":
                    continue
                elif self.filter_value == "Failed" and collection.status != "Failed":
                    continue
            
            filtered.append(collection)
        
        self.filtered_collections = filtered
    
    def get_list_data(self) -> List[dict]:
        """Get data in DetailedList format"""
        return [collection.to_list_data() for collection in self.filtered_collections]
    
    @property
    def collection_count(self) -> int:
        """Get total collection count"""
        return len(self.collections)
    
    @property
    def filtered_count(self) -> int:
        """Get filtered collection count"""
        return len(self.filtered_collections) 