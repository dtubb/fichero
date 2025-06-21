"""
Fichero Document class
Implements Toga's document-based architecture
"""

import toga
from pathlib import Path
import uuid
import logging
from typing import Optional

from ..utils import _, get_app_settings
from .document_window import FicheroDocumentWindow
from .auto_save import AutoSaveManager
from .document_state import DocumentStateManager
from .window_manager import DocumentWindowManager

logger = logging.getLogger(__name__)


class FicheroDocument(toga.Document):
    """Fichero document class representing a document processing project"""
    
    description = "Fichero Document Processing Project"
    extensions = ["fichero"]
    
    def __init__(self, app, path: Optional[Path] = None, test_mode: bool = False):
        # Minimal initialization - just call super and store basic info
        super().__init__(app)
        
        self.document_id = str(uuid.uuid4())
        self.is_modified = False
        self._test_mode = test_mode
        
        if path:
            self.path = path
            
        print(f"📄 FicheroDocument {self.document_id} created")
    
    def get_display_name(self) -> str:
        """Get display name for the document"""
        if hasattr(self, 'path') and self.path:
            return self.path.stem
        return "Untitled"
    
    def _init_document_structure(self):
        """Initialize or load document structure"""
        if hasattr(self, 'path') and self.path and self.path.exists():
            # Loading existing document - don't create auto-save
            self.state_manager.load_document(self.path)
            logger.info(f"Loaded existing document: {self.path}")
        else:
            # Creating new document - set up auto-save
            self._create_new_document()
    
    def _create_new_document(self):
        """Create a new document with default structure"""
        # For new documents, create an auto-save location
        self.auto_save_manager.setup_auto_save_path()
        
        # Create default plans and document config
        self.state_manager.create_default_plans()
        self.state_manager.create_default_document_config()
        
        # Auto-save the new document immediately
        self.auto_save_manager.auto_save()
        
        logger.info(f"Created new document with auto-save at: {self.auto_save_manager.auto_save_path}")
    
    def create(self):
        """Create the document window - called automatically by Toga"""
        if self._test_mode:
            logger.info(f"Skipping window creation in test mode for document {self.document_id}")
            return None
        
        try:
            print(f"📄 Creating window for document {self.document_id}")
            # Create a simple DocumentWindow with minimal content for now
            self.main_window = toga.DocumentWindow(
                doc=self,
                title=f"Fichero - {self.get_display_name()}"
            )
            
            # Add simple placeholder content
            content = toga.Box(
                children=[
                    toga.Label(f"Document: {self.get_display_name()}", style={"padding": 20})
                ]
            )
            self.main_window.content = content
            
            print(f"✅ Created simple document window")
            return self.main_window
        except Exception as e:
            print(f"❌ Failed to create document window: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def read(self):
        """Read document data from file"""
        if hasattr(self, 'path') and self.path:
            print(f"📖 Reading document: {self.path}")
            # Minimal implementation for now
    
    def write(self):
        """Write document data to file"""
        if hasattr(self, 'path') and self.path:
            print(f"💾 Writing document: {self.path}")
            # Minimal implementation - just create the directory
            self.path.mkdir(parents=True, exist_ok=True)
            self.is_modified = False

    # Delegation methods for easier access
    def get_effective_path(self) -> Optional[Path]:
        """Get the effective path (either user-set path or auto-save path)"""
        return self.auto_save_manager.get_effective_path()
    
    def is_auto_saved_document(self) -> bool:
        """Check if this is an auto-saved document"""
        return self.auto_save_manager.is_auto_saved
    
    def has_meaningful_changes(self) -> bool:
        """Check if document has meaningful changes from default state"""
        # Check document state first
        if self.state_manager.has_meaningful_changes():
            return True
        
        # Check if any files were added to documents folder
        if self.auto_save_manager.auto_save_path:
            documents_dir = self.auto_save_manager.auto_save_path / "documents"
            if documents_dir.exists() and any(documents_dir.iterdir()):
                return True
        
        return False
    
    def mark_modified(self):
        """Mark document as modified and trigger save"""
        self.is_modified = True
        
        # Save to appropriate location
        if hasattr(self, 'path') and self.path:
            # Existing document - save to original location
            self.write()
            logger.debug(f"Document saved after modification: {self.path}")
        elif self.auto_save_manager.auto_save_path:
            # New document - auto-save to temporary location
            self.auto_save_manager.auto_save()
            logger.debug(f"Document auto-saved after modification: {self.auto_save_manager.auto_save_path}")
    
    def get_display_name(self) -> str:
        """Get display name for the document"""
        if hasattr(self, 'path') and self.path:
            name = self.path.stem
        elif self.auto_save_manager.auto_save_path:
            # Show a friendly name for auto-saved documents
            name = self.auto_save_manager.auto_save_path.stem.replace(f"_{self.document_id[:8]}", "")
        else:
            name = "Untitled"
        
        # Add modified indicator
        if self.is_modified:
            name += " •"
        
        return name
    
    def close(self):
        """Close the document - if blank and unchanged, reset and keep open instead"""
        try:
            # Save current window position before any close logic
            self.window_manager.save_current_window_position()
            
            # If this is an auto-saved document that was never explicitly saved by user,
            # check if it has meaningful changes
            if self.auto_save_manager.is_auto_saved and self.auto_save_manager.auto_save_path and self.auto_save_manager.auto_save_path.exists():
                # Check if user ever explicitly saved this document
                if not (hasattr(self, 'path') and self.path):
                    # Check if document has meaningful changes
                    if self.has_meaningful_changes():
                        # Document has changes, should be preserved (don't clean up)
                        logger.info(f"Preserving auto-saved document with changes: {self.auto_save_manager.auto_save_path.name}")
                        return True  # Keep the auto-save
                    else:
                        # No meaningful changes - reset document instead of closing
                        logger.info(f"Resetting blank document instead of closing: {self.auto_save_manager.auto_save_path.name}")
                        self._reset_to_blank_document()
                        return False  # Don't close - keep window open
        except Exception as e:
            logger.error(f"Error in close logic: {e}")
        
        return True  # Allow close by default
    
    def can_close(self) -> bool:
        """Check if document can be closed"""
        # If document has meaningful changes, it should prompt for save
        if self.has_meaningful_changes():
            return False  # Will trigger save prompt
        
        # Unchanged documents can be closed without prompting
        return True
    
    def _reset_to_blank_document(self):
        """Reset document to blank state instead of closing"""
        try:
            # Reset auto-save
            self.auto_save_manager.reset_auto_save()
            
            # Reset document to default state
            self.state_manager.create_default_plans()
            self.state_manager.create_default_document_config()
            
            # Restore window position if we had one saved
            self.window_manager.restore_window_position()
            
            # Auto-save the fresh document
            self.auto_save_manager.auto_save()
            
            # Reset modification flag
            self.is_modified = False
            
            logger.info(f"Reset document to blank state: {self.auto_save_manager.auto_save_path}")
            
        except Exception as e:
            logger.error(f"Failed to reset document: {e}")
    
    def is_blank_document(self) -> bool:
        """Check if this is a blank, unchanged document that should be reset instead of closed"""
        return (self.auto_save_manager.is_auto_saved and 
                not (hasattr(self, 'path') and self.path) and
                not self.has_meaningful_changes())
    
    # Window position delegation methods
    def save_window_position(self, position: tuple, size: tuple = None):
        """Save window position and size to document config"""
        self.window_manager.save_window_position(position, size)
    
    def get_window_position(self) -> tuple:
        """Get saved window position"""
        return self.window_manager.get_window_position()
    
    def get_window_size(self) -> tuple:
        """Get saved window size"""
        return self.window_manager.get_window_size()
    
    def add_document_file(self, file_path: Path) -> bool:
        """Add a file to the document's documents folder and trigger auto-save"""
        return self.auto_save_manager.add_document_file(file_path)
    
    # Processing settings delegation methods
    def set_input_folder(self, folder_path: str):
        """Set the input folder for processing"""
        self.state_manager.set_input_folder(folder_path)
    
    def get_input_folder(self) -> str:
        """Get the input folder for processing"""
        return self.state_manager.get_input_folder()
    
    def update_title(self, new_title: str):
        """Update document title and trigger auto-save"""
        self.state_manager.update_title(new_title)
    
    def update_description(self, new_description: str):
        """Update document description and trigger auto-save"""
        self.state_manager.update_description(new_description)
    
    # File management delegation methods  
    def add_open_file(self, file_path: str):
        """Add a file to the open files list"""
        self.window_manager.add_open_file(file_path)
    
    def remove_open_file(self, file_path: str):
        """Remove a file from the open files list"""
        self.window_manager.remove_open_file(file_path)
    
    def get_open_files(self) -> list:
        """Get list of open files"""
        return self.window_manager.get_open_files()
    
    # Convenience properties for accessing manager data
    @property
    def plans_config(self):
        """Access to plans configuration"""
        return self.state_manager.plans_config
    
    @plans_config.setter
    def plans_config(self, value):
        """Set plans configuration"""
        self.state_manager.plans_config = value
    
    @property
    def document_config(self):
        """Access to document configuration"""
        return self.state_manager.document_config
    
    @document_config.setter
    def document_config(self, value):
        """Set document configuration"""
        self.state_manager.document_config = value 