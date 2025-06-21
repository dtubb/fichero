"""
Cross-platform menu system for Fichero.
Follows Toga's abstraction philosophy: let Toga handle standard commands automatically
"""

import toga
import webbrowser
import sys
from pathlib import Path
from ..utils import _
from .windows import AboutWindow
from ..config.ui import create_plans_window, create_prompts_window, create_settings_window


class MenuManager:
    """Manages menu commands for Fichero"""
    
    def __init__(self, app):
        """Initialize the menu manager with reference to main app"""
        self.app = app
        self.settings_window = None
        self.about_window = None
        self.recent_documents_group = None
        self.recent_document_commands = []
        
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
        
        # Create Open Recent submenu in File menu
        self.recent_documents_group = toga.Group(_("menu_open_recent"), parent=toga.Group.FILE, order=1)
        
        # Initially populate with recent documents
        self._update_recent_documents_menu()
        
        # Add recent document commands to the commands list
        commands.extend(self.recent_document_commands)
        
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
        
        # Configuration editors in App menu (after preferences)
        plans_editor_cmd = toga.Command(
            self._plans_editor_handler,
            text=_("menu_plans"),
            group=toga.Group.APP,
            section=3
        )
        commands.append(plans_editor_cmd)
        
        prompts_editor_cmd = toga.Command(
            self._prompts_editor_handler,
            text=_("menu_prompts"), 
            group=toga.Group.APP,
            section=3
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
        """Handle preferences command - show integrated settings window"""
        print("⚙️ Preferences menu clicked - opening integrated settings window")
        
        if self.settings_window is None:
            self.settings_window = create_settings_window(self.app)
        
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
    
    def _plans_editor_handler(self, widget):
        """Handle plans command"""
        print("📋 Plans menu clicked - opening plans library")
        try:
            plans_library = create_plans_window(self.app)
            plans_library.show()
        except Exception as e:
            print(f"❌ Failed to open plans library: {e}")
    
    def _prompts_editor_handler(self, widget):
        """Handle prompts command"""
        print("📄 Prompts menu clicked - opening prompts library")
        try:
            prompts_library = create_prompts_window(self.app)
            prompts_library.show()
        except Exception as e:
            print(f"❌ Failed to open prompts library: {e}")
    
    # ===== DOCUMENT OPERATIONS =====
    # Note: Document operations (NEW, OPEN, SAVE, etc.) are handled automatically
    # by Toga through the document system defined in FicheroDocument
    
    # ===== OPEN RECENT MENU MANAGEMENT =====
    
    def _update_recent_documents_menu(self):
        """Update the Open Recent submenu with current recent documents"""
        try:
            # Clear existing recent document commands
            for cmd in self.recent_document_commands:
                if cmd in self.app.commands:
                    self.app.commands.discard(cmd)
            self.recent_document_commands.clear()
            
            # Get recent documents directly from document tracker
            recent_documents = self.app.document_tracker.get_recent_documents()
            
            if not recent_documents:
                # Add "No Recent Documents" placeholder
                no_recent_cmd = toga.Command(
                    lambda widget: None,  # Do nothing
                    text=_("menu_no_recent_documents"),
                    group=self.recent_documents_group,
                    enabled=False
                )
                self.recent_document_commands.append(no_recent_cmd)
                self.app.commands.add(no_recent_cmd)
            else:
                # Add commands for each recent document
                for i, doc_path in enumerate(recent_documents):
                    try:
                        doc_path_obj = Path(doc_path)
                        display_name = doc_path_obj.stem
                        
                        # Create command for this document with proper closure
                        def create_handler(document_path):
                            return lambda widget: self._open_recent_document(document_path)
                        
                        recent_cmd = toga.Command(
                            create_handler(doc_path),
                            text=f"{display_name}",
                            group=self.recent_documents_group,
                            order=i
                        )
                        self.recent_document_commands.append(recent_cmd)
                        self.app.commands.add(recent_cmd)
                        
                    except Exception as e:
                        print(f"⚠️ Failed to add recent document {doc_path}: {e}")
                
                # Add separator and "Clear Recent Documents" command
                if recent_documents:
                    clear_recent_cmd = toga.Command(
                        self._clear_recent_documents,
                        text=_("menu_clear_recent_documents"),
                        group=self.recent_documents_group,
                        order=len(recent_documents) + 1
                    )
                    self.recent_document_commands.append(clear_recent_cmd)
                    self.app.commands.add(clear_recent_cmd)
            
            print(f"📋 Updated Open Recent menu with {len(recent_documents)} documents")
            
        except Exception as e:
            print(f"⚠️ Failed to update recent documents menu: {e}")
    
    def _open_recent_document(self, document_path: str):
        """Handle opening a recent document"""
        print(f"📂 Opening recent document: {document_path}")
        try:
            # Use the document tracker directly
            self.app.document_tracker.open_recent_document(document_path)
            # Menu will be updated automatically by the document tracker
        except Exception as e:
            print(f"❌ Failed to open recent document: {e}")
    
    def _clear_recent_documents(self, widget):
        """Handle clearing recent documents list"""
        print("🗑️ Clearing recent documents list")
        try:
            # Use the document tracker to clear recent documents
            self.app.document_tracker.clear_recent_documents()
            print("✅ Recent documents cleared")
        except Exception as e:
            print(f"❌ Failed to clear recent documents: {e}")
    
    def update_recent_documents(self):
        """Public method to update recent documents menu - call this when a document is opened/saved"""
        self._update_recent_documents_menu() 