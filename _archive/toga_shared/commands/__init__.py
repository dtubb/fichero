"""
Stub module for command system compatibility.

The native macOS menu/toolbar is now in windows/main/menu.py and toolbar.py.
These stubs exist only for code that hasn't been updated yet.
"""
from dataclasses import dataclass, field
from typing import Optional, Callable, Any


@dataclass
class FicheroCommand:
    """Stub command - for compatibility only."""
    id: str = ""
    label: str = ""
    action: Optional[Callable] = None
    shortcut: Any = None
    icon: str = ""
    description: str = ""
    group: Any = None
    section: int = 0
    order: int = 0
    show_in_menu: bool = False
    show_in_toolbar: bool = False
    show_in_top_toolbar: bool = False
    show_in_bottom_toolbar: bool = False
    toolbar_position: str = ""
    mobile_only: bool = False
    desktop_only: bool = False
    context: str = "normal"
    enabled: bool = True
    item_type: str = ""
    search_placeholder: str = ""
    search_action: Optional[Callable] = None
    toolbar_icon: str = ""
    visibility_priority: int = 0


class ViewCommandMixin:
    """Stub mixin - no-op."""
    def __init__(self):
        self.commands = {}

    def define_commands(self):
        pass

    def register_commands(self):
        pass


class CommandManager:
    """Stub command manager."""
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def get_instance(cls, app=None):
        return cls.instance()

    def register_command(self, command):
        pass

    def get_commands_for_view(self, view_id):
        return []

    def get_commands_for_toolbar(self, view_id, toolbar_type):
        return []


class CommandRegistry:
    """Stub command registry."""
    @classmethod
    def get_commands_for_group(cls, group):
        return []

    @classmethod
    def register(cls, command):
        pass
