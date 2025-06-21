"""
User Interface components for Fichero application.

This package contains UI-related modules including menus, windows,
and other interface components.
"""

from .menus import MenuManager
from .windows import AboutWindow
from ..config.ui import create_plans_window, create_prompts_window, create_settings_window

__all__ = [
    "MenuManager",
    "AboutWindow",
    "create_plans_window", "create_prompts_window", "create_settings_window"
] 