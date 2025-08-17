"""
Processing Window Components

Modular components for the processing window:
- FolderSelector: Folder selection and display
- PlanSelector: Plan and workflow selection  
- ProgressDisplay: Task progress monitoring
- DescriptionView: Welcome text and plan descriptions
"""

from fichero.windows.processing.components.folder_selector import FolderSelector
from fichero.windows.processing.components.plan_selector import PlanSelector
from fichero.windows.processing.components.progress_display import ProgressDisplay
from fichero.windows.processing.components.description_view import DescriptionView

__all__ = [
    'FolderSelector',
    'PlanSelector', 
    'ProgressDisplay',
    'DescriptionView'
] 