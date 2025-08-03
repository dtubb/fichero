"""
User Interface components for Fichero application.

This package contains UI-related modules including menus, windows,
translation/internationalization, and other interface components.
"""

# Import real MenuManager
from fichero.ui.menus import MenuManager

# Placeholder classes for missing components
class AboutWindow:
    pass

# Placeholder functions for config.ui components
def create_plans_window(app):
    return None

def create_prompts_window(app):
    return None

def create_settings_window(app):
    return None

__all__ = [
    "MenuManager",
    "AboutWindow", 
    "create_plans_window", "create_prompts_window", "create_settings_window"
] 