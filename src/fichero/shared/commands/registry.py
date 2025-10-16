"""
CommandRegistry - Central registry for all application commands

Provides a singleton registry where all commands are registered and can be:
- Retrieved by ID
- Executed by ID
- Enabled/disabled globally
- Listed for UI population
"""

import logging
from typing import Dict, Optional, List
from .command import FicheroCommand

logger = logging.getLogger(__name__)


class CommandRegistry:
    """
    Singleton registry for all Fichero commands.

    This central registry allows commands to be:
    1. Registered once
    2. Used by toolbars, menus, and keyboard handlers
    3. Enabled/disabled globally
    4. Executed from any source

    Example:
        # In app initialization:
        registry = CommandRegistry.get_instance()
        registry.register(rotate_left_command)
        registry.register(rotate_right_command)

        # In toolbar:
        toolbar.add_command_button(registry.get("output.rotate_left"))

        # In menu:
        menu.add_command(registry.get("output.rotate_left"))

        # Direct execution:
        registry.execute("output.rotate_left")
    """

    _instance: Optional['CommandRegistry'] = None

    @classmethod
    def get_instance(cls) -> 'CommandRegistry':
        """Get the singleton instance of the CommandRegistry."""
        if cls._instance is None:
            cls._instance = cls()
            logger.info("CommandRegistry singleton created")
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None
        logger.debug("CommandRegistry singleton reset")

    def __init__(self):
        """Initialize the command registry."""
        if CommandRegistry._instance is not None:
            raise RuntimeError("CommandRegistry is a singleton. Use get_instance() instead.")

        self._commands: Dict[str, FicheroCommand] = {}
        logger.info("CommandRegistry initialized")

    def register(self, command: FicheroCommand) -> None:
        """
        Register a command in the registry.

        Args:
            command: The command to register

        Raises:
            ValueError: If a command with the same ID is already registered
        """
        if command.id in self._commands:
            logger.warning(f"Overwriting existing command: {command.id}")

        self._commands[command.id] = command
        logger.debug(f"Registered command: {command.id} ({command.label})")

    def unregister(self, command_id: str) -> None:
        """
        Unregister a command from the registry.

        Args:
            command_id: ID of the command to unregister
        """
        if command_id in self._commands:
            command = self._commands.pop(command_id)
            logger.debug(f"Unregistered command: {command_id}")
        else:
            logger.warning(f"Attempted to unregister non-existent command: {command_id}")

    def get(self, command_id: str) -> Optional[FicheroCommand]:
        """
        Get a command by its ID.

        Args:
            command_id: ID of the command to retrieve

        Returns:
            The command if found, None otherwise
        """
        command = self._commands.get(command_id)
        if command is None:
            logger.warning(f"Command not found: {command_id}")
        return command

    def execute(self, command_id: str, *args, **kwargs):
        """
        Execute a command by its ID.

        Args:
            command_id: ID of the command to execute
            *args: Positional arguments to pass to the command
            **kwargs: Keyword arguments to pass to the command

        Returns:
            Result of the command execution, if any

        Raises:
            ValueError: If command is not found
            Exception: If command execution fails
        """
        command = self.get(command_id)
        if command is None:
            raise ValueError(f"Command not found: {command_id}")

        return command.execute(*args, **kwargs)

    def enable(self, command_id: str) -> None:
        """
        Enable a command.

        Args:
            command_id: ID of the command to enable
        """
        command = self.get(command_id)
        if command:
            command.enable()

    def disable(self, command_id: str) -> None:
        """
        Disable a command.

        Args:
            command_id: ID of the command to disable
        """
        command = self.get(command_id)
        if command:
            command.disable()

    def list_all(self) -> List[FicheroCommand]:
        """
        Get a list of all registered commands.

        Returns:
            List of all commands in the registry
        """
        return list(self._commands.values())

    def list_with_shortcuts(self) -> List[FicheroCommand]:
        """
        Get a list of commands that have keyboard shortcuts.

        Returns:
            List of commands with shortcuts defined
        """
        return [cmd for cmd in self._commands.values() if cmd.shortcut]

    def get_commands_for_view(
        self,
        view_id: str,
        context: str = None,
        show_in_top_toolbar: bool = None,
        show_in_bottom_toolbar: bool = None
    ) -> List[FicheroCommand]:
        """
        Get filtered commands for a specific view.

        This is the core method for the declarative system - toolbars query this
        to get the commands they should display.

        Args:
            view_id: View identifier (e.g., "library", "output", "collection")
            context: Filter by context ('normal', 'edit', etc.) - None means all
            show_in_top_toolbar: Filter by top toolbar visibility - None means all
            show_in_bottom_toolbar: Filter by bottom toolbar visibility - None means all

        Returns:
            List of commands matching the filters

        Example:
            # Get all edit mode bottom toolbar commands for library view
            commands = registry.get_commands_for_view(
                view_id='library',
                context='edit',
                show_in_bottom_toolbar=True
            )
        """
        results = []

        for command in self._commands.values():
            # Filter by view_id (command IDs are prefixed with view_id)
            if not command.id.startswith(f"{view_id}."):
                continue

            # Filter by context
            if context is not None and command.context != context:
                continue

            # Filter by top toolbar visibility
            if show_in_top_toolbar is not None and command.show_in_top_toolbar != show_in_top_toolbar:
                continue

            # Filter by bottom toolbar visibility
            if show_in_bottom_toolbar is not None and command.show_in_bottom_toolbar != show_in_bottom_toolbar:
                continue

            results.append(command)

        logger.debug(
            f"get_commands_for_view(view_id={view_id}, context={context}, "
            f"show_in_top_toolbar={show_in_top_toolbar}, show_in_bottom_toolbar={show_in_bottom_toolbar}) "
            f"returned {len(results)} commands"
        )

        return results

    def clear(self) -> None:
        """Clear all commands from the registry (useful for testing)."""
        self._commands.clear()
        logger.debug("All commands cleared from registry")

    def __repr__(self) -> str:
        """String representation of the registry."""
        return f"CommandRegistry({len(self._commands)} commands)"
