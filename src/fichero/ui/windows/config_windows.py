"""
Configuration Windows Factory
Convenience functions for creating different types of configuration windows
"""

from pathlib import Path
from typing import Optional

from .app_settings_window import AppSettingsWindow
from .prompts_editor_window import PromptsEditorWindow
from .plans_editor_window import PlansEditorWindow


def create_app_settings_window(app):
    """Create an application settings window"""
    return AppSettingsWindow(app)


def create_prompts_editor_window(app, config_file: Path):
    """Create a prompts editor window for JSONL files"""
    return PromptsEditorWindow(app, config_file)


def create_plans_editor_window(app, plans_file: Optional[Path] = None):
    """Create a plans.yml editor window"""
    return PlansEditorWindow(app, plans_file)