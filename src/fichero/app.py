"""
Fichero
Cross platform GUI (macOS, Windows, Linux) using Toga.
Document-based application.
"""

import toga
from toga.style import Pack
import os
import sys
from pathlib import Path

from .utils import _, translator, get_app_settings
from .ui import MenuManager
from .document_model import FicheroDocument
from . import director


class FicheroApp(toga.App):
    formal_name = "Fichero"
    app_id = "ca.tubb.fichero"
    app_name = "Fichero"
    description = "Document Processing and Transcription"
    author = "Daniel Tubb"
    version = "0.0.5"
    home_page = "https://www.tubb.ca/fichero/"
    
    def startup(self):
        """Initialize the app with toga document-based architecture"""
        # Configure logging
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        print("🚀 Fichero starting up...")
        
        # Initialize settings and environment
        self._init_settings()
        
        # Initialize language system (needs settings, so goes right after)
        from .utils.i18n import TranslationManager, set_global_translator
        self.translator = TranslationManager(app=self)
        set_global_translator(self.translator)
        print(f"🌐 Language: {self.translator.current_language}")
        
        # Initialize document tracker and managers
        from .document import init_document_tracker, init_app_auto_save_manager, init_session_manager
        self.document_tracker = init_document_tracker(self)
        self.auto_save_manager = init_app_auto_save_manager(self)
        self.session_manager = init_session_manager(self)
        
        # Initialize menu system
        self.menu_manager = MenuManager(self)
        commands = self.menu_manager.create_commands()
        self.commands.add(*commands)
        
        # Customize standard commands
        self.menu_manager.customize_standard_commands()
        
        # For document-based apps, main_window should be None
        # This allows the document system to work properly
        self.main_window = None
        
        print("✨ Fichero ready!")
        # Managers handle their own lifecycle automatically!

    def _init_settings(self):
        """Initialize application settings and environment variables"""
        try:
            # Initialize app preferences first (this creates the preferences file if needed)
            from .config.core.app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self)
            print("📋 App preferences initialized")
            
            # Load settings (environment variables are set automatically)
            settings = get_app_settings(self)
            
            # Initialize shared data backend with user's preference
            self._init_shared_data_backend(settings)
                
        except Exception as e:
            print(f"⚠️ Warning: Failed to load settings: {e}")

    def _init_shared_data_backend(self, settings):
        """Initialize the shared data backend based on user settings"""
        try:
            # Get user's backend preference
            backend_setting = settings.settings.get("workers", {}).get("backend", "python")
            
            # Convert setting to backend preference
            if backend_setting == "redis":
                prefer_backend = "redis"
            else:  # "python" or anything else
                prefer_backend = "manager"
            
            # Initialize shared data with the preference and proper app data directory
            from .shared_data import reload_shared_data
            app_data_dir = self.paths.data if hasattr(self, 'paths') else None
            shared_data = reload_shared_data(prefer_backend=prefer_backend, data_dir=app_data_dir)
            
            print(f"🔧 Processing backend initialized: {shared_data.backend_name} ({'Redis+Celery' if backend_setting == 'redis' else 'Python Manager'})")
            
        except Exception as e:
            print(f"⚠️ Warning: Failed to initialize processing backend: {e}")

    def finalize(self):
        """Clean up when app closes"""
        print("🔄 finalize() called - app is closing")
        try:
            # Only app-specific cleanup needed (session save happens automatically)
            print("🧹 Cleaning up Redis and Celery workers...")
            director.stop_workers()
            print("✓ Cleanup completed")
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")
            import traceback
            traceback.print_exc()







    # Document operations (using Toga's document system)
    # These methods will be called automatically by Toga's standard document commands
    
    def new_document(self):
        """Create a new document using Toga's document system"""
        try:
            # Check if there's already a blank document we can reuse
            if hasattr(self, 'documents') and self.documents:
                for existing_doc in self.documents:
                    if hasattr(existing_doc, 'is_blank_document') and existing_doc.is_blank_document():
                        # Found a blank document - bring it to front instead of creating new
                        if hasattr(existing_doc, 'main_window') and existing_doc.main_window:
                            existing_doc.main_window.show()
                            print(f"📄 Brought existing blank document to front: {existing_doc.get_display_name()}")
                            return existing_doc
            
            # No blank document found, create a new one
            doc = FicheroDocument(self)
            doc.create()  # This sets doc.main_window
            doc.main_window.show()  # Now show the window
            
            # Track the new document creation
            self.document_tracker.document_created(doc)
            print(f"📄 Created new document: {doc.get_display_name()}")
            
            return doc
        except Exception as e:
            print(f"❌ Failed to create new document: {e}")
            return None
    
    def open_document(self, document_path: Path):
        """Open an existing document using Toga's document system"""
        try:
            print(f"🔄 Opening document: {document_path}")
            
            # Validate document path
            if not document_path.exists():
                print(f"❌ Document does not exist: {document_path}")
                return None
            
            # Create document instance
            print(f"📄 Creating FicheroDocument instance...")
            doc = FicheroDocument(self, document_path)
            
            # Create document window
            print(f"🪟 Creating document window...")
            doc.create()  # This sets doc.main_window
            
            if not doc.main_window:
                print(f"❌ Failed to create document window")
                return None
            
            # Show the window  
            print(f"👁️ Showing document window...")
            doc.main_window.show()
            
            # Track the document opening
            self.document_tracker.document_opened(document_path)
            print(f"✅ Successfully opened document: {document_path.name}")
            return doc
        except Exception as e:
            print(f"❌ Failed to open document {document_path}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_document(self, document=None):
        """Save a document"""
        if document:
            document.write()
            # Track the document saving if it has a path
            if hasattr(document, 'path') and document.path:
                self.document_tracker.document_saved(document.path)
            elif hasattr(document, 'get_effective_path'):
                effective_path = document.get_effective_path()
                if effective_path:
                    self.document_tracker.document_saved(effective_path)
    
    def close_document(self, document):
        """Close a document with save prompt if needed"""
        try:
            # Check if document can be closed without prompting
            if hasattr(document, 'can_close') and not document.can_close():
                # Document has changes, prompt user to save
                if hasattr(document, 'has_meaningful_changes') and document.has_meaningful_changes():
                    try:
                        # Try to show save dialog (this will work in actual Toga app)
                        display_name = document.get_display_name() if hasattr(document, 'get_display_name') else "Untitled"
                        
                        # For now, auto-save if it's an auto-saved document with changes
                        if hasattr(document, 'is_auto_saved_document') and document.is_auto_saved_document():
                            print(f"💾 Auto-saving document with changes: {display_name}")
                            if hasattr(document, '_auto_save'):
                                document._auto_save()
                        else:
                            print(f"💾 Document has changes: {display_name}")
                            # In a real implementation, you'd show a save dialog here
                            # For now, we'll save automatically if it's an auto-saved document
                            if hasattr(document, 'write'):
                                document.write()
                    except Exception as e:
                        print(f"⚠️ Warning: Error handling document save: {e}")
            
            # Call document's close method to handle cleanup
            if hasattr(document, 'close'):
                document.close()
            
            # Toga handles document closing automatically
            return True
        except Exception as e:
            print(f"⚠️ Warning: Error closing document: {e}")
            return True  # Allow close even if cleanup fails

def main():
    """Main entry point"""
    try:
        app = FicheroApp(
            formal_name="Fichero",
            app_id="ca.tubb.fichero",
            document_types=[FicheroDocument]
        )
        app.main_loop()
    except KeyboardInterrupt:
        print("\n👋 Fichero interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"💥 Fichero crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main() 