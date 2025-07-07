"""
Document Tracking System
Centralized management of recent documents, open documents, and menu updates
"""

import logging
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import FicheroApp

logger = logging.getLogger(__name__)


class DocumentTracker:
    """Centralized tracker for document usage and recent documents"""
    
    def __init__(self, app: 'FicheroApp'):
        self.app = app
        self._recent_documents_cache = None
    
    def document_opened(self, document_path: Path):
        """Call this when a document is opened"""
        try:
            self._add_to_recent_documents(document_path)
            # Menu updates disabled
            logger.info(f"Tracked document opened: {document_path.name}")
        except Exception as e:
            logger.error(f"Failed to track document opening: {e}")
    
    def document_saved(self, document_path: Path):
        """Call this when a document is saved"""
        try:
            self._add_to_recent_documents(document_path)
            # Menu updates disabled
            logger.info(f"Tracked document saved: {document_path.name}")
        except Exception as e:
            logger.error(f"Failed to track document saving: {e}")
    
    def document_created(self, document):
        """Call this when a new document is created"""
        try:
            # For new documents, track if they have an effective path
            effective_path = None
            if hasattr(document, 'get_effective_path'):
                effective_path = document.get_effective_path()
            elif hasattr(document, 'auto_save_manager') and document.auto_save_manager.auto_save_path:
                effective_path = document.auto_save_manager.auto_save_path
            
            if effective_path and effective_path.exists():
                self._add_to_recent_documents(effective_path)
                # Menu updates disabled
                logger.info(f"Tracked document created: {effective_path.name}")
        except Exception as e:
            logger.error(f"Failed to track document creation: {e}")
    
    def _add_to_recent_documents(self, document_path: Path):
        """Add a document to the recent documents list"""
        try:
            from ..config.core.app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app)
            success = app_prefs.add_recent_document(document_path)
            
            if success:
                # Clear cache so it gets refreshed
                self._recent_documents_cache = None
                logger.debug(f"Added to recent documents: {document_path.name}")
            else:
                logger.warning(f"Failed to add to recent documents: {document_path.name}")
                
        except Exception as e:
            logger.error(f"Error adding to recent documents: {e}")
    
    def _update_menu(self):
        """Update the recent documents menu - currently disabled"""
        # Feature disabled - no-op
        pass
    
    def get_recent_documents(self) -> List[str]:
        """Get list of recent documents (cached)"""
        if self._recent_documents_cache is None:
            try:
                from ..config.core.app_preferences import get_app_preferences
                app_prefs = get_app_preferences(self.app)
                self._recent_documents_cache = app_prefs.get_recent_documents()
            except Exception as e:
                logger.error(f"Failed to get recent documents: {e}")
                self._recent_documents_cache = []
        
        return self._recent_documents_cache or []
    
    def clear_recent_documents(self):
        """Clear all recent documents"""
        try:
            from ..config.core.app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app)
            app_prefs._preferences["recent_documents"] = []
            app_prefs._save_preferences()
            
            # Clear cache and update menu
            self._recent_documents_cache = []
            self._update_menu()
            
            logger.info("Cleared recent documents")
        except Exception as e:
            logger.error(f"Failed to clear recent documents: {e}")
    
    def open_recent_document(self, document_path: str):
        """Open a document from the recent documents list"""
        try:
            path = Path(document_path)
            if path.exists():
                # Use the app's document opening method
                doc = self.app.open_document(path)
                if doc:
                    # Don't call document_opened here since open_document will handle it
                    return doc
                else:
                    logger.warning(f"Failed to open recent document: {path}")
            else:
                logger.warning(f"Recent document not found: {path}")
                # Remove from recent documents if it doesn't exist
                self._remove_missing_document(document_path)
            
            return None
        except Exception as e:
            logger.error(f"Failed to open recent document: {e}")
            return None
    
    def _remove_missing_document(self, document_path: str):
        """Remove a missing document from recent documents list"""
        try:
            from ..config.core.app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app)
            recent = app_prefs.get_recent_documents()
            
            if document_path in recent:
                recent.remove(document_path)
                app_prefs._preferences["recent_documents"] = recent
                app_prefs._save_preferences()
                
                # Clear cache and update menu
                self._recent_documents_cache = None
                self._update_menu()
                
                logger.info(f"Removed missing document from recent list: {document_path}")
                
        except Exception as e:
            logger.error(f"Failed to remove missing document: {e}")


# Global instance - will be initialized by the app
_document_tracker: Optional[DocumentTracker] = None

def get_document_tracker(app: 'FicheroApp' = None) -> DocumentTracker:
    """Get the global document tracker instance"""
    global _document_tracker
    if _document_tracker is None and app:
        _document_tracker = DocumentTracker(app)
    return _document_tracker

def init_document_tracker(app: 'FicheroApp'):
    """Initialize the global document tracker"""
    global _document_tracker
    _document_tracker = DocumentTracker(app)
    return _document_tracker 