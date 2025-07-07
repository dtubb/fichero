"""
Cross-platform menu system for Fichero.
Follows Toga's abstraction philosophy: let Toga handle standard commands automatically
"""

import toga
import webbrowser
import sys
from pathlib import Path
from .i18n import _
from .windows import AboutWindow, ActivityMonitorWindow
from ..config.ui import create_plans_window, create_prompts_window, create_settings_window


class MenuManager:
    """Manages menu commands for Fichero"""
    
    def __init__(self, app):
        """Initialize the menu manager with reference to main app"""
        self.app = app
        self.settings_window = None
        self.about_window = None
        self.activity_monitor_window = None
        self.recent_documents_group = None
        self.recent_document_commands = []
        
    def create_commands(self):
        """Create app-specific commands and customize standard ones
        
        Toga automatically provides these commands for document-based apps:
        - NEW, OPEN, SAVE, SAVE_AS, SAVE_ALL (File menu) 
        - ABOUT, EXIT, VISIT_HOMEPAGE (App menu)
        
        Toga may or may not automatically provide Window menu commands:
        - Behavior seems inconsistent/platform-dependent
        - We check for existing commands and only add if missing
        
        Edit menu commands must be added manually if needed.
        
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
        #plans_editor_cmd = toga.Command(
        #    self._plans_editor_handler,
        #    text=_("menu_plans"),
        #    group=toga.Group.APP,
        #    section=3
        #)
        #commands.append(plans_editor_cmd)
        
        #prompts_editor_cmd = toga.Command(
        #    self._prompts_editor_handler,
        #    text=_("menu_prompts"), 
        #    group=toga.Group.APP,
        #    section=3
        #)
        #commands.append(prompts_editor_cmd)
        
        # Support command in Help menu  
        support_cmd = toga.Command(
            self._support_handler,
            text=_("menu_help_support"),
            group=toga.Group.HELP
        )
        commands.append(support_cmd)
        

        
        # ===== WINDOW MANAGEMENT COMMANDS =====
        
        # Check if Toga has already added Window commands before adding our own
        existing_window_commands = [cmd for cmd in self.app.commands if cmd.group == toga.Group.WINDOW]
        existing_window_texts = [cmd.text for cmd in existing_window_commands if hasattr(cmd, 'text')]
        
        print(f"🔍 Existing Window commands before adding ours: {existing_window_texts}")
        
        if sys.platform == 'darwin':
            print("🍎 macOS detected - adding standard Window commands:")
            # Only add Window commands if they don't already exist
            if 'Minimize' not in existing_window_texts:
                minimize_cmd = toga.Command(
                    self._minimize_window_handler,
                    text="Minimize",
                    group=toga.Group.WINDOW,
                    section=0,
                    shortcut=toga.Key.MOD_1 + 'm'
                )
                commands.append(minimize_cmd)
                print("✅ Added Minimize command")
            else:
                print("ℹ️ Minimize command already exists - skipping")
            
            if 'Zoom' not in existing_window_texts:
                zoom_cmd = toga.Command(
                    self._zoom_window_handler,
                    text="Zoom",
                    group=toga.Group.WINDOW,
                    section=0
                )
                commands.append(zoom_cmd)
                print("✅ Added Zoom command")
            else:
                print("ℹ️ Zoom command already exists - skipping")
            
            if 'Bring All to Front' not in existing_window_texts:
                bring_all_to_front_cmd = toga.Command(
                    self._bring_all_to_front_handler,
                    text="Bring All to Front",
                    group=toga.Group.WINDOW,
                    section=1
                )
                commands.append(bring_all_to_front_cmd)
                print("✅ Added Bring All to Front command")
            else:
                print("ℹ️ Bring All to Front command already exists - skipping")
                
            print(f"📊 Total commands to be added to app: {len(commands)}")
        else:
            print("🖥️ Non-macOS platform - skipping Window commands")
        
        # Custom Activity Monitor command
        activity_monitor_cmd = toga.Command(
            self._activity_monitor_handler,
            text="Activity Monitor",
            group=toga.Group.WINDOW,
            section=2,
            shortcut=toga.Key.MOD_1 + toga.Key.MOD_2 + 'a'
        )
        commands.append(activity_monitor_cmd)
        
        # ===== COMMANDS MENU =====
        
        # Document processing commands
        process_folder_cmd = toga.Command(
            self._process_folder_handler,
            text="Process Folder",
            group=toga.Group.COMMANDS,
            section=0,
            shortcut=toga.Key.MOD_1 + 'p'
        )
        commands.append(process_folder_cmd)
        
        stop_processing_cmd = toga.Command(
            self._stop_processing_handler,
            text="Stop Processing",
            group=toga.Group.COMMANDS,
            section=0,
            shortcut=toga.Key.MOD_1 + '.'
        )
        commands.append(stop_processing_cmd)
        
        # Document management commands
        reveal_in_finder_cmd = toga.Command(
            self._reveal_in_finder_handler,
            text="Reveal in Finder",
            group=toga.Group.COMMANDS,
            section=1,
            shortcut=toga.Key.MOD_1 + toga.Key.MOD_2 + 'r'
        )
        commands.append(reveal_in_finder_cmd)
        

        
        return commands
    
    def customize_standard_commands(self):
        """Customize text of automatically-added standard commands"""
        try:
            # Debug: Show what commands Toga has automatically added
            print("🔍 Debugging Toga's automatic commands:")
            print(f"   Total commands: {len(self.app.commands)}")
            
            # Check for standard command IDs
            standard_commands = [
                toga.Command.NEW,
                toga.Command.OPEN,
                toga.Command.SAVE,
                toga.Command.SAVE_AS,
                toga.Command.ABOUT,
                toga.Command.EXIT,
                toga.Command.VISIT_HOMEPAGE
            ]
            
            for cmd_id in standard_commands:
                try:
                    if cmd_id in self.app.commands:
                        cmd = self.app.commands[cmd_id]
                        # Handle commands that might not have text (like separators)
                        text = getattr(cmd, 'text', '[no-text]') if hasattr(cmd, 'text') else '[no-text]'
                        print(f"   ✅ {cmd_id}: '{text}' in group {cmd.group}")
                    else:
                        print(f"   ❌ {cmd_id}: Not found")
                except Exception as e:
                    print(f"   ⚠️ Error checking {cmd_id}: {e}")
            
            # Check Window menu commands specifically
            try:
                window_commands = [cmd for cmd in self.app.commands if cmd.group == toga.Group.WINDOW]
                print(f"   Window menu commands: {len(window_commands)}")
                for cmd in window_commands:
                    try:
                        # Skip separators which don't have text
                        if hasattr(cmd, 'text'):
                            print(f"      - '{cmd.text}' (id: {getattr(cmd, 'id', 'no-id')})")
                        else:
                            print(f"      - [Separator] (id: {getattr(cmd, 'id', 'no-id')})")
                    except Exception as e:
                        print(f"      - [Error reading command]: {e}")
            except Exception as e:
                print(f"   ⚠️ Error listing Window commands: {e}")
            
            # Customize the text of the Exit command (safely)
            try:
                if toga.Command.EXIT in self.app.commands:
                    exit_cmd = self.app.commands[toga.Command.EXIT]
                    if hasattr(exit_cmd, 'text'):
                        exit_cmd.text = _("menu_quit")
            except Exception as e:
                print(f"⚠️ Error customizing Exit command: {e}")
            
            # On macOS, remove "Save All" as it's not standard for document apps
            try:
                if sys.platform == 'darwin' and toga.Command.SAVE_ALL in self.app.commands:
                    save_all_cmd = self.app.commands[toga.Command.SAVE_ALL]
                    if hasattr(save_all_cmd, 'text'):  # Only remove if it's actually a command
                        self.app.commands.discard(save_all_cmd)
            except Exception as e:
                print(f"⚠️ Error removing Save All command: {e}")
                
        except Exception as e:
            print(f"⚠️ Error in customize_standard_commands: {e}")
            import traceback
            traceback.print_exc()
    
    def check_for_missing_window_commands(self):
        """Check if standard macOS Window commands are present (we add them manually)"""
        try:
            if sys.platform != 'darwin':
                print("ℹ️ Non-macOS platform - Window menu commands not added")
                return
                
            print("\n🔍 DETAILED WINDOW MENU ANALYSIS:")
            
            # Check if we have the standard Window commands we added manually
            window_commands = [cmd for cmd in self.app.commands if cmd.group == toga.Group.WINDOW]
            print(f"📊 Total Window menu items: {len(window_commands)}")
            
            # Detailed analysis of each command
            print("📋 All Window menu items:")
            for i, cmd in enumerate(window_commands):
                try:
                    if hasattr(cmd, 'text'):
                        shortcut = getattr(cmd, 'shortcut', 'No shortcut')
                        section = getattr(cmd, 'section', 'No section')
                        enabled = getattr(cmd, 'enabled', 'Unknown')
                        print(f"   {i+1}. '{cmd.text}' - Section: {section}, Shortcut: {shortcut}, Enabled: {enabled}")
                    else:
                        print(f"   {i+1}. [Separator or special item]")
                except Exception as e:
                    print(f"   {i+1}. [Error reading item]: {e}")
            
            # Check for expected commands
            standard_window_commands = ['Minimize', 'Zoom', 'Bring All to Front']
            existing_texts = [cmd.text for cmd in window_commands if hasattr(cmd, 'text')]
            
            print(f"\n📝 Expected standard commands: {standard_window_commands}")
            print(f"✅ Commands found: {existing_texts}")
            
            missing_commands = [cmd for cmd in standard_window_commands if cmd not in existing_texts]
            if missing_commands:
                print(f"❌ MISSING commands: {missing_commands}")
                print("   → These should be added to match macOS standards")
            else:
                print("✅ All standard macOS Window commands are present")
            
            # Check for unexpected commands
            unexpected_commands = [cmd for cmd in existing_texts if cmd not in standard_window_commands and cmd != 'Activity Monitor']
            if unexpected_commands:
                print(f"❓ Unexpected commands: {unexpected_commands}")
                
        except Exception as e:
            print(f"⚠️ Error in check_for_missing_window_commands: {e}")
            import traceback
            traceback.print_exc()
    
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
    

    
    # ===== DIALOG HELPERS =====
    
    def _show_info_dialog(self, title: str, message: str):
        """Show an info dialog"""
        try:
            # Use async/await pattern for Toga dialogs
            import asyncio
            import toga
            async def show_dialog():
                await self.app.dialog(toga.InfoDialog(title, message))
            asyncio.create_task(show_dialog())
        except Exception as e:
            print(f"Failed to show info dialog: {e}")
    
    def _show_error_dialog(self, title: str, message: str):
        """Show an error dialog"""
        try:
            # Use async/await pattern for Toga dialogs
            import asyncio
            import toga
            async def show_dialog():
                await self.app.dialog(toga.ErrorDialog(title, message))
            asyncio.create_task(show_dialog())
        except Exception as e:
            print(f"Failed to show error dialog: {e}")
    

    
    def _activity_monitor_handler(self, widget):
        """Handle activity monitor command - show global activity monitor window"""
        print("📊 Activity Monitor menu clicked - managing activity monitor window")
        
        try:
            # Check if window exists and is visible
            if self.activity_monitor_window is not None:
                if self.activity_monitor_window.is_visible:
                    # Window is visible, hide it
                    print("🔄 Hiding existing Activity Monitor window")
                    self.activity_monitor_window.hide()
                    return
                else:
                    # Window exists but not visible, show it
                    print("🔄 Showing existing Activity Monitor window")
                    self.activity_monitor_window.show()
                    return
            
            # No window exists, create new one
            print("🔄 Creating new Activity Monitor window")
            self.activity_monitor_window = ActivityMonitorWindow(self.app)
            self.activity_monitor_window.show()
            print("✅ Activity Monitor window opened successfully")
            
        except Exception as e:
            print(f"❌ Failed to manage activity monitor: {e}")
            import traceback
            traceback.print_exc()
            
            # Use sync error dialog since we're not in async context
            try:
                import asyncio
                import toga
                error_message = str(e)  # Capture the error message
                async def show_error():
                    await self.app.dialog(toga.ErrorDialog("Activity Monitor Error", f"Failed to manage Activity Monitor: {error_message}"))
                asyncio.create_task(show_error())
            except Exception as dialog_error:
                print(f"❌ Also failed to show error dialog: {dialog_error}")
    
    # ===== WINDOW MANAGEMENT HANDLERS =====
    
    def _minimize_window_handler(self, widget):
        """Handle minimize window command"""
        print("🔹 Minimize command triggered")
        try:
            if self.app.current_window:
                print(f"   Current window: {self.app.current_window}")
                print(f"   Window type: {type(self.app.current_window)}")
                
                # Try multiple approaches for minimizing on macOS
                if hasattr(self.app.current_window, 'minimize'):
                    print("   Using window.minimize() method")
                    self.app.current_window.minimize()
                elif hasattr(self.app.current_window, 'state'):
                    print("   Using window.state = MINIMIZED")
                    import toga
                    self.app.current_window.state = toga.WindowState.MINIMIZED
                else:
                    print("⚠️ Window minimize not supported - no minimize() method or state property")
                    
                print("✅ Minimize command completed")
            else:
                print("⚠️ No current window to minimize")
        except Exception as e:
            print(f"❌ Failed to minimize window: {e}")
            import traceback
            traceback.print_exc()
    
    def _zoom_window_handler(self, widget):
        """Handle zoom/maximize window command"""
        print("🔹 Zoom command triggered")
        try:
            if self.app.current_window:
                print(f"   Current window: {self.app.current_window}")
                print(f"   Window type: {type(self.app.current_window)}")
                
                # Toggle between maximized and normal state
                import toga
                if hasattr(self.app.current_window, 'state'):
                    current_state = self.app.current_window.state
                    print(f"   Current state: {current_state}")
                    
                    if current_state == toga.WindowState.MAXIMIZED:
                        print("   Changing to NORMAL state")
                        self.app.current_window.state = toga.WindowState.NORMAL
                    else:
                        print("   Changing to MAXIMIZED state")
                        self.app.current_window.state = toga.WindowState.MAXIMIZED
                        
                    print("✅ Zoom command completed")
                else:
                    print("⚠️ Window zoom not supported - no state property")
            else:
                print("⚠️ No current window to zoom")
        except Exception as e:
            print(f"❌ Failed to zoom window: {e}")
            import traceback
            traceback.print_exc()
    
    def _bring_all_to_front_handler(self, widget):
        """Handle bring all windows to front command"""
        print("🔹 Bring All to Front command triggered")
        try:
            print(f"   Total app windows: {len(self.app.windows)}")
            brought_count = 0
            
            # Bring all app windows to front
            for i, window in enumerate(self.app.windows):
                print(f"   Window {i+1}: {window} (closed: {window.closed})")
                if not window.closed and hasattr(window, 'show'):
                    window.show()  # This should bring window to front
                    brought_count += 1
                    
            print(f"✅ Brought {brought_count} windows to front")
        except Exception as e:
            print(f"❌ Failed to bring windows to front: {e}")
            import traceback
            traceback.print_exc()
    
    # ===== COMMANDS MENU HANDLERS =====
    
    def _process_folder_handler(self, widget):
        """Handle process folder command - delegate to current document"""
        print("🚀 Process Folder command triggered")
        try:
            # Get the current document window
            current_window = self.app.current_window
            if hasattr(current_window, 'process_handler'):
                # Trigger the process handler if not currently processing
                if not hasattr(current_window, 'current_task_ids') or not current_window.current_task_ids:
                    import asyncio
                    asyncio.create_task(current_window.process_handler(widget))
                else:
                    print("⚠️ Document is already processing")
            else:
                print("⚠️ No active document window to process folder")
        except Exception as e:
            print(f"❌ Failed to process folder: {e}")
    
    def _stop_processing_handler(self, widget):
        """Handle stop processing command - open activity monitor for stop functionality"""
        print("🛑 Stop Processing command triggered")
        try:
            # Open activity monitor where stop functionality is available
            if hasattr(self, 'activity_monitor_window'):
                if not self.activity_monitor_window.is_visible:
                    self.activity_monitor_window.show()
                else:
                    # Bring to front if already visible
                    self.activity_monitor_window.display.window.show()
                print("✅ Activity monitor opened for stop functionality")
            else:
                # Create and show activity monitor
                self.activity_monitor_window = ActivityMonitorWindow(self.app)
                self.activity_monitor_window.show()
                print("✅ Activity monitor created and opened for stop functionality")
        except Exception as e:
            print(f"❌ Failed to open activity monitor: {e}")
    
    def _reveal_in_finder_handler(self, widget):
        """Handle reveal in finder command"""
        print("📁 Reveal in Finder command triggered")
        try:
            # Get the current document window
            current_window = self.app.current_window
            if hasattr(current_window, '_document') and hasattr(current_window._document, 'selected_folder'):
                selected_folder = current_window._document.selected_folder
                if selected_folder and Path(selected_folder).exists():
                    import subprocess
                    subprocess.run(['open', '-R', str(selected_folder)])
                else:
                    self._show_info_dialog("No Folder", "No folder selected or folder doesn't exist.")
            else:
                self._show_info_dialog("No Document", "No active document to reveal folder for.")
        except Exception as e:
            print(f"❌ Failed to reveal in finder: {e}")
            self._show_error_dialog("Reveal Error", f"Failed to reveal in Finder: {e}")

 