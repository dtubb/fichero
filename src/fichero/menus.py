"""
Cross-platform menu system for Fichero application
Follows Toga's abstraction philosophy: let Toga handle standard commands automatically
"""

import toga
import webbrowser
from .i18n import _
from .windows import SettingsWindow, AboutWindow


class MenuManager:
    """Manages menu commands for Fichero - focusing on app-specific functionality"""
    
    def __init__(self, app):
        """Initialize the menu manager with reference to main app"""
        self.app = app
        self.settings_window = None
        self.about_window = None
        
    def create_commands(self):
        """Create app-specific commands and customize standard ones"""
        commands = []
        
        # ===== CUSTOMIZE STANDARD COMMANDS =====
        # Toga automatically provides About, Exit, etc. We can customize them.
        
        # Override the default About command with our custom handler
        about_cmd = toga.Command(
            self._about_handler,
            text=_("menu_about"),
            group=toga.Group.APP,
            section=0,  # First section
            id=toga.Command.ABOUT  # Replace the default About
        )
        commands.append(about_cmd)
        
        # Add Preferences command (not installed by default)
        preferences_cmd = toga.Command(
            self._preferences_handler,
            text=_("menu_preferences"),
            group=toga.Group.APP,
            section=1,  # Different section creates separator after About
            id=toga.Command.PREFERENCES,
            shortcut=toga.Key.MOD_1 + ','
        )
        commands.append(preferences_cmd)
        
        # ===== APP-SPECIFIC COMMANDS =====
        
        # Website command in Help menu
        help_cmd = toga.Command(
            self._help_handler,
            text=_("menu_help_website"),
            group=toga.Group.HELP
        )
        commands.append(help_cmd)
        
        # Support command in Help menu  
        support_cmd = toga.Command(
            self._support_handler,
            text=_("menu_help_support"),
            group=toga.Group.HELP
        )
        commands.append(support_cmd)
        
        return commands
    
    def customize_standard_commands(self):
        """Customize any standard commands that Toga added automatically"""
        # This method can be called after startup to modify standard commands
        try:
            # Example: Customize the text of automatically-added commands
            if toga.Command.EXIT in self.app.commands:
                self.app.commands[toga.Command.EXIT].text = _("menu_quit")
                
        except Exception as e:
            print(f"Note: Could not customize standard commands: {e}")
    
    # ===== COMMAND HANDLERS =====
    
    def _about_handler(self, widget):
        """Handle about command - show custom about window"""
        print("ℹ️ About menu clicked - opening about window")
        
        if self.about_window is None:
            self.about_window = AboutWindow(self.app)
        
        self.about_window.show()
    
    def _preferences_handler(self, widget):
        """Handle preferences command - show settings window"""
        print("⚙️ Preferences menu clicked - opening settings window")
        
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self.app)
        
        self.settings_window.show()
    
    def _help_handler(self, widget):
        """Handle help command - open Fichero website"""
        print("🔘 Help menu clicked - opening website")
        webbrowser.open("https://www.tubb.ca/fichero/")
    
    def _support_handler(self, widget):
        """Handle support command - open support page"""
        print("🔘 Support menu clicked - opening support page")
        webbrowser.open("https://www.tubb.ca/fichero/support/") 