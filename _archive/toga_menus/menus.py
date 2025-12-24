"""
Menu Management for Fichero - Pure Toga Standard Approach

This module now does nothing - letting Toga handle everything automatically.
This shows how Toga's standard command system works without any custom overrides.
"""

import toga
import logging

logger = logging.getLogger(__name__)


class MenuManager:
    """Minimal menu manager - no custom overrides, pure Toga standard"""

    def __init__(self, app):
        """Initialize the menu manager"""
        self.app = app
        self._command_map = {}  # Maps FicheroCommand.id to Toga Command
        logger.info("MenuManager initialized - using pure Toga standard commands")

    def add_command(self, fichero_command, group=None):
        """
        Add a FicheroCommand to the menu system with keyboard shortcut.

        This creates a Toga Command with keyboard shortcut support and adds it
        to the app's command set. The command can be triggered from menus,
        toolbars, or direct keyboard shortcuts.

        Args:
            fichero_command: FicheroCommand instance with id, label, action, and shortcut
            group: Optional Toga command group (e.g., toga.Group.EDIT, toga.Group.VIEW)

        Example:
            # In app initialization:
            from fichero.shared.commands import CommandRegistry

            registry = CommandRegistry.get_instance()
            rotate_left = registry.get("output.rotate_left")
            menu_manager.add_command(rotate_left, group=toga.Group.EDIT)
        """
        try:
            # Create wrapper action that logs menu selection before executing
            def logged_action(widget):
                logger.info(f"🎯 Menu/Shortcut triggered: {fichero_command.id} ({fichero_command.label})")
                return fichero_command.execute(widget)

            # Create Toga command from FicheroCommand
            toga_cmd = toga.Command(
                action=logged_action,
                text=fichero_command.label,
                tooltip=fichero_command.description,
                shortcut=fichero_command.shortcut,
                group=group or toga.Group.COMMANDS,
                section=0
            )

            # Add to app commands
            self.app.commands.add(toga_cmd)

            # Store mapping for later reference
            self._command_map[fichero_command.id] = toga_cmd

            logger.debug(f"Added command to menu: {fichero_command.label} (shortcut: {fichero_command.shortcut})")

        except Exception as e:
            logger.error(f"Failed to add command {fichero_command.id}: {e}")
    
    def customize_standard_commands(self):
        """No customizations - let Toga handle everything"""
        try:
            # Remove document commands we don't implement
            document_commands_to_remove = [
                toga.Command.OPEN,
                toga.Command.SAVE,
                toga.Command.SAVE_AS,
                toga.Command.SAVE_ALL
            ]
            
            for cmd_id in document_commands_to_remove:
                try:
                    if cmd_id in self.app.commands:
                        logger.info(f"Removing unimplemented command: {cmd_id}")
                        self.app.commands.discard(cmd_id)
                except Exception as cmd_error:
                    logger.debug(f"Could not remove command {cmd_id}: {cmd_error}")
                    
            logger.info("Using pure Toga standard commands - no custom overrides")
                    
        except Exception as e:
            logger.error(f"Error in standard command customization: {e}")

 