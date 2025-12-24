"""
Reusable UI Components

Phase 3 components for the OutputView refactoring.
These components follow the inspector pattern and can be embedded anywhere.
"""

from .metadata_viewer import MetadataViewer
from .json_editor import JsonEditor

__all__ = [
    'MetadataViewer',
    'JsonEditor',
]
