"""
User Interface components for Fichero application.

This package contains UI-related modules including menus, windows,
and other interface components.
"""

from .menus import MenuManager
from .windows import AboutWindow, AppSettingsWindow, PlansEditorWindow, PromptsEditorWindow
from .windows.config_windows import create_plans_editor_window, create_prompts_editor_window, create_app_settings_window
from .document_manager import DocumentManager, DocumentWindow

__all__ = [
    "MenuManager",
    "AppSettingsWindow", "AboutWindow",
    "PlansEditorWindow", "PromptsEditorWindow",
    "create_plans_editor_window", "create_prompts_editor_window", "create_app_settings_window",
    "DocumentManager", "DocumentWindow"
] 