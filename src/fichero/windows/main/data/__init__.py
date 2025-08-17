"""
Data Models for Main Window

Data models and state management for the main window.
Separated from UI components for better maintainability.
"""

from fichero.windows.main.data.collection_data import CollectionData
from fichero.windows.main.data.window_state import WindowState

__all__ = [
    'CollectionData',
    'WindowState'
] 