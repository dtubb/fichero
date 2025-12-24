"""
Unit tests for native macOS menu.

Tests verify menu structure and data validation.
Note: Full ObjC integration tests require macOS runtime.
"""

import pytest
from unittest.mock import Mock


class TestMenuDataclasses:
    """Test menu dataclass definitions."""

    def test_item_dataclass(self):
        """Verify Item dataclass structure."""
        from fichero.app.main_window.menu import Item

        item = Item("Test", "handler", "t", 0)
        assert item.label == "Test"
        assert item.handler == "handler"
        assert item.key == "t"
        assert item.mods == 0

    def test_item_defaults(self):
        """Verify Item default values."""
        from fichero.app.main_window.menu import Item

        item = Item("Test")
        assert item.label == "Test"
        assert item.handler == ""
        assert item.key == ""
        assert item.mods == 0

    def test_submenu_dataclass(self):
        """Verify Submenu dataclass structure."""
        from fichero.app.main_window.menu import Submenu, Item

        items = (Item("Child", "handler"),)
        sub = Submenu("Parent", items)
        assert sub.label == "Parent"
        assert len(sub.items) == 1

    def test_menu_dataclass(self):
        """Verify Menu dataclass structure."""
        from fichero.app.main_window.menu import Menu, Item

        items = (Item("Test", "handler"),)
        menu = Menu("Title", items)
        assert menu.title == "Title"
        assert len(menu.items) == 1

    def test_dataclasses_are_frozen(self):
        """Verify dataclasses are immutable."""
        from fichero.app.main_window.menu import Item

        item = Item("Test")
        with pytest.raises(AttributeError):
            item.label = "New"


class TestMenuStructure:
    """Test menu structure definition."""

    def test_menus_defined(self):
        """Verify all expected menus are defined."""
        from fichero.app.main_window.menu import MENUS

        menu_titles = [m.title for m in MENUS]
        assert "Fichero" in menu_titles  # App menu
        assert "File" in menu_titles
        assert "Edit" in menu_titles
        assert "View" in menu_titles
        assert "Tools" in menu_titles
        assert "Window" in menu_titles
        assert "Help" in menu_titles

    def test_menus_ordered(self):
        """Verify menus are in correct display order."""
        from fichero.app.main_window.menu import MENUS

        menu_titles = [m.title for m in MENUS]
        # Standard macOS menu bar order
        assert menu_titles.index("Fichero") < menu_titles.index("File")
        assert menu_titles.index("File") < menu_titles.index("Edit")
        assert menu_titles.index("Edit") < menu_titles.index("View")
        assert menu_titles.index("View") < menu_titles.index("Tools")
        assert menu_titles.index("Window") < menu_titles.index("Help")

    def test_menu_file_items(self):
        """Verify File menu contains expected items."""
        from fichero.app.main_window.menu import MENU_FILE, Item, Submenu

        # Collect handlers from items (including submenu items)
        handlers = []
        for entry in MENU_FILE.items:
            if isinstance(entry, Item):
                handlers.append(entry.handler)
            elif isinstance(entry, Submenu):
                for sub_item in entry.items:
                    if isinstance(sub_item, Item):
                        handlers.append(sub_item.handler)

        assert "new_collection" in handlers
        assert "import_file" in handlers
        assert "import_folder" in handlers
        assert "close_window" in handlers

    def test_menu_edit_items(self):
        """Verify Edit menu contains standard edit items."""
        from fichero.app.main_window.menu import MENU_EDIT, Item

        handlers = [e.handler for e in MENU_EDIT.items if isinstance(e, Item)]

        assert "undo" in handlers
        assert "redo" in handlers
        assert "cut" in handlers
        assert "copy" in handlers
        assert "paste" in handlers
        assert "select_all" in handlers

    def test_menu_view_items(self):
        """Verify View menu contains pane toggle items."""
        from fichero.app.main_window.menu import MENU_VIEW, Item

        handlers = [e.handler for e in MENU_VIEW.items if isinstance(e, Item)]

        assert "toggle_library" in handlers
        assert "toggle_collection" in handlers
        assert "toggle_preview_image" in handlers
        assert "toggle_inspector" in handlers

    def test_menu_tools_items(self):
        """Verify Tools menu contains processing items."""
        from fichero.app.main_window.menu import MENU_TOOLS, Item, Submenu

        # Collect handlers from items and submenus
        handlers = []
        for entry in MENU_TOOLS.items:
            if isinstance(entry, Item):
                handlers.append(entry.handler)
            elif isinstance(entry, Submenu):
                for sub_item in entry.items:
                    if isinstance(sub_item, Item):
                        handlers.append(sub_item.handler)

        assert "process" in handlers
        assert "process_transcribe" in handlers

    def test_file_menu_has_import_submenu(self):
        """Verify File menu has Import submenu."""
        from fichero.app.main_window.menu import MENU_FILE, Submenu

        submenus = [e for e in MENU_FILE.items if isinstance(e, Submenu)]
        submenu_labels = [s.label for s in submenus]

        assert "Import" in submenu_labels


class TestKeyboardShortcuts:
    """Test keyboard shortcut validation."""

    def test_shortcuts_valid_format(self):
        """Verify keyboard shortcut keys are valid."""
        from fichero.app.main_window.menu import (
            MENU_FILE, MENU_EDIT, MENU_VIEW, MENU_TOOLS, MENU_WINDOW
        )
        from fichero.app.main_window.menu import Item

        all_menus = [MENU_FILE, MENU_EDIT, MENU_VIEW, MENU_TOOLS, MENU_WINDOW]

        for menu in all_menus:
            for entry in menu.items:
                if isinstance(entry, Item) and entry.key:
                    # Key should be single char or special char
                    assert len(entry.key) == 1 or entry.key in ['\r', '\x7f'], \
                        f"Invalid key '{repr(entry.key)}' for {entry.label}"

    def test_modifier_constants_valid(self):
        """Verify modifier constants are correct bit values."""
        from fichero.app.main_window.menu import SHIFT, CTRL, OPT, CMD

        # Standard NSEventModifierFlags values
        assert SHIFT == 1 << 17
        assert CTRL == 1 << 18
        assert OPT == 1 << 19
        assert CMD == 1 << 20


class TestSeparators:
    """Test menu separator handling."""

    def test_sep_constant(self):
        """Verify SEP is None."""
        from fichero.app.main_window.menu import SEP

        assert SEP is None

    def test_menus_have_separators(self):
        """Verify menus contain separators (None entries)."""
        from fichero.app.main_window.menu import MENU_FILE, MENU_EDIT, MENU_VIEW

        assert None in MENU_FILE.items
        assert None in MENU_EDIT.items
        assert None in MENU_VIEW.items


class TestAppMenuClass:
    """Test AppMenu class structure."""

    def test_init_creates_delegate(self):
        """Test that AppMenu creates delegate on init."""
        pytest.importorskip("rubicon.objc")

        from fichero.app.main_window.menu import AppMenu

        handler = Mock()
        menu = AppMenu(handler=handler)

        assert menu.handler is handler
        assert menu._items == {}
        assert menu._delegate is not None

    def test_set_enabled_missing_item(self):
        """Test set_enabled handles missing items gracefully."""
        pytest.importorskip("rubicon.objc")

        from fichero.app.main_window.menu import AppMenu

        handler = Mock()
        menu = AppMenu(handler=handler)

        # Should not raise even if item doesn't exist
        menu.set_enabled("nonexistent_item", False)


class TestServicesMenu:
    """Test Services menu special handling."""

    def test_app_menu_has_services(self):
        """Verify App menu has Services submenu."""
        from fichero.app.main_window.menu import MENU_APP, Submenu

        submenus = [e for e in MENU_APP.items if isinstance(e, Submenu)]
        submenu_labels = [s.label for s in submenus]

        assert "Services" in submenu_labels

    def test_services_submenu_empty(self):
        """Verify Services submenu is empty (macOS fills it)."""
        from fichero.app.main_window.menu import MENU_APP, Submenu

        for entry in MENU_APP.items:
            if isinstance(entry, Submenu) and entry.label == "Services":
                assert len(entry.items) == 0


class TestMenuItemFormat:
    """Test menu item structure validation."""

    def test_all_items_are_valid_types(self):
        """Verify all menu entries are valid types."""
        from fichero.app.main_window.menu import MENUS, Item, Submenu

        for menu in MENUS:
            for entry in menu.items:
                assert entry is None or isinstance(entry, (Item, Submenu)), \
                    f"Invalid entry type in {menu.title}: {type(entry)}"

    def test_submenu_items_are_valid(self):
        """Verify all submenu items are valid types."""
        from fichero.app.main_window.menu import MENUS, Item, Submenu

        for menu in MENUS:
            for entry in menu.items:
                if isinstance(entry, Submenu):
                    for sub_item in entry.items:
                        assert sub_item is None or isinstance(sub_item, Item), \
                            f"Invalid submenu item in {entry.label}: {type(sub_item)}"
