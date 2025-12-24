"""
Stub module for mobile toolbar compatibility.

The native macOS toolbar/menu is now in windows/main/toolbar.py and menu.py.
These stubs exist only for mobile views that haven't been updated yet.
"""

import toga
from toga.style import Pack
from toga.constants import ROW


class ToolbarCoordinator:
    """Stub coordinator - no-op for desktop."""
    def __init__(self, app, is_mobile=False):
        self.app = app
        self.is_mobile = is_mobile
        self.on_edit_mode_change = None
        self.handle_sort = None

    def set_active_view(self, view_id):
        pass

    def set_edit_mode(self, enabled, **kwargs):
        pass


class TopToolbar:
    """Stub top toolbar."""
    def __init__(self, app=None, title="", auto_mobile_nav=False, is_mobile=False, coordinator=None, **kwargs):
        self.app = app
        self.title = title
        self.is_mobile = is_mobile
        self.on_back = None
        self._container = toga.Box(style=Pack(direction=ROW, height=0))

    def get_container(self):
        return self._container

    def set_back_callback(self, callback):
        self.on_back = callback

    def populate_from_commands(self, **kwargs):
        pass


class BottomToolbar:
    """Stub bottom toolbar."""
    def __init__(self, app=None, is_mobile=False, coordinator=None, **kwargs):
        self.app = app
        self.is_mobile = is_mobile
        self._container = toga.Box(style=Pack(direction=ROW, height=0))

    def get_container(self):
        return self._container

    def register_callbacks(self, **kwargs):
        pass

    def populate_from_commands(self, **kwargs):
        pass
