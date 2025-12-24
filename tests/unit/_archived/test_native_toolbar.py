"""
Unit tests for native macOS toolbar.

Tests verify toolbar structure and data validation.
Note: Full ObjC integration tests require macOS runtime.
"""

import pytest
from unittest.mock import Mock


class TestToolbarDataclasses:
    """Test toolbar dataclass definitions."""

    def test_button_dataclass(self):
        """Verify Button dataclass structure."""
        from fichero.app.main_window.toolbar import Button

        btn = Button("test_id", "star", "Test", "Test tooltip")
        assert btn.id == "test_id"
        assert btn.icon == "star"
        assert btn.label == "Test"
        assert btn.tooltip == "Test tooltip"

    def test_button_default_tooltip(self):
        """Verify Button tooltip defaults to empty string."""
        from fichero.app.main_window.toolbar import Button

        btn = Button("test_id", "star", "Test")
        assert btn.tooltip == ""

    def test_dropdown_dataclass(self):
        """Verify Dropdown dataclass structure."""
        from fichero.app.main_window.toolbar import Dropdown, MenuItem

        items = (MenuItem("Item 1", "doc", "handler1"),)
        dd = Dropdown("menu_id", "folder", "Menu", "Menu tooltip", items)

        assert dd.id == "menu_id"
        assert dd.icon == "folder"
        assert dd.label == "Menu"
        assert dd.tooltip == "Menu tooltip"
        assert len(dd.items) == 1

    def test_search_dataclass(self):
        """Verify Search dataclass structure."""
        from fichero.app.main_window.toolbar import Search

        search = Search()
        assert search.id == "search"
        assert search.label == "Search"

    def test_menu_item_dataclass(self):
        """Verify MenuItem dataclass structure."""
        from fichero.app.main_window.toolbar import MenuItem

        mi = MenuItem("File...", "doc", "import_file")
        assert mi.label == "File..."
        assert mi.icon == "doc"
        assert mi.handler == "import_file"

    def test_dataclasses_are_frozen(self):
        """Verify dataclasses are immutable."""
        from fichero.app.main_window.toolbar import Button

        btn = Button("test_id", "star", "Test")
        with pytest.raises(AttributeError):
            btn.id = "new_id"


class TestToolbarStructure:
    """Test TOOLBAR tuple structure."""

    def test_toolbar_defined(self):
        """Verify TOOLBAR is defined and non-empty."""
        from fichero.app.main_window.toolbar import TOOLBAR

        assert len(TOOLBAR) > 0

    def test_required_buttons_present(self):
        """Verify required toolbar buttons are present."""
        from fichero.app.main_window.toolbar import TOOLBAR, Button

        button_ids = [item.id for item in TOOLBAR if isinstance(item, Button)]

        assert "toggle_library" in button_ids
        assert "process" in button_ids
        assert "settings" in button_ids

    def test_search_present(self):
        """Verify search is in toolbar."""
        from fichero.app.main_window.toolbar import TOOLBAR, Search

        search_items = [item for item in TOOLBAR if isinstance(item, Search)]
        assert len(search_items) == 1

    def test_flex_space_present(self):
        """Verify flexible space is present."""
        from fichero.app.main_window.toolbar import TOOLBAR, FLEX

        assert FLEX in TOOLBAR

    def test_import_dropdown_present(self):
        """Verify import dropdown menu is present."""
        from fichero.app.main_window.toolbar import TOOLBAR, Dropdown

        dropdowns = [item for item in TOOLBAR if isinstance(item, Dropdown)]
        dropdown_ids = [d.id for d in dropdowns]

        assert "import_menu" in dropdown_ids


class TestSFSymbols:
    """Test SF Symbol definitions."""

    def test_sf_symbols_valid_format(self):
        """Verify SF Symbol names are valid format."""
        from fichero.app.main_window.toolbar import TOOLBAR, Button, Dropdown

        # Single-word SF Symbols (no dots)
        single_word_symbols = [
            "plus", "minus", "gearshape", "sparkles", "photo",
            "trash", "folder", "doc", "star", "heart", "magnifyingglass",
            "link"
        ]

        for item in TOOLBAR:
            if isinstance(item, (Button, Dropdown)):
                icon = item.icon
                assert isinstance(icon, str), f"Icon not string: {icon}"
                # Most SF Symbols have dots, but some don't
                assert "." in icon or icon in single_word_symbols, \
                    f"Invalid SF Symbol format: {icon}"


class TestDisplayModeConstants:
    """Test display mode constants."""

    def test_display_modes_defined(self):
        """Verify display mode constants are correct."""
        from fichero.app.main_window.toolbar import (
            DISPLAY_ICON_ONLY, DISPLAY_ICON_AND_LABEL, DISPLAY_LABEL_ONLY
        )

        assert DISPLAY_ICON_ONLY == 2
        assert DISPLAY_ICON_AND_LABEL == 0
        assert DISPLAY_LABEL_ONLY == 1


class TestStandardIdentifiers:
    """Test standard toolbar identifiers."""

    def test_flex_identifier(self):
        """Verify flex space identifier is correct NSToolbar identifier."""
        from fichero.app.main_window.toolbar import FLEX

        assert FLEX == "NSToolbarFlexibleSpaceItem"

    def test_sidebar_separator_identifier(self):
        """Verify sidebar separator identifier is correct."""
        from fichero.app.main_window.toolbar import SIDEBAR_SEPARATOR

        assert SIDEBAR_SEPARATOR == "NSToolbarSidebarTrackingSeparatorItemIdentifier"


class TestImportMenu:
    """Test import menu structure."""

    def test_import_menu_defined(self):
        """Verify import menu is defined."""
        from fichero.app.main_window.toolbar import IMPORT_MENU

        assert len(IMPORT_MENU) > 0

    def test_import_menu_has_file_and_folder(self):
        """Verify import menu has file and folder options."""
        from fichero.app.main_window.toolbar import IMPORT_MENU, MenuItem

        handlers = [item.handler for item in IMPORT_MENU if isinstance(item, MenuItem)]

        assert "import_file" in handlers
        assert "import_folder" in handlers

    def test_import_menu_has_separator(self):
        """Verify import menu has separator (None)."""
        from fichero.app.main_window.toolbar import IMPORT_MENU, SEP

        assert SEP in IMPORT_MENU


class TestAppToolbarClass:
    """Test AppToolbar class structure."""

    def test_init_creates_toolbar(self):
        """Test that AppToolbar creates toolbar on init."""
        pytest.importorskip("rubicon.objc")

        from fichero.app.main_window.toolbar import AppToolbar

        handler = Mock()
        toolbar = AppToolbar(handler=handler)

        assert toolbar._toolbar is not None
        assert toolbar._delegate is not None

    def test_init_with_search_callback(self):
        """Test AppToolbar with search callback."""
        pytest.importorskip("rubicon.objc")

        from fichero.app.main_window.toolbar import AppToolbar, _ToolbarDelegate

        handler = Mock()
        on_search = Mock()
        toolbar = AppToolbar(handler=handler, on_search=on_search)

        assert _ToolbarDelegate.on_search is on_search

    def test_set_enabled_missing_item(self):
        """Test set_enabled handles missing items gracefully."""
        pytest.importorskip("rubicon.objc")

        from fichero.app.main_window.toolbar import AppToolbar

        handler = Mock()
        toolbar = AppToolbar(handler=handler)

        # Should not raise even if item doesn't exist
        toolbar.set_enabled("nonexistent_item", False)

    def test_native_property(self):
        """Test native property returns toolbar."""
        pytest.importorskip("rubicon.objc")

        from fichero.app.main_window.toolbar import AppToolbar

        handler = Mock()
        toolbar = AppToolbar(handler=handler)

        assert toolbar.native is toolbar._toolbar


class TestToolbarIdentifiers:
    """Test toolbar identifiers for standard macOS patterns."""

    def test_toolbar_identifier_format(self):
        """Verify toolbar identifier uses reverse DNS format."""
        pytest.importorskip("rubicon.objc")

        from fichero.app.main_window.toolbar import AppToolbar

        handler = Mock()
        toolbar = AppToolbar(handler=handler)

        # Toolbar identifier should contain fichero
        assert "fichero" in str(toolbar._toolbar.identifier).lower()
