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
from pathlib import Path
from .ui import _, translator
from .utils import get_app_settings
from .ui import MenuManager
from .document.document_model import FicheroDocument
from .core.app_initializer import initialize_gui_app
from .core.error_handler import create_gui_error_handler
from . import __version__


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
        print("🚀 Fichero GUI starting up...")
        
         # Initialize components immediately
        try:
            self.components, self.initializer = initialize_gui_app(app_context=self)
            
            # Extract initialized components (same as CLI gets, plus GUI-specific)
            self.settings = self.components['settings']
            self.director = self.components['director']
            self.translator = self.components['translator']
            self.document_tracker = self.components['document_tracker']
            self.auto_save_manager = self.components['auto_save_manager']
            self.session_manager = self.components['session_manager']
            
            print("✅ Fichero components initialized")
            
        except Exception as e:
            print(f"❌ Failed to initialize Fichero: {e}")
            print("Cannot continue without core services.")
            import traceback
            traceback.print_exc()
            
            # Show error dialog to user then quit
            import asyncio
            async def show_error_and_quit():
                # Create a simple error dialog without main window
                await self.error_dialog(
                    "Initialization Error",
                    f"Failed to initialize Fichero core services:\n\n{e}\n\nCannot continue without core services\n\nThe application will now exit."
                )
                self.exit()
            
            # Schedule the error dialog
            asyncio.create_task(show_error_and_quit())
            return
        
        # Initialize GUI-specific systems
        self._setup_gui_interface()
        
        print("✨ Fichero GUI ready!")

    def _setup_gui_interface(self):
        """Set up GUI-specific interface elements"""
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
            
        except Exception as e:
            print(f"⚠️ Warning: GUI interface setup failed: {e}")

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
            print(f"❌ Failed to create new document: {e}")
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
            print(f"❌ Failed to open document: {e}")
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
            print(f"⚠️ Warning: Error closing document: {e}")
            return True

    def finalize(self):
        """Clean up when app closes - delegates to shared cleanup system"""
        print("🔄 Fichero GUI closing...")
        try:
            # Use shared cleanup wrapper (same pattern as CLI)
            if hasattr(self, 'initializer') and self.initializer:
                self.initializer.cleanup()
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")
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