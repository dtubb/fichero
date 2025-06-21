"""
Document Manager
Handles high-level document operations for the application
"""

import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import FicheroApp
    from .document_model import FicheroDocument

logger = logging.getLogger(__name__)


class DocumentManager:
    """Manages high-level document operations for the application"""
    
    def __init__(self, app: 'FicheroApp'):
        self.app = app
        logger.info("DocumentManager initialized")
    
    def new_document(self) -> Optional['FicheroDocument']:
        """Create a new document using Toga's document system"""
        try:
            # Check if there's already a blank document we can reuse
            if hasattr(self.app, 'documents') and self.app.documents:
                for existing_doc in self.app.documents:
                    if hasattr(existing_doc, 'is_blank_document') and existing_doc.is_blank_document():
                        # Found a blank document - bring it to front instead of creating new
                        if hasattr(existing_doc, 'main_window') and existing_doc.main_window:
                            existing_doc.main_window.show()
                            logger.info(f"Brought existing blank document to front: {existing_doc.get_display_name()}")
                            return existing_doc
            
            # No blank document found, create a new one
            from .document_model import FicheroDocument
            doc = FicheroDocument(self.app)
            doc.create()  # This sets doc.main_window
            doc.main_window.show()  # Now show the window
            
            # Track the new document creation
            from . import get_document_tracker
            tracker = get_document_tracker()
            if tracker:
                tracker.document_created(doc)
            
            logger.info(f"Created new document: {doc.get_display_name()}")
            return doc
            
        except Exception as e:
            logger.error(f"Failed to create new document: {e}")
            return None
    
    def open_document(self, document_path: Path) -> Optional['FicheroDocument']:
        """Open an existing document using Toga's document system"""
        try:
            logger.info(f"Opening document: {document_path}")
            
            # Validate document path
            if not document_path.exists():
                logger.error(f"Document does not exist: {document_path}")
                return None
            
            # Create document instance
            logger.debug("Creating FicheroDocument instance...")
            from .document_model import FicheroDocument
            doc = FicheroDocument(self.app, document_path)
            
            # Create document window
            logger.debug("Creating document window...")
            doc.create()  # This sets doc.main_window
            
            if not doc.main_window:
                logger.error("Failed to create document window")
                return None
            
            # Show the window  
            logger.debug("Showing document window...")
            doc.main_window.show()
            
            # Track the document opening
            from . import get_document_tracker
            tracker = get_document_tracker()
            if tracker:
                tracker.document_opened(document_path)
            
            logger.info(f"Successfully opened document: {document_path.name}")
            return doc
            
        except Exception as e:
            logger.error(f"Failed to open document {document_path}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_document(self, document: 'FicheroDocument' = None) -> bool:
        """Save a document"""
        try:
            if not document:
                logger.warning("No document provided to save")
                return False
            
            document.write()
            
            # Track the document saving if it has a path
            from . import get_document_tracker
            tracker = get_document_tracker()
            if tracker:
                if hasattr(document, 'path') and document.path:
                    tracker.document_saved(document.path)
                elif hasattr(document, 'get_effective_path'):
                    effective_path = document.get_effective_path()
                    if effective_path:
                        tracker.document_saved(effective_path)
            
            logger.info(f"Saved document: {getattr(document, 'path', 'auto-saved')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save document: {e}")
            return False
    
    def close_document(self, document: 'FicheroDocument') -> bool:
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
                            logger.info(f"Auto-saving document with changes: {display_name}")
                            if hasattr(document, 'auto_save_manager') and document.auto_save_manager:
                                document.auto_save_manager.auto_save()
                        else:
                            logger.info(f"Document has changes: {display_name}")
                            # In a real implementation, you'd show a save dialog here
                            # For now, we'll save automatically if it's an auto-saved document
                            if hasattr(document, 'write'):
                                document.write()
                    except Exception as e:
                        logger.warning(f"Error handling document save: {e}")
            
            # Call document's close method to handle cleanup
            if hasattr(document, 'close'):
                should_close = document.close()
                if not should_close:
                    # Document decided not to close (e.g., reset to blank instead)
                    return False
            
            logger.info(f"Closed document: {getattr(document, 'path', 'untitled')}")
            return True
            
        except Exception as e:
            logger.warning(f"Error closing document: {e}")
            return True  # Allow close even if cleanup fails


# Global instance - will be initialized by the app
_document_manager: Optional[DocumentManager] = None

def get_document_manager(app: 'FicheroApp' = None) -> Optional[DocumentManager]:
    """Get the global document manager instance"""
    global _document_manager
    if _document_manager is None and app:
        _document_manager = DocumentManager(app)
    return _document_manager

def init_document_manager(app: 'FicheroApp') -> DocumentManager:
    """Initialize the global document manager"""
    global _document_manager
    _document_manager = DocumentManager(app)
    return _document_manager 