"""
Processing Window Package

Clean modular processing window with separation of concerns:

Desktop/Mobile Windows:
- ProcessingWindow: Desktop standalone window
- ProcessingMobileView: Mobile embedded view

Content Implementation:
- ProcessingContent: Clean modular implementation using managers

Modular Managers:
- ProcessingStateManager: Centralized state management
- ProcessingLayoutManager: UI layout and assembly
- ProcessingController: Business logic and processing workflow

Components:
- FolderSelector: Folder selection UI
- PlanSelector: Plan/workflow selection UI  
- ProgressDisplay: Task progress monitoring
- DescriptionView: Welcome text and descriptions
"""

# Desktop/Mobile windows
from fichero.windows.processing.desktop_window import ProcessingWindow
from fichero.windows.processing.mobile_view import ProcessingMobileView

# Content implementation
from fichero.windows.processing.processing_content import ProcessingContent

# Modular managers
from fichero.windows.processing.state_manager import ProcessingStateManager, ProcessingState
from fichero.windows.processing.layout_manager import ProcessingLayoutManager
from fichero.windows.processing.processing_controller import ProcessingController

__all__ = [
    # Windows/Views
    'ProcessingWindow',
    'ProcessingMobileView',
    
    # Content implementation  
    'ProcessingContent',
    
    # Managers
    'ProcessingStateManager',
    'ProcessingState', 
    'ProcessingLayoutManager',
    'ProcessingController'
] 