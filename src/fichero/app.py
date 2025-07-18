"""
Fichero GUI Application - Thin Wrapper

Cross-platform GUI (macOS, Windows, Linux) using Toga and Briefcase.

Architecture:
- Thin wrapper: delegates ALL initialization to core/app_initializer.py
- Extracts components (director, settings) for convenient access
- Delegates ALL business logic to appropriate shared systems
- Document-based application with Toga's document system

Two-step process:
1. Delegate initialization to shared app_initializer
2. Extract components for clean method code
"""

import toga
from toga.style import Pack
import os
import sys
import logging
from pathlib import Path
from .ui import _, translator
from .utils import get_app_settings
from .ui import MenuManager
from .document.document_model import FicheroDocument
from .core.app_initializer import initialize_gui_app
from .core.error_handler import create_gui_error_handler
from . import __version__

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
        
        # Set app icon first
        try:
            self.icon = toga.Icon("resources/icons/fichero")
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
            self.translator = self.components['translator']
            self.document_tracker = self.components['document_tracker']
            self.auto_save_manager = self.components['auto_save_manager']
            self.session_manager = self.components['session_manager']
            
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
            
            # Exit cleanly without showing dialog during startup
            self.exit()
            return
        
        # Initialize GUI-specific systems
        self._setup_gui_interface()
        
        if not is_gui_only:
            print("✨ Fichero GUI ready!")
        logger.info("Fichero GUI ready")
    
    def _is_gui_only_mode(self):
        """Detect if running as bundled GUI app (minimize console output)"""
        # Check if running as bundled app
        is_bundled = getattr(sys, 'frozen', False) or hasattr(sys, '_MEIPASS')
        
        # Check if stdout is not connected to terminal (GUI app)
        is_gui_app = not sys.stdout.isatty() if hasattr(sys.stdout, 'isatty') else True
        
        # Check if running via briefcase (look for app bundle structure)
        is_briefcase_app = 'Contents/MacOS' in str(sys.executable) if sys.executable else False
        
        return is_bundled or is_briefcase_app or (is_gui_app and not os.environ.get('TERM'))

    def _setup_gui_interface(self):
        """Set up GUI-specific interface elements"""
        is_gui_only = self._is_gui_only_mode()
        
        try:
            # Initialize menu system
            self.menu_manager = MenuManager(self)
            commands = self.menu_manager.create_commands()
            self.commands.add(*commands)
            
            # Customize standard commands
            self.menu_manager.customize_standard_commands()
            
            # Check for missing Window commands (debugging)
            self.menu_manager.check_for_missing_window_commands()
            
            # For document-based apps, main_window should be None
            # This allows the document system to work properly
            self.main_window = None
            
            if not is_gui_only:
                print("✅ Document-based app configured (no main window)")
            logger.info("Document-based app configured (no main window)")
            
            # Create a new document window on startup (session restoration disabled)
            self.new_document()
            
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
            # Use the menu manager's activity monitor window
            if hasattr(self, 'menu_manager') and self.menu_manager:
                self.menu_manager._activity_monitor_handler(None)
            else:
                error_msg = "Menu manager not available for activity monitor"
                logger.warning(error_msg)
                if not is_gui_only:
                    print(f"⚠️ {error_msg}")
        except Exception as e:
            error_msg = f"Failed to show activity monitor: {e}"
            logger.error(error_msg)
            if not is_gui_only:
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()

    # Document operations - thin wrappers that delegate to document system
    def new_document(self):
        """Create a new document - delegates to document system"""
        try:
            doc = FicheroDocument(self)
            doc.create()
            doc.main_window.show()
            
            # Track via document system
            if self.document_tracker:
                self.document_tracker.document_created(doc)
            
            return doc
        except Exception as e:
            error_msg = f"Failed to create new document: {e}"
            logger.error(error_msg)
            is_gui_only = self._is_gui_only_mode()
            if not is_gui_only:
                print(f"❌ {error_msg}")
            return None
    
    def open_document(self, document_path: Path):
        """Open an existing document - delegates to document system"""
        try:
            doc = FicheroDocument(self, document_path)
            doc.create()
            doc.main_window.show()
            
            # Track via document system
            if self.document_tracker:
                self.document_tracker.document_opened(document_path)
            
            return doc
        except Exception as e:
            error_msg = f"Failed to open document: {e}"
            logger.error(error_msg)
            is_gui_only = self._is_gui_only_mode()
            if not is_gui_only:
                print(f"❌ {error_msg}")
            return None
    
    def save_document(self, document=None):
        """Save a document - delegates to document system"""
        if document and hasattr(document, 'write'):
            document.write()
            
            # Track via document system
            if self.document_tracker and hasattr(document, 'path') and document.path:
                self.document_tracker.document_saved(document.path)
    
    def close_document(self, document):
        """Close a document - delegates to document system"""
        try:
            # Let document handle its own closing logic
            if hasattr(document, 'close'):
                document.close()
            return True
        except Exception as e:
            error_msg = f"Error closing document: {e}"
            logger.warning(error_msg)
            is_gui_only = self._is_gui_only_mode()
            if not is_gui_only:
                print(f"⚠️ Warning: {error_msg}")
            return True

    def finalize(self):
        """Clean up when app closes - delegates to shared cleanup system"""
        is_gui_only = self._is_gui_only_mode()
        if not is_gui_only:
            print("🔄 Fichero GUI closing...")
        logger.info("Fichero GUI closing")
        
        try:
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
            app_id="ca.tubb.fichero",
            document_types=[FicheroDocument]
        )
        app.main_loop()
    
    wrapped_app = error_handler.wrap_main_function(run_app, "GUI application")
    wrapped_app()


if __name__ == "__main__":
    main() 