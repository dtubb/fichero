"""
ViewCommandMixin - Simplifies command registration for views

This mixin provides a unified way for views to register commands with the
command system. Views define commands once, and the mixin handles all the
platform-specific registration automatically.

Usage:
    class MyView(BaseView, ViewCommandMixin):
        def __init__(self, app, is_mobile=False):
            super().__init__(app, is_mobile)

            # Define commands for this view
            self.define_commands()

            # Register with system (auto-handles platform)
            self.register_commands()
"""

import toga
import logging
from typing import Dict, Optional
from fichero.shared.commands.command import FicheroCommand
from fichero.shared.commands.command_manager import CommandManager

logger = logging.getLogger(__name__)


class ViewCommandMixin:
    """
    Mixin for views to easily register and manage commands.

    This mixin provides:
    - Automatic command registration with CommandManager
    - Platform-aware setup (mobile/desktop)
    - Toolbar auto-population from registered commands

    The view class must have:
    - self.app: The Toga application instance
    - self.view_id: Unique identifier for this view (e.g., "library", "output")
    - self.commands: Dict of FicheroCommand instances (populated by define_commands)
    """

    def __init__(self):
        """Initialize the mixin (called by view)"""
        self.commands: Dict[str, FicheroCommand] = {}
        self.command_manager: Optional[CommandManager] = None

    def define_commands(self) -> None:
        """
        Define commands for this view.

        Override this method in your view to define commands.
        Populate self.commands dict with FicheroCommand instances.

        Example:
            def define_commands(self):
                self.commands = {
                    'rotate_left': FicheroCommand(
                        id=f'{self.view_id}.rotate_left',
                        label='Rotate Left',
                        action=self._rotate_left,
                        shortcut=toga.Key.MOD_1 + 'l',
                        icon='resources/icons/rotate_left.png',
                        toolbar_position='center',
                        show_in_menu=True,      # Desktop: adds to menu with shortcut
                        show_in_toolbar=True    # Both: adds to toolbar
                    ),
                    'rotate_right': FicheroCommand(
                        id=f'{self.view_id}.rotate_right',
                        label='Rotate Right',
                        action=self._rotate_right,
                        shortcut=toga.Key.MOD_1 + 'r',
                        icon='resources/icons/rotate_right.png',
                        toolbar_position='center',
                        show_in_menu=True,
                        show_in_toolbar=True
                    )
                }
        """
        logger.warning(f"define_commands() not implemented in {self.__class__.__name__}")

    def register_commands(self) -> None:
        """
        Register all commands with the CommandManager.

        This method should be called after define_commands() to register
        all commands with the system. It automatically:
        - Gets CommandManager instance
        - Registers all commands in self.commands
        - Routes to menus (desktop) or toolbars (mobile/desktop)

        Call this in your view's __init__ after define_commands().
        """
        try:
            if not hasattr(self, 'app'):
                logger.error("ViewCommandMixin requires self.app to be set")
                return

            if not hasattr(self, 'view_id'):
                logger.error("ViewCommandMixin requires self.view_id to be set")
                return

            if not self.commands:
                logger.debug(f"No commands defined for view '{self.view_id}'")
                return

            # Get command manager instance
            self.command_manager = CommandManager.get_instance(self.app)

            # Register all commands for this view
            self.command_manager.register_view_commands(self.view_id, self.commands)

            logger.info(f"✅ Registered {len(self.commands)} commands for view '{self.view_id}'")

        except Exception as e:
            logger.error(f"Failed to register commands for view '{self.view_id}': {e}")

    def populate_toolbar_with_commands(self, toolbar, context: str = "normal") -> None:
        """
        Auto-populate a toolbar with this view's commands.

        Args:
            toolbar: The toolbar to populate (TopToolbar, BottomToolbar, etc.)
            context: Context for filtering (e.g., "normal", "edit")

        Example:
            # In your view's toolbar setup:
            self.top_toolbar.populate_from_commands(self.view_id, context="normal")

            # Or using this helper method:
            self.populate_toolbar_with_commands(self.top_toolbar, "normal")
        """
        try:
            if not hasattr(toolbar, 'populate_from_commands'):
                logger.error(f"Toolbar does not support populate_from_commands")
                return

            toolbar.populate_from_commands(self.view_id, context=context)

        except Exception as e:
            logger.error(f"Failed to populate toolbar: {e}")

    def get_command(self, command_name: str) -> Optional[FicheroCommand]:
        """
        Get a command by its name.

        Args:
            command_name: Name of the command (key in self.commands dict)

        Returns:
            The FicheroCommand instance, or None if not found
        """
        return self.commands.get(command_name)

    def enable_command(self, command_name: str) -> None:
        """Enable a command by name"""
        command = self.get_command(command_name)
        if command:
            command.enable()

    def disable_command(self, command_name: str) -> None:
        """Disable a command by name"""
        command = self.get_command(command_name)
        if command:
            command.disable()
