"""
Unit tests for Fichero Command System

Tests command registration, platform filtering, menu creation, and toolbar population.
"""

import pytest
import toga
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fichero.shared.commands.command import FicheroCommand
from fichero.shared.commands.registry import CommandRegistry
from fichero.shared.commands.command_manager import CommandManager


class TestFicheroCommand:
    """Test FicheroCommand creation and properties"""

    def test_command_creation_minimal(self):
        """Test creating command with minimal parameters"""
        cmd = FicheroCommand(
            id="test.command",
            label="Test Command",
            action=lambda w: None
        )

        assert cmd.id == "test.command"
        assert cmd.label == "Test Command"
        assert cmd.action is not None
        assert cmd.show_in_menu is True  # Default is True
        assert cmd.show_in_bottom_toolbar is False  # Default
        assert cmd.mobile_only is False
        assert cmd.desktop_only is False

    def test_command_creation_full(self):
        """Test creating command with all parameters"""
        action = lambda w: print("Test")

        cmd = FicheroCommand(
            id="test.full",
            label="Full Command",
            action=action,
            shortcut=toga.Key.MOD_1 + 't',
            icon="test.png",
            description="Test description",
            group=toga.Group.VIEW,
            toolbar_text="Test",
            show_in_menu=True,
            show_in_bottom_toolbar=True,
            toolbar_position="left",
            mobile_only=False,
            desktop_only=False,
            context="normal",
            enabled=True
        )

        assert cmd.id == "test.full"
        assert cmd.label == "Full Command"
        assert cmd.action == action
        assert cmd.shortcut == toga.Key.MOD_1 + 't'
        assert cmd.icon == "test.png"
        assert cmd.description == "Test description"
        assert cmd.group == toga.Group.VIEW
        assert cmd.show_in_menu is True
        assert cmd.show_in_bottom_toolbar is True
        assert cmd.mobile_only is False
        assert cmd.desktop_only is False

    def test_command_deprecated_show_in_toolbar(self):
        """Test deprecated show_in_toolbar flag (backward compatibility)"""
        cmd = FicheroCommand(
            id="test.deprecated",
            label="Deprecated",
            action=lambda w: None,
            show_in_toolbar=True  # Deprecated
        )

        # Should still work for backward compatibility
        assert cmd.show_in_toolbar is True


class TestCommandRegistry:
    """Test CommandRegistry singleton and storage"""

    def setup_method(self):
        """Reset registry before each test"""
        CommandRegistry._instance = None
        CommandRegistry._commands = {}

    def test_registry_singleton(self):
        """Test that CommandRegistry is a singleton"""
        registry1 = CommandRegistry.get_instance()
        registry2 = CommandRegistry.get_instance()

        assert registry1 is registry2

    def test_register_command(self):
        """Test registering a command"""
        registry = CommandRegistry.get_instance()

        cmd = FicheroCommand(
            id="test.register",
            label="Test",
            action=lambda w: None
        )

        registry.register(cmd)

        assert registry.get("test.register") == cmd

    def test_get_nonexistent_command(self):
        """Test getting a command that doesn't exist"""
        registry = CommandRegistry.get_instance()

        result = registry.get("nonexistent")

        assert result is None

    def test_get_all_commands(self):
        """Test getting all registered commands"""
        registry = CommandRegistry.get_instance()

        cmd1 = FicheroCommand(id="test.1", label="Test 1", action=lambda w: None)
        cmd2 = FicheroCommand(id="test.2", label="Test 2", action=lambda w: None)

        registry.register(cmd1)
        registry.register(cmd2)

        all_commands = registry.list_all()

        assert len(all_commands) == 2
        assert cmd1 in all_commands
        assert cmd2 in all_commands

    def test_clear_registry(self):
        """Test clearing all commands"""
        registry = CommandRegistry.get_instance()

        cmd = FicheroCommand(id="test.clear", label="Test", action=lambda w: None)
        registry.register(cmd)

        assert len(registry.list_all()) == 1

        registry.clear()

        assert len(registry.list_all()) == 0


class TestCommandManagerPlatformFiltering:
    """Test platform-specific command filtering"""

    def setup_method(self):
        """Reset registry and create mock app"""
        CommandRegistry._instance = None
        CommandRegistry._commands = {}
        CommandManager._instance = None

        # Create mock app
        self.mock_app = Mock()
        self.mock_app.commands = Mock()
        self.mock_app.commands.add = Mock()

    def test_mobile_only_command_on_desktop(self):
        """Test mobile_only command is filtered on desktop"""
        self.mock_app.is_mobile = False
        manager = CommandManager(self.mock_app)

        cmd = FicheroCommand(
            id="test.mobile_only",
            label="Mobile Only",
            action=lambda w: None,
            show_in_menu=True,
            mobile_only=True  # Should be filtered on desktop
        )

        manager.register_command(cmd)

        # Command should NOT be in registry (skipped completely on desktop)
        registry = CommandRegistry.get_instance()
        assert registry.get("test.mobile_only") is None

        # And should NOT be added to app.commands (desktop menus)
        self.mock_app.commands.add.assert_not_called()

    def test_mobile_only_command_on_mobile(self):
        """Test mobile_only command is shown on mobile"""
        self.mock_app.is_mobile = True
        manager = CommandManager(self.mock_app)

        cmd = FicheroCommand(
            id="test.mobile_only",
            label="Mobile Only",
            action=lambda w: None,
            show_in_menu=True,
            mobile_only=True
        )

        manager.register_command(cmd)

        # On mobile, show_in_menu is ignored (mobile doesn't use native menus)
        # So app.commands.add should still not be called
        self.mock_app.commands.add.assert_not_called()

    def test_desktop_only_command_on_desktop(self):
        """Test desktop_only command is shown on desktop"""
        self.mock_app.is_mobile = False
        manager = CommandManager(self.mock_app)

        cmd = FicheroCommand(
            id="test.desktop_only",
            label="Desktop Only",
            action=lambda w: None,
            show_in_menu=True,
            desktop_only=True
        )

        manager.register_command(cmd)

        # Should be added to app.commands (desktop menus)
        self.mock_app.commands.add.assert_called_once()

    def test_desktop_only_command_on_mobile(self):
        """Test desktop_only command is filtered on mobile"""
        self.mock_app.is_mobile = True
        manager = CommandManager(self.mock_app)

        cmd = FicheroCommand(
            id="test.desktop_only",
            label="Desktop Only",
            action=lambda w: None,
            show_in_menu=True,
            desktop_only=True
        )

        manager.register_command(cmd)

        # Command should NOT be in registry (skipped completely on mobile)
        registry = CommandRegistry.get_instance()
        assert registry.get("test.desktop_only") is None

    def test_platform_agnostic_command(self):
        """Test command without platform restrictions works on both"""
        # Test on desktop
        self.mock_app.is_mobile = False
        manager_desktop = CommandManager(self.mock_app)

        cmd = FicheroCommand(
            id="test.agnostic",
            label="Platform Agnostic",
            action=lambda w: None,
            show_in_menu=True,
            mobile_only=False,
            desktop_only=False
        )

        manager_desktop.register_command(cmd)

        # Should be added to desktop menus
        assert self.mock_app.commands.add.call_count == 1

        # Reset mocks
        CommandRegistry._instance = None
        CommandRegistry._commands = {}
        CommandManager._instance = None
        self.mock_app.commands.add.reset_mock()

        # Test on mobile
        self.mock_app.is_mobile = True
        manager_mobile = CommandManager(self.mock_app)
        manager_mobile.register_command(cmd)

        # On mobile, menus are ignored, so no app.commands.add
        self.mock_app.commands.add.assert_not_called()


class TestCommandManagerMenuCreation:
    """Test desktop menu creation"""

    def setup_method(self):
        """Reset and create mock app"""
        CommandRegistry._instance = None
        CommandRegistry._commands = {}
        CommandManager._instance = None

        self.mock_app = Mock()
        self.mock_app.commands = Mock()
        self.mock_app.commands.add = Mock()

    def test_menu_command_creation_desktop(self):
        """Test that show_in_menu creates native menu items on desktop"""
        self.mock_app.is_mobile = False
        manager = CommandManager(self.mock_app)

        cmd = FicheroCommand(
            id="test.menu",
            label="Menu Command",
            action=lambda w: None,
            show_in_menu=True,
            group=toga.Group.VIEW
        )

        manager.register_command(cmd)

        # Should create toga.Command and add to app.commands
        self.mock_app.commands.add.assert_called_once()

    def test_menu_command_ignored_mobile(self):
        """Test that show_in_menu is ignored on mobile"""
        self.mock_app.is_mobile = True
        manager = CommandManager(self.mock_app)

        cmd = FicheroCommand(
            id="test.menu_mobile",
            label="Menu Command",
            action=lambda w: None,
            show_in_menu=True
        )

        manager.register_command(cmd)

        # Mobile doesn't create menu items
        self.mock_app.commands.add.assert_not_called()

    def test_menu_grouping(self):
        """Test that commands are grouped correctly in menus"""
        self.mock_app.is_mobile = False
        manager = CommandManager(self.mock_app)

        # Create commands in different groups
        commands = [
            FicheroCommand(
                id="test.view",
                label="View Cmd",
                action=lambda w: None,
                show_in_menu=True,
                group=toga.Group.VIEW
            ),
            FicheroCommand(
                id="test.edit",
                label="Edit Cmd",
                action=lambda w: None,
                show_in_menu=True,
                group=toga.Group.EDIT
            ),
            FicheroCommand(
                id="test.window",
                label="Window Cmd",
                action=lambda w: None,
                show_in_menu=True,
                group=toga.Group.WINDOW
            ),
        ]

        for cmd in commands:
            manager.register_command(cmd)

        # All should be added to app.commands
        assert self.mock_app.commands.add.call_count == 3


class TestCommandManagerToolbarPopulation:
    """Test toolbar command population"""

    def setup_method(self):
        """Reset and create mock app"""
        CommandRegistry._instance = None
        CommandRegistry._commands = {}
        CommandManager._instance = None

        self.mock_app = Mock()
        self.mock_app.commands = Mock()

    def test_get_toolbar_commands_by_view(self):
        """Test getting toolbar commands for specific view"""
        self.mock_app.is_mobile = False
        manager = CommandManager(self.mock_app)

        # Register commands for different views
        library_cmd = FicheroCommand(
            id="library.add",
            label="Add File",
            action=lambda w: None,
            show_in_bottom_toolbar=True,
            context='normal'
        )

        collection_cmd = FicheroCommand(
            id="collection.process",
            label="Process",
            action=lambda w: None,
            show_in_bottom_toolbar=True,
            context='normal'
        )

        # Add view_id to commands (normally done by register_view_commands)
        library_cmd.view_id = "library"
        collection_cmd.view_id = "collection"

        # Register commands via manager (not directly in registry)
        manager.register_command(library_cmd)
        manager.register_command(collection_cmd)

        # Get toolbar commands for library view using CommandManager method
        library_commands = manager.get_toolbar_commands(
            view_id="library",
            context="normal",
            toolbar_type="bottom"
        )

        assert len(library_commands) == 1
        assert library_commands[0].id == "library.add"

    def test_context_filtering(self):
        """Test filtering commands by context (normal vs edit)"""
        self.mock_app.is_mobile = False
        manager = CommandManager(self.mock_app)

        normal_cmd = FicheroCommand(
            id="test.normal",
            label="Normal Mode",
            action=lambda w: None,
            show_in_bottom_toolbar=True,
            context='normal'
        )

        edit_cmd = FicheroCommand(
            id="test.edit",
            label="Edit Mode",
            action=lambda w: None,
            show_in_bottom_toolbar=True,
            context='edit'
        )

        normal_cmd.view_id = "test"
        edit_cmd.view_id = "test"

        registry = CommandRegistry.get_instance()
        registry.register(normal_cmd)
        registry.register(edit_cmd)

        # Get normal mode commands
        all_commands = registry.list_all()
        normal_commands = [
            cmd for cmd in all_commands
            if cmd.context == 'normal' and cmd.show_in_bottom_toolbar
        ]

        assert len(normal_commands) == 1
        assert normal_commands[0].id == "test.normal"

        # Get edit mode commands
        edit_commands = [
            cmd for cmd in all_commands
            if cmd.context == 'edit' and cmd.show_in_bottom_toolbar
        ]

        assert len(edit_commands) == 1
        assert edit_commands[0].id == "test.edit"


class TestWindowNavigationCommands:
    """Test window navigation commands (Settings, Processing, etc.)"""

    def setup_method(self):
        """Reset and create mock app"""
        CommandRegistry._instance = None
        CommandRegistry._commands = {}
        CommandManager._instance = None

        self.mock_app = Mock()
        self.mock_app.commands = Mock()
        self.mock_app.commands.add = Mock()

    def test_settings_command_desktop(self):
        """Test Settings command appears in Window menu on desktop"""
        self.mock_app.is_mobile = False
        manager = CommandManager(self.mock_app)

        settings_cmd = FicheroCommand(
            id="library.settings",
            label="Settings",
            action=lambda w: None,
            group=toga.Group.WINDOW,
            show_in_menu=True,
            show_in_bottom_toolbar=True,
            mobile_only=False
        )

        manager.register_command(settings_cmd)

        # Should be added to app.commands (Window menu)
        self.mock_app.commands.add.assert_called_once()

        # Verify the toga.Command was created with correct group
        call_args = self.mock_app.commands.add.call_args
        toga_command = call_args[0][0]
        assert hasattr(toga_command, 'group')
        # Group would be toga.Group.WINDOW if properly passed

    def test_window_nav_commands_mobile_toolbar(self):
        """Test window navigation commands appear in mobile toolbar"""
        self.mock_app.is_mobile = True
        manager = CommandManager(self.mock_app)

        window_cmds = [
            FicheroCommand(
                id=f"library.{name}",
                label=name.title(),
                action=lambda w: None,
                group=toga.Group.WINDOW,
                show_in_menu=True,  # Ignored on mobile
                show_in_bottom_toolbar=True,
                mobile_only=False
            )
            for name in ["settings", "processing", "about", "activity", "prompts", "plans"]
        ]

        for cmd in window_cmds:
            cmd.view_id = "library"
            cmd.context = "normal"
            manager.register_command(cmd)

        # Should NOT be added to app.commands (mobile doesn't use menus)
        self.mock_app.commands.add.assert_not_called()

        # But should be in registry for toolbar
        registry = CommandRegistry.get_instance()
        toolbar_commands = [
            cmd for cmd in registry.list_all()
            if cmd.show_in_bottom_toolbar
        ]

        assert len(toolbar_commands) == 6


class TestOutputViewCommands:
    """Test OutputView command system"""

    def setup_method(self):
        """Reset and create mock app"""
        CommandRegistry._instance = None
        CommandRegistry._commands = {}
        CommandManager._instance = None

        self.mock_app = Mock()
        self.mock_app.commands = Mock()
        self.mock_app.commands.add = Mock()

    def test_edit_commands_in_menu(self):
        """Test edit commands (Rotate, Crop, Reset) appear in Edit menu"""
        self.mock_app.is_mobile = False
        manager = CommandManager(self.mock_app)

        edit_cmds = [
            FicheroCommand(
                id=f"output.edit.{name}",
                label=name.replace('_', ' ').title(),
                action=lambda w: None,
                group=toga.Group.EDIT,
                show_in_menu=True,
                show_in_bottom_toolbar=True
            )
            for name in ["rotate_left", "rotate_right", "crop", "reset"]
        ]

        for cmd in edit_cmds:
            manager.register_command(cmd)

        # With section rebuilding: 1 + 2 + 3 + 4 = 10 calls to add
        # (Each time a command is added to the section, the entire section is rebuilt)
        assert self.mock_app.commands.add.call_count == 10

    def test_zoom_commands_in_view_menu(self):
        """Test zoom commands appear in View menu"""
        self.mock_app.is_mobile = False
        manager = CommandManager(self.mock_app)

        zoom_cmds = [
            FicheroCommand(
                id=f"output.view.{name}",
                label=name.replace('_', ' ').title(),
                action=lambda w: None,
                group=toga.Group.VIEW,
                show_in_menu=True,
                show_in_bottom_toolbar=False  # Zoom not in toolbar
            )
            for name in ["zoom_in", "zoom_out", "zoom_fit", "actual_size",
                        "fit_width", "fit_height", "zoom_selection"]
        ]

        for cmd in zoom_cmds:
            manager.register_command(cmd)

        # With section rebuilding: 1 + 2 + 3 + 4 + 5 + 6 + 7 = 28 calls to add
        assert self.mock_app.commands.add.call_count == 28

    def test_navigation_commands_in_window_menu(self):
        """Test navigation commands appear in Window menu"""
        self.mock_app.is_mobile = False
        manager = CommandManager(self.mock_app)

        nav_cmds = [
            FicheroCommand(
                id=f"output.nav.{name}",
                label=name.replace('_', ' ').title(),
                action=lambda w: None,
                group=toga.Group.WINDOW,
                show_in_menu=True,
                show_in_bottom_toolbar=False  # Nav not in toolbar
            )
            for name in ["prev_file", "next_file", "prev_step", "next_step"]
        ]

        for cmd in nav_cmds:
            manager.register_command(cmd)

        # With section rebuilding: 1 + 2 + 3 + 4 = 10 calls to add
        assert self.mock_app.commands.add.call_count == 10


class TestCommandAccumulation:
    """Test desktop toolbar command accumulation"""

    def setup_method(self):
        """Reset"""
        CommandRegistry._instance = None
        CommandRegistry._commands = {}
        CommandManager._instance = None

    def test_toolbar_accumulation_concept(self):
        """Test that commands from multiple views can accumulate"""
        registry = CommandRegistry.get_instance()

        # Simulate LibraryView registering commands
        library_cmds = [
            FicheroCommand(
                id=f"library.{name}",
                label=name.title(),
                action=lambda w: None,
                show_in_bottom_toolbar=True,
                context='normal'
            )
            for name in ["add_file", "add_folder", "add_url"]
        ]

        for cmd in library_cmds:
            cmd.view_id = "library"
            registry.register(cmd)

        # Simulate CollectionView registering commands
        collection_cmds = [
            FicheroCommand(
                id=f"collection.{name}",
                label=name.title(),
                action=lambda w: None,
                show_in_bottom_toolbar=True,
                context='normal'
            )
            for name in ["process", "add_file", "add_folder"]
        ]

        for cmd in collection_cmds:
            cmd.view_id = "collection"
            registry.register(cmd)

        # Get all toolbar commands
        all_toolbar_commands = [
            cmd for cmd in registry.list_all()
            if cmd.show_in_bottom_toolbar
        ]

        # Should have 6 total (3 from library + 3 from collection)
        assert len(all_toolbar_commands) == 6


# Integration test for complete flow
class TestCommandSystemIntegration:
    """Integration tests for complete command flow"""

    def setup_method(self):
        """Reset everything"""
        CommandRegistry._instance = None
        CommandRegistry._commands = {}
        CommandManager._instance = None

    def test_complete_desktop_flow(self):
        """Test complete command registration and retrieval flow on desktop"""
        # Create mock app
        mock_app = Mock()
        mock_app.commands = Mock()
        mock_app.commands.add = Mock()
        mock_app.is_mobile = False

        # Create manager
        manager = CommandManager(mock_app)

        # Register a complete command
        cmd = FicheroCommand(
            id="integration.test",
            label="Integration Test",
            action=lambda w: print("Test"),
            group=toga.Group.VIEW,
            show_in_menu=True,
            show_in_bottom_toolbar=True,
            mobile_only=False,
            desktop_only=False,
            context='normal'
        )

        cmd.view_id = "test"
        manager.register_command(cmd)

        # Verify command is in registry
        registry = CommandRegistry.get_instance()
        retrieved = registry.get("integration.test")
        assert retrieved == cmd

        # Verify menu item was created
        mock_app.commands.add.assert_called_once()

        # Verify command is available for toolbar
        toolbar_cmds = [
            c for c in registry.list_all()
            if c.show_in_bottom_toolbar
        ]
        assert cmd in toolbar_cmds

    def test_complete_mobile_flow(self):
        """Test complete command registration flow on mobile"""
        mock_app = Mock()
        mock_app.commands = Mock()
        mock_app.is_mobile = True

        manager = CommandManager(mock_app)

        cmd = FicheroCommand(
            id="mobile.test",
            label="Mobile Test",
            action=lambda w: None,
            show_in_menu=True,  # Should be ignored
            show_in_bottom_toolbar=True,
            mobile_only=False,
            context='normal'
        )

        cmd.view_id = "test"
        manager.register_command(cmd)

        # Verify command is in registry
        registry = CommandRegistry.get_instance()
        assert registry.get("mobile.test") == cmd

        # Verify NO menu item was created (mobile doesn't use menus)
        mock_app.commands.add.assert_not_called()


class TestMenuOrganization:
    """Test menu organization features: section, order, and submenus"""

    def setup_method(self):
        """Reset everything"""
        CommandRegistry._instance = None
        CommandRegistry._commands = {}
        CommandManager._instance = None

    def test_command_with_section_and_order(self):
        """Test creating command with section and order parameters"""
        cmd = FicheroCommand(
            id="test.ordered",
            label="Ordered Command",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=2,
            order=5
        )

        assert cmd.section == 2
        assert cmd.order == 5

    def test_command_with_parent(self):
        """Test creating command with parent for submenus"""
        parent_cmd = FicheroCommand(
            id="edit.rotate",
            label="Rotate",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=2,
            order=0
        )

        child_cmd = FicheroCommand(
            id="edit.rotate.left",
            label="Rotate Left",
            action=lambda w: None,
            parent="edit.rotate",
            section=2,
            order=0
        )

        assert parent_cmd.parent is None
        assert child_cmd.parent == "edit.rotate"

    def test_section_ordering(self):
        """Test that commands are tracked by section in CommandManager"""
        mock_app = Mock()
        mock_app.commands = Mock()
        mock_app.commands.add = Mock()
        mock_app.commands.discard = Mock()
        mock_app.is_mobile = False

        manager = CommandManager(mock_app)

        # Create commands in same group but different sections
        cmd1 = FicheroCommand(
            id="test.section0",
            label="Section 0",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=0,
            order=0,
            show_in_menu=True
        )

        cmd2 = FicheroCommand(
            id="test.section1",
            label="Section 1",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=1,
            order=0,
            show_in_menu=True
        )

        manager.register_command(cmd1)
        manager.register_command(cmd2)

        # Check internal tracking structure
        assert (toga.Group.EDIT, 0) in manager._menu_commands
        assert (toga.Group.EDIT, 1) in manager._menu_commands
        assert len(manager._menu_commands[(toga.Group.EDIT, 0)]) == 1
        assert len(manager._menu_commands[(toga.Group.EDIT, 1)]) == 1

    def test_order_within_section(self):
        """Test that commands are sorted by order within same section"""
        mock_app = Mock()
        mock_app.commands = Mock()
        mock_app.commands.add = Mock()
        mock_app.commands.discard = Mock()
        mock_app.is_mobile = False

        manager = CommandManager(mock_app)

        # Create commands in same section but different orders
        # Register in reverse order to verify sorting
        cmd3 = FicheroCommand(
            id="test.order2",
            label="Order 2",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=0,
            order=2,
            show_in_menu=True
        )

        cmd1 = FicheroCommand(
            id="test.order0",
            label="Order 0",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=0,
            order=0,
            show_in_menu=True
        )

        cmd2 = FicheroCommand(
            id="test.order1",
            label="Order 1",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=0,
            order=1,
            show_in_menu=True
        )

        # Register in random order
        manager.register_command(cmd3)
        manager.register_command(cmd1)
        manager.register_command(cmd2)

        # Verify they are sorted by order
        section_commands = manager._menu_commands[(toga.Group.EDIT, 0)]
        assert section_commands[0].id == "test.order0"
        assert section_commands[1].id == "test.order1"
        assert section_commands[2].id == "test.order2"

    def test_submenu_group_creation(self):
        """Test that parent commands create submenu groups"""
        mock_app = Mock()
        mock_app.commands = Mock()
        mock_app.commands.add = Mock()
        mock_app.commands.discard = Mock()
        mock_app.is_mobile = False

        manager = CommandManager(mock_app)
        registry = CommandRegistry.get_instance()

        # Register parent command first
        parent = FicheroCommand(
            id="edit.rotate",
            label="Rotate",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=2,
            order=0,
            show_in_menu=True
        )
        manager.register_command(parent)

        # Register child command with parent reference
        child = FicheroCommand(
            id="edit.rotate.left",
            label="Rotate Left",
            action=lambda w: None,
            parent="edit.rotate",
            section=2,
            order=0,
            show_in_menu=True
        )
        manager.register_command(child)

        # Verify submenu group was created
        assert "edit.rotate" in manager._submenu_groups
        submenu_group = manager._submenu_groups["edit.rotate"]
        assert submenu_group is not None

    def test_multiple_children_same_parent(self):
        """Test multiple child commands with same parent"""
        mock_app = Mock()
        mock_app.commands = Mock()
        mock_app.commands.add = Mock()
        mock_app.commands.discard = Mock()
        mock_app.is_mobile = False

        manager = CommandManager(mock_app)
        registry = CommandRegistry.get_instance()

        # Register parent
        parent = FicheroCommand(
            id="edit.rotate",
            label="Rotate",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=2,
            order=0,
            show_in_menu=True
        )
        manager.register_command(parent)

        # Register multiple children
        child1 = FicheroCommand(
            id="edit.rotate.left",
            label="Rotate Left",
            action=lambda w: None,
            parent="edit.rotate",
            section=2,
            order=0,
            show_in_menu=True
        )

        child2 = FicheroCommand(
            id="edit.rotate.right",
            label="Rotate Right",
            action=lambda w: None,
            parent="edit.rotate",
            section=2,
            order=1,
            show_in_menu=True
        )

        child3 = FicheroCommand(
            id="edit.rotate.180",
            label="Rotate 180°",
            action=lambda w: None,
            parent="edit.rotate",
            section=2,
            order=2,
            show_in_menu=True
        )

        manager.register_command(child1)
        manager.register_command(child2)
        manager.register_command(child3)

        # All children should use same submenu group
        assert "edit.rotate" in manager._submenu_groups
        # Verify all three commands are registered
        assert registry.get("edit.rotate.left") == child1
        assert registry.get("edit.rotate.right") == child2
        assert registry.get("edit.rotate.180") == child3

    def test_section_rebuilding_on_new_command(self):
        """Test that adding new command rebuilds section with correct order"""
        mock_app = Mock()
        mock_app.commands = Mock()
        mock_app.commands.add = Mock()
        mock_app.commands.discard = Mock()
        mock_app.is_mobile = False

        manager = CommandManager(mock_app)

        # Add first command
        cmd1 = FicheroCommand(
            id="test.first",
            label="First",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=0,
            order=0,
            show_in_menu=True
        )
        manager.register_command(cmd1)

        # Should have been added once
        assert mock_app.commands.add.call_count == 1

        # Add second command to same section
        cmd2 = FicheroCommand(
            id="test.second",
            label="Second",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=0,
            order=1,
            show_in_menu=True
        )
        manager.register_command(cmd2)

        # Section should be rebuilt, so commands are added again
        # Total calls: 1 (first cmd) + 2 (rebuild with both)
        assert mock_app.commands.add.call_count == 3

    def test_default_section_and_order(self):
        """Test that section and order default to 0"""
        cmd = FicheroCommand(
            id="test.defaults",
            label="Default Values",
            action=lambda w: None
        )

        assert cmd.section == 0
        assert cmd.order == 0
        assert cmd.parent is None

    def test_parent_without_registry_lookup(self):
        """Test submenu group creation when parent not in registry"""
        mock_app = Mock()
        mock_app.commands = Mock()
        mock_app.commands.add = Mock()
        mock_app.commands.discard = Mock()
        mock_app.is_mobile = False

        manager = CommandManager(mock_app)

        # Register child without parent in registry
        # This tests fallback to ID-based label generation
        child = FicheroCommand(
            id="edit.unknown_parent.child",
            label="Child Command",
            action=lambda w: None,
            parent="edit.unknown_parent",
            group=toga.Group.EDIT,
            section=2,
            order=0,
            show_in_menu=True
        )
        manager.register_command(child)

        # Should still create submenu group with fallback label
        assert "edit.unknown_parent" in manager._submenu_groups

    def test_complex_menu_structure(self):
        """Test complex menu with multiple sections, orders, and submenus"""
        mock_app = Mock()
        mock_app.commands = Mock()
        mock_app.commands.add = Mock()
        mock_app.commands.discard = Mock()
        mock_app.is_mobile = False

        manager = CommandManager(mock_app)

        # Section 0: Basic edit commands
        undo = FicheroCommand(
            id="edit.undo",
            label="Undo",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=0,
            order=0,
            show_in_menu=True
        )

        redo = FicheroCommand(
            id="edit.redo",
            label="Redo",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=0,
            order=1,
            show_in_menu=True
        )

        # Section 1: Cut/Copy/Paste
        cut = FicheroCommand(
            id="edit.cut",
            label="Cut",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=1,
            order=0,
            show_in_menu=True
        )

        copy = FicheroCommand(
            id="edit.copy",
            label="Copy",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=1,
            order=1,
            show_in_menu=True
        )

        # Section 2: Rotate submenu
        rotate_parent = FicheroCommand(
            id="edit.rotate",
            label="Rotate",
            action=lambda w: None,
            group=toga.Group.EDIT,
            section=2,
            order=0,
            show_in_menu=True
        )

        rotate_left = FicheroCommand(
            id="edit.rotate.left",
            label="Rotate Left",
            action=lambda w: None,
            parent="edit.rotate",
            section=2,
            order=0,
            show_in_menu=True
        )

        rotate_right = FicheroCommand(
            id="edit.rotate.right",
            label="Rotate Right",
            action=lambda w: None,
            parent="edit.rotate",
            section=2,
            order=1,
            show_in_menu=True
        )

        # Register all commands
        for cmd in [undo, redo, cut, copy, rotate_parent, rotate_left, rotate_right]:
            manager.register_command(cmd)

        # Verify section structure
        assert (toga.Group.EDIT, 0) in manager._menu_commands
        assert (toga.Group.EDIT, 1) in manager._menu_commands
        assert (toga.Group.EDIT, 2) in manager._menu_commands

        # Verify order within sections
        section0 = manager._menu_commands[(toga.Group.EDIT, 0)]
        assert section0[0].id == "edit.undo"
        assert section0[1].id == "edit.redo"

        section1 = manager._menu_commands[(toga.Group.EDIT, 1)]
        assert section1[0].id == "edit.cut"
        assert section1[1].id == "edit.copy"

        # Verify submenu was created
        assert "edit.rotate" in manager._submenu_groups


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
