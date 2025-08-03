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
        logger.info("MenuManager initialized - using pure Toga standard commands")
    
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

 