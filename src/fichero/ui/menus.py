"""
Cross-platform menu system for Fichero.
Follows Toga's abstraction philosophy: let Toga handle standard commands automatically
"""

import toga
import webbrowser
import sys
from pathlib import Path
from ..utils import _
from .windows import AboutWindow, AppSettingsWindow
from .windows.config_windows import create_plans_editor_window, create_prompts_editor_window


class MenuManager:
    """Manages menu commands for Fichero"""
    
    def __init__(self, app):
        """Initialize the menu manager with reference to main app"""
        self.app = app
        self.settings_window = None
        self.about_window = None
        
    def create_commands(self):
        """Create app-specific commands and customize standard ones
        
        Toga automatically provides these commands for document-based apps:
        - NEW, OPEN, SAVE, SAVE_AS, SAVE_ALL (File menu) 
        - ABOUT, EXIT, VISIT_HOMEPAGE (App menu)
        - Standard Edit commands on macOS (Undo, Redo, Cut, Copy, Paste)
        
        Only override standard commands when we need custom behavior.
        """
        commands = []
        
        # ===== OVERRIDE STANDARD COMMANDS =====
        
        # Override About command with custom window
        about_cmd = toga.Command(
            self._about_handler,
            text=_("menu_about"),
            group=toga.Group.APP,
            section=0,
            id=toga.Command.ABOUT
        )
        commands.append(about_cmd)
        
        # Override Visit Homepage with our URL
        visit_homepage_cmd = toga.Command(
            self._help_handler,
            text=_("menu_help_website"),
            group=toga.Group.HELP,
            id=toga.Command.VISIT_HOMEPAGE
        )
        commands.append(visit_homepage_cmd)
        
        # ===== ADD NON-STANDARD COMMANDS =====
        
        # Preferences (create manually to control section placement)
        preferences_cmd = toga.Command(
            self._preferences_handler,
            text=_("menu_preferences"),
            group=toga.Group.APP,
            section=1,
            shortcut=toga.Key.MOD_1 + ','
        )
        commands.append(preferences_cmd)
        
        # ===== APP-SPECIFIC COMMANDS =====
        
        # Global configuration editors in App menu (after preferences)
        plans_editor_cmd = toga.Command(
            self._plans_editor_handler,
            text="Plans Editor",
            group=toga.Group.APP,
            section=3,
            shortcut=toga.Key.MOD_1 + 'p'
        )
        commands.append(plans_editor_cmd)
        
        prompts_editor_cmd = toga.Command(
            self._prompts_editor_handler,
            text="Prompts Editor", 
            group=toga.Group.APP,
            section=3,
            shortcut=toga.Key.MOD_1 + 'r'
        )
        commands.append(prompts_editor_cmd)
        

        
        # Support command in Help menu  
        support_cmd = toga.Command(
            self._support_handler,
            text=_("menu_help_support"),
            group=toga.Group.HELP
        )
        commands.append(support_cmd)
        
        return commands
    
    def customize_standard_commands(self):
        """Customize text of automatically-added standard commands"""
        try:
            # Customize the text of the Exit command
            if toga.Command.EXIT in self.app.commands:
                self.app.commands[toga.Command.EXIT].text = _("menu_quit")
            
            # On macOS, remove "Save All" as it's not standard for document apps
            if sys.platform == 'darwin' and toga.Command.SAVE_ALL in self.app.commands:
                save_all_cmd = self.app.commands[toga.Command.SAVE_ALL]
                self.app.commands.discard(save_all_cmd)
                print("🚫 Removed non-standard 'Save All' command on macOS")
                
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
        """Handle preferences command - show schema-driven settings window"""
        print("⚙️ Preferences menu clicked - opening settings window")
        
        if self.settings_window is None:
            self.settings_window = AppSettingsWindow(self.app)
        
        self.settings_window.show()
    
    def _help_handler(self, widget):
        """Handle help command - open Fichero website"""
        print("🔘 Help menu clicked - opening website")
        webbrowser.open("https://www.tubb.ca/fichero/")
    
    def _support_handler(self, widget):
        """Handle support command - open support page"""
        print("🔘 Support menu clicked - opening support page")
        webbrowser.open("https://www.tubb.ca/fichero/support/")
    
    # ===== APP-SPECIFIC CONFIGURATION HANDLERS =====
    # Note: Document operations (NEW, OPEN, SAVE, etc.) are handled automatically
    # by Toga through the document system defined in FicheroDocument
    
    def _plans_editor_handler(self, widget):
        """Handle plans editor command"""
        print("📋 Plans Editor menu clicked")
        try:
            plans_editor = create_plans_editor_window(self.app)
            plans_editor.show()
        except Exception as e:
            print(f"❌ Failed to open plans editor: {e}")
    
    def _prompts_editor_handler(self, widget):
        """Handle prompts editor command"""
        print("📄 Prompts Editor menu clicked")
        try:
            self._show_prompts_editor_selection()
        except Exception as e:
            print(f"❌ Failed to open prompts editor: {e}")
    
    def _show_prompts_editor_selection(self):
        """Show a selection dialog for which prompts editor to open"""
        prompts_dir = self.app.paths.app / "resources" / "prompts"
        
        if not prompts_dir.exists():
            print(f"❌ Prompts directory not found: {prompts_dir}")
            return
        
        # Find all JSONL config files
        config_files = list(prompts_dir.glob("*.jsonl"))
        
        if not config_files:
            print(f"❌ No JSONL config files found in {prompts_dir}")
            return
        
        if len(config_files) == 1:
            # If only one config file, open it directly
            editor = create_prompts_editor_window(self.app, config_files[0])
            editor.show()
            print(f"📝 Opening {config_files[0].name}")
        else:
            # Multiple configs - for now, default to the English catalogue config
            # TODO: In the future, show a selection dialog
            default_config = prompts_dir / "catalogue_folder_local_config_english.jsonl"
            if default_config.exists():
                editor = create_prompts_editor_window(self.app, default_config)
                editor.show()
                print(f"📝 Opening default config: {default_config.name}")
            else:
                # Fallback to first available config
                editor = create_prompts_editor_window(self.app, config_files[0])
                editor.show()
                print(f"📝 Opening {config_files[0].name}")
                print(f"💡 Found {len(config_files)} configs. Future versions will show selection dialog.") 