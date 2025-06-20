"""
Fichero - Document Processing and Transcription GUI
Document-based application using Toga's document system
"""

import toga
from toga.style import Pack
import os
import sys
from pathlib import Path

from .utils import _, translator, get_app_settings
from .ui import MenuManager
from .document import FicheroDocument
from . import director


class FicheroApp(toga.App):
    """Fichero document-based application"""
    
    formal_name = "Fichero"
    app_id = "ca.tubb.fichero"
    app_name = "Fichero"
    description = "Document Processing and Transcription"
    author = "David Tubb"
    version = "0.0.5"
    home_page = "https://www.tubb.ca/fichero/"
    
    def startup(self):
        """Initialize the app with document-based architecture"""
        # Configure logging
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        print("🚀 Fichero starting up...")
        
        # Initialize settings and environment
        self._init_settings()
        
        # Initialize menu system
        self.menu_manager = MenuManager(self)
        commands = self.menu_manager.create_commands()
        self.commands.add(*commands)
        
        # Customize standard commands
        self.menu_manager.customize_standard_commands()
        
        # For document-based apps, main_window should be None
        # This allows the document system to work properly
        self.main_window = None
        
        # Set initial language after app is initialized
        try:
            # Use the translator's built-in language detection
            # which already detects system language on initialization
            print(f"🌐 Language initialized: {translator.current_language}")
        except Exception as e:
            print(f"⚠️ Warning: Language initialization issue: {e}")
        
        print("✨ Fichero ready!")
        
        # If no documents are specified at startup, create a new document
        # This is typical behavior for document-based apps
        if not hasattr(self, '_documents_opened_at_startup'):
            self.new_document()

    def _init_settings(self):
        """Initialize application settings and environment variables"""
        try:
            # Load settings and set environment variables
            settings = get_app_settings(self)
            api_servers = settings.get_api_servers()
            
            # Set environment variables for API keys
            if api_servers.get("openai", {}).get("api_key"):
                os.environ["OPENAI_API_KEY"] = api_servers["openai"]["api_key"]
                print("🔑 OpenAI API key loaded")
            
            if api_servers.get("qwen", {}).get("api_key"):
                os.environ["DASHSCOPE_API_KEY"] = api_servers["qwen"]["api_key"]
                print("🔑 Qwen API key loaded")
            
            if api_servers.get("claude", {}).get("api_key"):
                os.environ["ANTHROPIC_API_KEY"] = api_servers["claude"]["api_key"]
                print("🔑 Claude API key loaded")
                
        except Exception as e:
            print(f"⚠️ Warning: Failed to load settings: {e}")

    def finalize(self):
        """Clean up when app closes"""
        try:
            print("🧹 Cleaning up Redis and Celery workers...")
            director.stop_workers()
            print("✓ Cleanup completed")
        except Exception as e:
            print(f"Warning: Error during cleanup: {e}")

    def set_language(self, language_code: str):
        """Set the application language and refresh UI"""
        try:
            # Set the language using the translator
            translator.set_language(language_code)
            print(f"🌐 Language changed to: {language_code}")
            
            # Refresh main window title if it exists and is initialized
            try:
                if (hasattr(self, 'main_window') and 
                    self.main_window and 
                    hasattr(self.main_window, 'title')):
                    self.main_window.title = _("app_title")
                    print("✓ Main window title updated")
            except Exception as title_error:
                print(f"⚠️ Could not update main window title: {title_error}")
            
            # Note: In a full implementation, you'd want to refresh all open windows
            # For now, user needs to restart or reopen windows to see language changes
            
        except Exception as e:
            print(f"❌ Error setting language: {e}")
            # Don't raise the exception - allow the app to continue running

    # Document operations (using Toga's document system)
    # These methods will be called automatically by Toga's standard document commands
    
    def new_document(self):
        """Create a new document using Toga's document system"""
        try:
            doc = FicheroDocument(self)
            doc.create()  # This sets doc.main_window
            doc.main_window.show()  # Now show the window
            return doc
        except Exception as e:
            print(f"❌ Failed to create new document: {e}")
            return None
    
    def open_document(self, document_path: Path):
        """Open an existing document using Toga's document system"""
        try:
            doc = FicheroDocument(self, document_path)
            doc.create()  # This sets doc.main_window
            doc.main_window.show()  # Now show the window
            return doc
        except Exception as e:
            print(f"❌ Failed to open document: {e}")
            return None
    
    def save_document(self, document=None):
        """Save a document"""
        if document:
            document.write()
    
    def close_document(self, document):
        """Close a document"""
        # Toga handles document closing automatically
        return True

    # Menu access points
    
    def show_preferences(self):
        """Show application preferences"""
        self.menu_manager._preferences_handler(None)
    
    def show_about(self):
        """Show about dialog"""
        self.menu_manager._about_handler(None)
    
    def edit_global_plans(self):
        """Edit global plans template"""
        self.menu_manager._edit_global_plans_handler(None)
    
    def edit_llm_configs(self):
        """Edit LLM configurations"""
        self.menu_manager._edit_llm_config_handler(None)


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