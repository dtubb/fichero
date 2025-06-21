"""
Configuration Windows Factory
Convenience functions for creating different types of configuration windows
"""

from pathlib import Path
from typing import Optional

from .windows.settings_library import SettingsLibrary
from .windows.prompts_library import PromptsLibrary
from .windows.plans_library import PlansLibrary


def create_settings_window(app):
    """Create a settings window with file library"""
    return SettingsLibrary(app)


def create_prompts_window(app):
    """Create a prompts window with file library"""
    return PromptsLibrary(app)


def create_plans_window(app):
    """Create a plans window with file library"""
    return PlansLibrary(app)