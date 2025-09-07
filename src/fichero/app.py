"""
Fichero GUI Application

Main entry point for the Fichero GUI application.
Uses Toga for cross-platform GUI framework.
"""

import toga
import sys
import os
import logging
from pathlib import Path
import gettext
import locale

# Install basic gettext for now - proper translation setup happens after Toga app creation
gettext.install('fichero')

from fichero.menus import MenuManager
# Document model removed - using library approach instead
from fichero.core.app_initializer import initialize_gui_app
from fichero.core.error_handler import create_gui_error_handler
from fichero.windows.main.window_view_manager import WindowViewManager, WindowType
from fichero import __version__
from fichero.library.library_manager import LibraryManager
from fichero.windows.main.services.library_service import LibraryService

logger = logging.getLogger(__name__)


class FicheroApp(toga.App):
    """Thin wrapper GUI application - delegates all business logic to shared systems"""
    
    # Application metadata
    formal_name = "Fichero"
    app_id = "ca.tubb.fichero"
    description = "Multi-Step Document Processing"
    author = "Daniel Tubb"
    version = __version__
    home_page = "https://www.tubb.ca/fichero/"
    
    def _setup_translations_early(self):
        """Setup translations immediately after app creation, before UI imports"""
        try:
            from fichero.ui.i18n import setup_translations
            if setup_translations(self):
                print("✅ Translations loaded successfully")
            else:
                print("⚠️ Using fallback translations")
        except Exception as e:
            print(f"❌ Translation setup failed: {e}")
            # Ensure fallback is installed
            gettext.install('fichero')
    
    def startup(self):
        """Initialize the app - delegates to shared initialization system"""
        # Check if running as bundled GUI app (minimize console output)
        is_gui_only = self._is_gui_only_mode()
        
        if not is_gui_only:
            print("🚀 Fichero GUI starting up...")
        logger.info("Fichero GUI starting up")
        
        # Setup translations immediately after app creation, before importing UI modules
        self._setup_translations_early()
        
        # Import UI modules after translations are set up  
        
        # Set app icon first
        try:
            self.icon = toga.Icon("resources/icons/fichero.png")
            if not is_gui_only:
                print("✅ App icon loaded")
            logger.info("App icon loaded")
        except Exception as e:
            if not is_gui_only:
                print(f"⚠️ Warning: Could not load app icon: {e}")
            logger.warning(f"Could not load app icon: {e}")
        
        # Initialize components immediately
        try:
            self.components, self.initializer = initialize_gui_app(app_context=self)
            
            # Extract initialized components (same as CLI gets, plus GUI-specific)
            # Set director first since document system depends on it
            self.director = self.components['director']
            self.settings = self.components['settings']
            # Document system components removed - using library approach
            
            # Initialize library manager
            self.library_manager = LibraryManager(self)
            logger.info("Library manager initialized at app level")
            
            # Initialize library service
            self.library_service = LibraryService(self.library_manager)
            logger.info("Library service initialized at app level")            # Initialize unified window/view manager
            self.window_view_manager = WindowViewManager(self)
            
            # Detect platform once and set as app property
            self.is_mobile = self._detect_platform_simple()
            logger.info(f"Platform detection complete: is_mobile={self.is_mobile}")
            
            if not is_gui_only:
                print("✅ Fichero components initialized")
            logger.info("Fichero components initialized")
            
        except Exception as e:
            error_msg = f"Failed to initialize Fichero: {e}"
            logger.error(error_msg)
            
            if not is_gui_only:
                print(f"❌ {error_msg}")
                print("Cannot continue without core services.")
                import traceback
                traceback.print_exc()
                print("The application will now exit.")
            
            # For iOS, don't exit - create a minimal app instead
            if is_gui_only:
                logger.warning("Running in GUI-only mode, creating minimal app without core services")
                self.director = None
                self.settings = None
                self.components = {}
            else:
                # Exit cleanly without showing dialog during startup
                self.exit()
                return
        
        # Initialize GUI-specific systems
        try:
            self._setup_gui_interface()
            
            if not is_gui_only:
                print("✨ Fichero GUI ready!")
            logger.info("Fichero GUI ready")
        except Exception as e:
            error_msg = f"GUI interface setup failed: {e}"
            logger.error(error_msg)
            
            if not is_gui_only:
                print(f"❌ {error_msg}")
                print("Cannot continue without GUI interface.")
                import traceback
                traceback.print_exc()
                print("The application will now exit.")
            
            # Exit cleanly
            self.exit()
            return
    
    def _is_gui_only_mode(self):
        """Detect if running as bundled GUI app (minimize console output)"""
        # Check if running as bundled app
        is_bundled = getattr(sys, 'frozen', False) or hasattr(sys, '_MEIPASS')
        
        # Check if stdout is not connected to terminal (GUI app)
        is_gui_app = not sys.stdout.isatty() if hasattr(sys.stdout, 'isatty') else True
        
        # Check if running via briefcase (look for app bundle structure)
        is_briefcase_app = 'Contents/MacOS' in str(sys.executable) if sys.executable else False
        
        return is_bundled or is_briefcase_app or (is_gui_app and not os.environ.get('TERM'))

    def _detect_platform_simple(self):
        """Simple platform detection using environment variables and Toga"""
        try:
            # First check for environment variable override (for testing)
            import os
            env_mobile = os.environ.get('FORCE_MOBILE_UI')
            if env_mobile is not None:
                is_mobile = env_mobile.lower() in ('true', '1', 'yes', 'on')
                logger.info(f"Using environment variable FORCE_MOBILE_UI: {is_mobile}")
                return is_mobile
            
            # Use Toga's platform detection
            import toga.platform
            current_platform = toga.platform.current_platform
            is_mobile = current_platform in ['iOS', 'android']
            
            logger.info(f"Platform detection: {current_platform} -> mobile={is_mobile}")
            return is_mobile
                
        except Exception as e:
            logger.error(f"Platform detection failed: {e}, assuming desktop")
            return False

    def about(self):
        """Override Toga's default About dialog with custom About window"""
        self.show_about()

    def _setup_gui_interface(self):
        """Set up GUI-specific interface elements"""
        print("🔍 Starting _setup_gui_interface...")
        is_gui_only = self._is_gui_only_mode()
        
        try:
            # Check if this is a desktop platform
            import toga.platform
            current_platform = toga.platform.current_platform
            is_desktop = current_platform not in ['iOS', 'android']
            
            if is_desktop:
                # Desktop only: Initialize command manager for native menus/toolbars
                from fichero.windows.main.command_manager import CommandManagerRefactored
                self.command_manager = CommandManagerRefactored(self)
                self.command_manager.add_to_app()
                
                # Initialize menu system (only handles custom overrides)
                self.menu_manager = MenuManager(self)
                self.menu_manager.customize_standard_commands()
                
                # Customize standard commands (remove unimplemented ones)
                self.menu_manager.customize_standard_commands()
            else:
                # Mobile: Skip command manager and menu system (use mobile toolbar only)
                self.command_manager = None
                self.menu_manager = None
            
            # Create main window for collection library view (only once)
            print("🔍 Creating MainWindow...")
            from fichero.windows.main import MainWindow
            self.main_window_wrapper = MainWindow(self)
            print("✅ MainWindow created successfully")
            
            if not is_gui_only:
                print("✅ Main window configured for collection library")
            logger.info("Main window configured for collection library")
            
            # Show the main window on startup (this creates the Toga window)
            print("🔍 About to show main window...")
            try:
                self.main_window_wrapper.show()
                print("✅ Main window shown successfully")
            except Exception as e:
                print(f"❌ Failed to show main window: {e}")
                import traceback
                traceback.print_exc()
                raise
            
            # Set the Toga main_window property to the actual Toga window
            self.main_window = self.main_window_wrapper.window
            
        except Exception as e:
            error_msg = f"GUI interface setup failed: {e}"
            logger.error(error_msg)
            if not is_gui_only:
                print(f"❌ Error: {error_msg}")
                import traceback
                traceback.print_exc()
            # Exit the app if GUI setup fails
            self.exit()

    # Activity Monitor Management
    def show_activity_monitor(self):
        """Show the activity monitor window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.show_window_or_view(WindowType.ACTIVITY_MONITOR)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to show activity monitor: {e}")
            return False

    def close_activity_monitor(self):
        """Close the activity monitor window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.close_window_or_view(WindowType.ACTIVITY_MONITOR)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to close activity monitor: {e}")
            return False

    def show_settings(self):
        """Show the settings window or view"""
        try:
            logger.info("=== show_settings() called ===")
            logger.info(f"Has window_view_manager: {hasattr(self, 'window_view_manager')}")
            if hasattr(self, 'window_view_manager'):
                logger.info(f"WindowViewManager is_mobile: {self.window_view_manager.is_mobile}")
                logger.info(f"Mobile view manager set: {self.window_view_manager.mobile_view_manager is not None}")
            
            return self.window_view_manager.show_window_or_view(WindowType.SETTINGS)
        except Exception as e:
            logger.error(f"Failed to show settings: {e}")
            return False

    def close_settings(self):
        """Close the settings window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.close_window_or_view(WindowType.SETTINGS)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to close settings: {e}")
            return False

    def show_plans(self):
        """Show the plans window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.show_window_or_view(WindowType.PLANS)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to show plans: {e}")
            return False

    def close_plans(self):
        """Close the plans window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.close_window_or_view(WindowType.PLANS)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to close plans: {e}")
            return False

    def show_prompts(self):
        """Show the prompts window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.show_window_or_view(WindowType.PROMPTS)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to show prompts: {e}")
            return False

    def close_prompts(self):
        """Close the prompts window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.close_window_or_view(WindowType.PROMPTS)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to close prompts: {e}")
            return False

    def show_processing(self):
        """Show the processing window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.show_window_or_view(WindowType.PROCESSING)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to show processing: {e}")
            return False

    def close_processing(self):
        """Close the processing window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.close_window_or_view(WindowType.PROCESSING)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to close processing: {e}")
            return False

    def show_preview(self, file_path=None, **kwargs):
        """Show the preview window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.show_window_or_view(
                    WindowType.PREVIEW, 
                    file_path=file_path,
                    **kwargs
                )
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to show preview: {e}")
            return False

    def close_preview(self):
        """Close the preview window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.close_window_or_view(WindowType.PREVIEW)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to close preview: {e}")
            return False

    def show_about(self):
        """Show the about window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.show_window_or_view(WindowType.ABOUT)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to show about: {e}")
            return False

    def close_about(self):
        """Close the about window - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                return self.window_view_manager.close_window_or_view(WindowType.ABOUT)
            else:
                logger.error("Window/view manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Failed to close about: {e}")
            return False

    def close_all_windows(self):
        """Close all secondary windows - delegates to unified manager"""
        try:
            if hasattr(self, 'window_view_manager'):
                self.window_view_manager.close_all_windows_or_views()
                logger.info("All secondary windows/views closed")
            else:
                logger.error("Window/view manager not initialized")
        except Exception as e:
            logger.error(f"Failed to close all windows: {e}")

    # Document operations removed - using library approach instead

    def finalize(self):
        """Clean up when app closes - delegates to shared cleanup system"""
        is_gui_only = self._is_gui_only_mode()
        if not is_gui_only:
            print("🔄 Fichero GUI closing...")
        logger.info("Fichero GUI closing")
        
        try:
            # Close all secondary windows first
            self.close_all_windows()
            
            # Use shared cleanup wrapper (same pattern as CLI)
            if hasattr(self, 'initializer') and self.initializer:
                self.initializer.cleanup()
        except Exception as e:
            error_msg = f"Error during cleanup: {e}"
            logger.error(error_msg)
            is_gui_only = self._is_gui_only_mode()
            if not is_gui_only:
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()


def main():
    """Main entry point - delegates to shared error handling"""
    error_handler = create_gui_error_handler()
    
    def run_app():
        app = FicheroApp(
            formal_name="Fichero",
            app_id="ca.tubb.fichero"
        )
        app.main_loop()
    
    wrapped_app = error_handler.wrap_main_function(run_app, "GUI application")
    wrapped_app()


if __name__ == "__main__":
    main() 