"""
Command Manager for Fichero Main Window

Manages command registration and menu integration.
Handles platform-specific command availability.
"""

import toga
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class CommandManagerRefactored:
    """
    Simplified command manager focused on essential Fichero commands.
    No complex command abstractions - direct toga command registration.
    """
    
    def __init__(self, app):
        """Initialize command manager"""
        self.app = app
        self.registered_commands: Dict[str, toga.Command] = {}
        
        logger.info("CommandManagerRefactored initialized")

        # Initialize commands immediately
        self._initialize_commands()

    def set_command_bridge(self, command_bridge):
        """Set command bridge - compatibility method for main window"""
        # This method exists for compatibility with main window initialization
        # The refactored command manager doesn't need the bridge pattern
        logger.debug("Command bridge set (compatibility method)")
    
    def _initialize_commands(self):
        """Initialize essential commands"""
        try:
            # Create Settings command (default App menu location)
            settings_cmd = toga.Command(
                self._on_settings,
                text="Settings…",
                icon=toga.Icon("resources/icons/toolbar/settings.png"),
                group=toga.Group.APP,
                section=0,
                order=2
            )
            self.registered_commands["settings"] = settings_cmd
            
            # Create Activity Monitor command
            activity_cmd = toga.Command(
                self._on_activity_monitor,
                text="Activity Monitor",
                icon=toga.Icon("resources/icons/toolbar/activity.png"),
                group=toga.Group.VIEW,
                section=1,
                order=0
            )
            self.registered_commands["activity"] = activity_cmd
            
            # Create Plans command for Tools menu
            plans_cmd = toga.Command(
                self._on_plans,
                text="Plans…",
                icon=toga.Icon("resources/icons/toolbar/plans.png"),
                group=toga.Group.FILE,
                section=2,
                order=1
            )
            self.registered_commands["plans"] = plans_cmd
            
            # Create Prompts command for Tools menu
            prompts_cmd = toga.Command(
                self._on_prompts,
                text="Prompts…",
                icon=toga.Icon("resources/icons/toolbar/prompts.png"),
                group=toga.Group.FILE,
                section=2,
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
            
            # Initialize Add commands based on platform features
            self._initialize_add_commands()
            
            # Create Preview command for View menu
            preview_cmd = toga.Command(
                self._on_preview,
                text="Preview Window",
                icon=toga.Icon("resources/icons/toolbar/preview.png"),
                group=toga.Group.VIEW,
                section=0,
                order=0
            )
            self.registered_commands["preview"] = preview_cmd
            
            logger.info(f"Essential commands created: {list(self.registered_commands.keys())}")
            
        except Exception as e:
            logger.error(f"Failed to initialize commands: {e}")
    
    def _initialize_add_commands(self):
        """Initialize platform-specific Add commands"""
        try:
            from fichero.windows.add.platform_features import detect_platform_features, get_available_add_options
            
            # Detect platform features
            platform_features = detect_platform_features(self.app)
            available_options = get_available_add_options(platform_features)
            
            logger.info(f"Initializing {len(available_options)} add commands")
            
            # General "Add to Library" command
            general_cmd = toga.Command(
                self._on_add_general,
                text="Add to Library…",
                group=toga.Group.FILE,
                section=10,
                order=1
            )
            self.app.commands.add(general_cmd)
            
            # Individual option commands with proper keyboard shortcuts
            shortcuts = {
                'file': 'cmd+shift+o',
                'folder': 'cmd+shift+f', 
                'url': 'cmd+shift+u',
                'website': 'cmd+shift+w',
                'camera': 'cmd+shift+p',
                'audio': 'cmd+shift+a'
            }
            
            for i, option in enumerate(available_options):
                option_id = option['id']
                shortcut = shortcuts.get(option_id)
                
                # Create command
                cmd = toga.Command(
                    lambda widget, opt=option: self._on_add_option(opt),
                    text=option['title'],
                    group=toga.Group.FILE,
                    section=11,  # Separate section for individual options
                    order=i + 1,
                    shortcut=shortcut if option['available'] else None,
                    enabled=option['available']
                )
                
                self.app.commands.add(cmd)
                logger.debug(f"Added command: {option['title']} ({'enabled' if option['available'] else 'disabled'})")
            
            logger.info("Add commands initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize add commands: {e}")
    
    def _on_add_option(self, option: Dict[str, Any]):
        """Handle specific add option command"""
        try:
            option_id = option['id']
            logger.info(f"Add option command executed: {option_id}")
            
            # For specific options, show the Add Window and navigate directly to that option
            if hasattr(self.app, 'show_add_dialog'):
                self.app.show_add_dialog(option_id=option_id)
            else:
                logger.warning("Add dialog not available")
                
        except Exception as e:
            logger.error(f"Failed to execute add option {option.get('id', 'unknown')}: {e}")
    
    def _on_add_general(self, widget):
        """Handle general Add to Library command"""
        try:
            logger.info("General add to library command executed")
            
            # For general command, show the Add Window with main list
            if hasattr(self.app, 'show_add_dialog'):
                self.app.show_add_dialog()
            else:
                logger.warning("Add dialog not available")
                
        except Exception as e:
            logger.error(f"Failed to execute general add command: {e}")
    

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
            
            if hasattr(self.app, 'show_activity_monitor'):
                self.app.show_activity_monitor()
            else:
                logger.warning("Activity Monitor not available")
                
        except Exception as e:
            logger.error(f"Failed to open activity monitor: {e}")
    
    def _on_plans(self, widget):
        """Handle Plans command"""
        try:
            logger.debug("Plans command executed")
            
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
            
            if hasattr(self.app, 'show_processing'):
                self.app.show_processing()
            else:
                logger.warning("Processing window not available")
                
        except Exception as e:
            logger.error(f"Failed to open processing: {e}")
    
    def _on_preview(self, widget):
        """Handle Preview command"""
        try:
            logger.debug("Preview command executed")
            
            if hasattr(self.app, 'show_preview'):
                self.app.show_preview()
            else:
                logger.warning("Preview window not available")
                
        except Exception as e:
            logger.error(f"Failed to open preview: {e}")
    
    def add_to_app(self):
        """Add all registered commands to the app"""
        try:
            for cmd_id, command in self.registered_commands.items():
                logger.debug(f"Adding command to app: {cmd_id}")
                self.app.commands.add(command)
            
            logger.info(f"Added {len(self.registered_commands)} commands to app")
            
        except Exception as e:
            logger.error(f"Failed to add commands to app: {e}")
    
    def get_command(self, command_id: str) -> Optional[toga.Command]:
        """Get a registered command by ID"""
        return self.registered_commands.get(command_id) 