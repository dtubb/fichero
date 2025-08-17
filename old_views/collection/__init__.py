"""
Collection View Components

Modular collection view system organized by UI components rather than platforms.
This allows maximum code sharing while maintaining clear separation of concerns.

Architecture:
- presenter.py: Core business logic and state management
- middle_column.py: Current level list component (shared between desktop and mobile)
- right_column.py: Preview component (desktop only)  
- mobile_view.py: Mobile DetailedList view (uses middle column logic)
"""

from .presenter import CollectionPresenter
from .middle_column import CurrentLevelColumn  
from .right_column import PreviewColumn
from .mobile_view import MobileCollectionView

__all__ = [
    'CollectionPresenter',
    'CurrentLevelColumn', 
    'PreviewColumn',
    'MobileCollectionView'
] 