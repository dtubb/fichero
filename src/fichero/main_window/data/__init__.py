"""
Data Models for Main Window

Data models and state management for the main window.
Separated from UI components for better maintainability.
"""

from fichero.main_window.data.collection_data import CollectionData
from fichero.main_window.data.window_state import WindowState

__all__ = [
    'CollectionData',
    'WindowState'
] 