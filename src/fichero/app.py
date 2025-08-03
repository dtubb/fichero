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

# Setup gettext translations properly
def setup_translations():
    """Setup gettext translations with our custom locale directory."""
    try:
        # Detect system language using non-deprecated methods
        try:
            # Try to get the current locale
            current_locale = locale.getlocale()
            if current_locale and current_locale[0]:
                lang = current_locale[0].split('_')[0].lower()
            else:
                # Fallback to environment variables
                import os
                lang_env = os.environ.get('LANG', '') or os.environ.get('LC_ALL', '')
                if lang_env:
                    lang = lang_env.split('_')[0].split('.')[0].lower()
                else:
                    lang = 'en'
        except:
            lang = 'en'
        
        # Validate language
        if lang not in ['en', 'es', 'fr']:
            lang = 'en'
        
        # Use Toga's app path
        app_root = toga.App.app.paths.app
        locale_dir = app_root / "resources" / "locale"
        print(f"🔍 Looking for translations in: {locale_dir}")
        
        if locale_dir.exists() and (locale_dir / lang / "LC_MESSAGES" / "fichero.mo").exists():
            # Load and install translations
            translation = gettext.translation('fichero', str(locale_dir), [lang])
            translation.install()
            print(f"✅ Translations loaded for language: {lang} from {locale_dir}")
        else:
            # No translations available
            gettext.install('fichero')
            print(f"⚠️ No translation files found, using English")
            
    except Exception as e:
        print(f"❌ Failed to setup translations: {e}")
        # No translations available
        gettext.install('fichero')

# Don't setup translations during import - wait for app creation
gettext.install('fichero')  # Install basic gettext for now

from fichero.config.core.settings import get_app_settings
from fichero.ui import MenuManager
# Document model removed - using library approach instead
from fichero.core.app_initializer import initialize_gui_app
from fichero.core.error_handler import create_gui_error_handler
from fichero import __version__

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
    
    def startup(self):
        """Initialize the app - delegates to shared initialization system"""
        # Check if running as bundled GUI app (minimize console output)
        is_gui_only = self._is_gui_only_mode()
        
        if not is_gui_only:
            print("🚀 Fichero GUI starting up...")
        logger.info("Fichero GUI starting up")
        
        # Setup translations after app is created
        setup_translations()
        
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

    def about(self):
        """Override Toga's default About dialog with custom About window"""
        self.show_about()

    def _setup_gui_interface(self):
        """Set up GUI-specific interface elements"""
        is_gui_only = self._is_gui_only_mode()
        
        try:
            # Initialize centralized command manager (creates all commands once)
            from fichero.main_window.command_manager import CommandManager
            self.command_manager = CommandManager(self)
            self.command_manager.add_to_app()
            
            # Initialize menu system (only handles custom overrides)
            self.menu_manager = MenuManager(self)
            self.menu_manager.customize_standard_commands()
            
            # Customize standard commands (remove unimplemented ones)
            self.menu_manager.customize_standard_commands()
            
            # Create main window for collection library view (only once)
            from fichero.main_window import MainWindow
            self.main_window_wrapper = MainWindow(self)
            
            if not is_gui_only:
                print("✅ Main window configured for collection library")
            logger.info("Main window configured for collection library")
            
            # Show the main window on startup (this creates the Toga window)
            self.main_window_wrapper.show()
            
            # Set the Toga main_window property to the actual Toga window
            self.main_window = self.main_window_wrapper.window
            
        except Exception as e:
            error_msg = f"GUI interface setup failed: {e}"
            logger.warning(error_msg)
            if not is_gui_only:
                print(f"⚠️ Warning: {error_msg}")

    # Activity Monitor Management
    def show_activity_monitor(self):
        """Show the activity monitor window - manages single instance"""
        is_gui_only = self._is_gui_only_mode()
        
        try:
            # Check if activity monitor window already exists in Toga's window list
            activity_window = None
            for window in self.windows:
                if window.title == "Fichero Activity Monitor":
                    activity_window = window
                    break
            
            if activity_window and not activity_window.closed:
                # Window exists and is not closed - force it to come to front
                if activity_window.visible:
                    # Hide and show to force it to come to front
                    activity_window.hide()
                    activity_window.show()
                else:
                    activity_window.show()
                logger.info("Activity monitor window shown (existing)")
            else:
                # Create new activity monitor window - Toga will automatically add it to app.windows
                from fichero.ui.windows.activity_monitor_window import ActivityMonitorWindow
                self._activity_monitor_window = ActivityMonitorWindow(self)
                self._activity_monitor_window.show()
                logger.info("Activity monitor window created and shown")
                
        except Exception as e:
            error_msg = f"Failed to show activity monitor: {e}"
            logger.error(error_msg)
            if not is_gui_only:
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()

    def close_activity_monitor(self):
        """Close the activity monitor window"""
        try:
            if hasattr(self, '_activity_monitor_window') and self._activity_monitor_window:
                self._activity_monitor_window.close()
                # Toga will automatically remove it from app.windows
                self._activity_monitor_window = None
                logger.info("Activity monitor window closed")
        except Exception as e:
            logger.error(f"Failed to close activity monitor: {e}")

    def show_settings(self):
        """Show the settings window - manages single instance"""
        is_gui_only = self._is_gui_only_mode()
        
        try:
            # Check if settings window already exists in Toga's window list
            settings_window = None
            for window in self.windows:
                if window.title == "Fichero Settings":
                    settings_window = window
                    break
            
            if settings_window and not settings_window.closed:
                # Window exists and is not closed - force it to come to front
                if settings_window.visible:
                    # Hide and show to force it to come to front
                    settings_window.hide()
                    settings_window.show()
                else:
                    settings_window.show()
                logger.info("Settings window shown (existing)")
            else:
                # Create new settings window - Toga will automatically add it to app.windows
                from fichero.config.ui import create_settings_window
                self._settings_window = create_settings_window(self)
                self._settings_window.show()
                logger.info("Settings window created and shown")
                
        except Exception as e:
            error_msg = f"Failed to show settings: {e}"
            logger.error(error_msg)
            if not is_gui_only:
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()

    def close_settings(self):
        """Close the settings window"""
        try:
            if hasattr(self, '_settings_window') and self._settings_window:
                self._settings_window.close()
                # Toga will automatically remove it from app.windows
                self._settings_window = None
                logger.info("Settings window closed")
        except Exception as e:
            logger.error(f"Failed to close settings: {e}")

    def show_about(self):
        """Show the about window - manages single instance"""
        is_gui_only = self._is_gui_only_mode()
        
        try:
            # Check if about window already exists in Toga's window list
            about_window = None
            for window in self.windows:
                if window.title == "About Fichero":
                    about_window = window
                    break
            
            if about_window and not about_window.closed:
                # Window exists and is not closed - force it to come to front
                if about_window.visible:
                    # Hide and show to force it to come to front
                    about_window.hide()
                    about_window.show()
                else:
                    about_window.show()
                logger.info("About window shown (existing)")
            else:
                # Create new about window - Toga will automatically add it to app.windows
                from fichero.ui.windows.about_window import AboutWindow
                self._about_window = AboutWindow(self)
                self._about_window.show()
                logger.info("About window created and shown")
                
        except Exception as e:
            error_msg = f"Failed to show about window: {e}"
            logger.error(error_msg)
            if not is_gui_only:
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()

    def close_about(self):
        """Close the about window"""
        try:
            if hasattr(self, '_about_window') and self._about_window:
                self._about_window.close()
                # Toga will automatically remove it from app.windows
                self._about_window = None
                logger.info("About window closed")
        except Exception as e:
            logger.error(f"Failed to close about window: {e}")

    def close_all_windows(self):
        """Close all secondary windows"""
        try:
            # Close activity monitor
            if hasattr(self, '_activity_monitor_window') and self._activity_monitor_window:
                try:
                    self._activity_monitor_window.close()
                except Exception as e:
                    logger.warning(f"Error closing activity monitor: {e}")
                finally:
                    self._activity_monitor_window = None
            
            # Close settings
            if hasattr(self, '_settings_window') and self._settings_window:
                try:
                    self._settings_window.close()
                except Exception as e:
                    logger.warning(f"Error closing settings: {e}")
                finally:
                    self._settings_window = None
            
            # Close about
            if hasattr(self, '_about_window') and self._about_window:
                try:
                    self._about_window.close()
                except Exception as e:
                    logger.warning(f"Error closing about: {e}")
                finally:
                    self._about_window = None
            
            logger.info("All secondary windows closed")
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