"""
Command Manager for Fichero

Manages Toga commands and their registration with the app.
"""

import toga
import logging
from typing import Optional, Any, Dict, List

from fichero.windows.main.commands.command_bridge import CommandBridge

logger = logging.getLogger(__name__)


class CommandManagerRefactored:
    """Refactored command manager for Fichero"""
    
    def __init__(self, app):
        """Initialize command manager"""
        self.app = app
        
        # Command bridge
        self.command_bridge: Optional[CommandBridge] = None
        
        # Command registry
        self.registered_commands: Dict[str, toga.Command] = {}
        
        # Initialize commands
        self._initialize_commands()
        
        logger.info("Refactored command manager initialized successfully")
    
    def _initialize_commands(self):
        """Initialize essential commands"""
        try:
            # Create Settings command for App menu
            settings_cmd = toga.Command(
                self._on_settings,
                text="Settings…",
                icon=toga.Icon("resources/icons/toolbar/gear@10x.png"),
                group=toga.Group.APP,
                section=0,
                order=0
            )
            self.registered_commands["settings"] = settings_cmd
            
            # Create Activity Monitor command for Window menu
            activity_cmd = toga.Command(
                self._on_activity_monitor,
                text="Activity Monitor",
                icon=toga.Icon("resources/icons/toolbar/activity.png"),
                group=toga.Group.WINDOW,
                section=0,
                order=0
            )
            self.registered_commands["activity"] = activity_cmd
            
            # Create Plans command for App menu  
            plans_cmd = toga.Command(
                self._on_plans,
                text="Plans…",
                icon=toga.Icon("resources/icons/toolbar/plan.png"),
                group=toga.Group.APP,
                section=0,
                order=1
            )
            self.registered_commands["plans"] = plans_cmd
            
            # Create Prompts command for App menu
            prompts_cmd = toga.Command(
                self._on_prompts,
                text="Prompts…",
                icon=toga.Icon("resources/icons/toolbar/prompt.png"),
                group=toga.Group.APP,
                section=0,
                order=2
            )
            self.registered_commands["prompts"] = prompts_cmd
            
            # Create Processing command for File menu
            processing_cmd = toga.Command(
                self._on_processing,
                text="Process Documents…",
                icon=toga.Icon("resources/icons/toolbar/process.png"),
                group=toga.Group.FILE,
                section=0,
                order=0
            )
            self.registered_commands["processing"] = processing_cmd
            
            logger.info(f"Essential commands created: {list(self.registered_commands.keys())}")
            
        except Exception as e:
            logger.error(f"Failed to initialize commands: {e}")
    
    def _on_settings(self, widget):
        """Handle Settings command"""
        try:
            logger.debug("Settings command executed")
            
            # Use the app's settings window method
            if hasattr(self.app, 'show_settings'):
                self.app.show_settings()
            else:
                logger.warning("Settings window not available")
                
        except Exception as e:
            logger.error(f"Failed to open settings: {e}")
    
    def _on_activity_monitor(self, widget):
        """Handle Activity Monitor command"""
        try:
            logger.debug("Activity Monitor command executed")
            
            # Use the app's activity monitor method
            if hasattr(self.app, 'show_activity_monitor'):
                self.app.show_activity_monitor()
            else:
                logger.warning("Activity monitor not available")
                
        except Exception as e:
            logger.error(f"Failed to show activity monitor: {e}")
    
    def _on_plans(self, widget):
        """Handle Plans command"""
        try:
            logger.debug("Plans command executed")
            
            # Use the app's plans window method
            if hasattr(self.app, 'show_plans'):
                self.app.show_plans()
            else:
                logger.warning("Plans window not available")
                
        except Exception as e:
            logger.error(f"Failed to open plans: {e}")
    
    def _on_prompts(self, widget):
        """Handle Prompts command"""
        try:
            logger.debug("Prompts command executed")
            
            # Use the app's prompts window method
            if hasattr(self.app, 'show_prompts'):
                self.app.show_prompts()
            else:
                logger.warning("Prompts window not available")
                
        except Exception as e:
            logger.error(f"Failed to open prompts: {e}")
    
    def _on_processing(self, widget):
        """Handle Processing command"""
        try:
            logger.debug("Processing command executed")
            
            # Use the app's processing window method
            if hasattr(self.app, 'show_processing'):
                self.app.show_processing()
            else:
                logger.warning("Processing window not available")
                
        except Exception as e:
            logger.error(f"Failed to open processing: {e}")
    
    def set_command_bridge(self, command_bridge: CommandBridge):
        """Set the command bridge"""
        self.command_bridge = command_bridge
        logger.info("CommandManager wrapper initialized")
    
    def add_to_app(self):
        """Add commands to the Toga app - compatibility method"""
        try:
            # Add commands to app
            for command in self.registered_commands.values():
                self.app.commands.add(command)
            
            logger.info(f"Added {len(self.registered_commands)} commands to app")
            logger.info("Commands added to app successfully")
            
        except Exception as e:
            logger.error(f"Failed to add commands to app: {e}")
    
    def add_commands_to_app(self):
        """Add commands to the Toga app"""
        try:
            # Add commands to app
            for command in self.registered_commands.values():
                self.app.commands.add(command)
            
            logger.info("Added 0 commands to app")
            logger.info("Commands added to app successfully")
            
        except Exception as e:
            logger.error(f"Failed to add commands to app: {e}")
    
    def get_command_info(self) -> Dict[str, Any]:
        """Get information about registered commands"""
        return {
            'total_commands': len(self.registered_commands),
            'registered_commands': list(self.registered_commands.keys())
        } 