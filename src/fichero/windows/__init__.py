"""
Windows Package

Organized window and view components for the application.
Each window type has its own package with desktop and mobile variants.

Structure:
- main/           : Primary application window with library navigation  
- processing/     : Document processing windows and views
- activity_monitor/: Task monitoring and system health
- plans/          : Project plans library and management
- prompts/        : LLM prompts library and management
- about/          : Application information and help
- settings/       : Configuration and preferences
"""

# Main window components
from fichero.windows.main import MainWindow

# Standalone desktop windows
from fichero.windows.processing import ProcessingWindow
from fichero.windows.activity_monitor import ActivityMonitorWindow  
from fichero.windows.plans import PlansWindow
from fichero.windows.prompts import PromptsWindow
from fichero.windows.about import AboutWindow
from fichero.windows.settings import SettingsWindow

__all__ = [
    # Main windows
    'MainWindow',
    
    # Standalone windows
    'ProcessingWindow',
    'ActivityMonitorWindow', 
    'PlansWindow',
    'PromptsWindow',
    'AboutWindow',
    'SettingsWindow'
] 