"""
Session Management
Handles saving and restoring document sessions
"""

import logging
from pathlib import Path
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import FicheroApp

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages document session persistence"""
    
    def __init__(self, app: 'FicheroApp'):
        self.app = app
        # Don't auto-restore session during initialization - delay until app is ready
        self._initialization_complete = False
        # Register for automatic cleanup - no manual orchestration needed
        self._register_cleanup()
    
    def startup_when_ready(self):
        """Restore session after app is fully initialized"""
        if not self._initialization_complete:
            try:
                logger.info("Auto-restoring session during startup...")
                self.restore_session()
                logger.info("Session auto-restore completed")
                self._initialization_complete = True
            except Exception as e:
                logger.error(f"Session auto-restore failed: {e}")
    
    def _register_cleanup(self):
        """Register automatic session saving for app cleanup"""
        try:
            # Store original finalize method if it exists
            original_finalize = getattr(self.app, '_original_finalize', getattr(self.app, 'finalize', None))
            if original_finalize:
                # Store the original method
                self.app._original_finalize = original_finalize
                
                # Create wrapper that calls session save + original finalize
                def enhanced_finalize():
                    try:
                        logger.info("Auto-saving session during app finalize...")
                        self.save_session()
                        logger.info("Session auto-save completed")
                    except Exception as e:
                        logger.error(f"Session auto-save failed: {e}")
                    # Call original finalize
                    if original_finalize:
                        original_finalize()
                
                # Replace finalize with enhanced version
                self.app.finalize = enhanced_finalize
                logger.info("Session auto-save registered for app finalize")
        except Exception as e:
            logger.warning(f"Failed to register session auto-save: {e}")
    
    def save_session(self):
        """Save currently open documents for session restoration"""
        logger.info("Saving session...")
        try:
            from ..config.core.app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app)
            
            # Get list of open document paths - SIMPLIFIED
            open_doc_paths = []
            if hasattr(self.app, 'documents') and self.app.documents:
                logger.info(f"Found {len(self.app.documents)} open documents")
                for doc in self.app.documents:
                    # Get effective path (user path or auto-save path)
                    effective_path = doc.get_effective_path()
                    if effective_path and effective_path.exists():
                        # Save ALL documents with paths, regardless of type
                        open_doc_paths.append(effective_path)
                        logger.info(f"Saving session document: {doc.get_display_name()} -> {effective_path}")
                    else:
                        logger.warning(f"Skipping document with no effective path: {doc.get_display_name()}")
            else:
                logger.info("No documents found or documents attribute missing")
            
            # Save to preferences
            logger.info(f"Saving {len(open_doc_paths)} document paths to preferences...")
            success = app_prefs.set_open_documents(open_doc_paths)
            logger.info(f"Preferences save result: {success}")
            
            if open_doc_paths:
                logger.info(f"Session saved: {len(open_doc_paths)} documents")
            else:
                logger.info("Session saved: no open documents")
                
        except Exception as e:
            logger.error(f"Error in save_session: {e}")
            import traceback
            traceback.print_exc()
    
    def restore_session(self):
        """Restore previously open documents or create new document"""
        try:
            from ..config.core.app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app)
            
            # Get list of documents to restore
            docs_to_restore = app_prefs.get_open_documents()
            
            if docs_to_restore:
                logger.info(f"Restoring session: {len(docs_to_restore)} documents")
                documents_opened = 0
                failed_documents = []
                
                for doc_path in docs_to_restore:
                    try:
                        logger.info(f"Attempting to restore: {doc_path}")
                        # Check if document still exists
                        if not doc_path.exists():
                            logger.warning(f"Document no longer exists: {doc_path}")
                            failed_documents.append(doc_path)
                            continue
                        
                        # Attempt to open the document
                        doc = self.app.open_document(doc_path)
                        if doc:
                            documents_opened += 1
                            logger.info(f"Successfully restored: {doc_path.name}")
                        else:
                            logger.error(f"Failed to open document: {doc_path.name}")
                            failed_documents.append(doc_path)
                    except Exception as e:
                        logger.error(f"Error restoring {doc_path.name}: {e}")
                        failed_documents.append(doc_path)
                
                # Clean up failed documents from session
                if failed_documents:
                    remaining_docs = [doc for doc in docs_to_restore if doc not in failed_documents]
                    app_prefs.set_open_documents(remaining_docs)
                    logger.info(f"Cleaned {len(failed_documents)} failed documents from session")
                
                if documents_opened > 0:
                    logger.info(f"Successfully restored {documents_opened} documents")
                    return  # Don't create new document if we restored some
                else:
                    logger.warning("No documents could be restored, not creating new document automatically")
                    # Don't auto-create document - let user create when needed
            else:
                logger.info("No previous session found, not creating new document automatically")
                # Don't auto-create document - let user create when needed
                
        except Exception as e:
            logger.error(f"Critical error in session restoration: {e}")
            import traceback
            traceback.print_exc()
            logger.info("Not creating new document due to error")
            # Don't auto-create document - let user create when needed
    
    def clear_session(self):
        """Clear saved session (useful for 'Start Fresh' option)"""
        try:
            from ..config.core.app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app)
            app_prefs.clear_open_documents()
            logger.info("Session cleared")
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")


# Global session manager instance
_session_manager = None

def get_session_manager(app: 'FicheroApp' = None):
    """Get the global session manager instance"""
    global _session_manager
    if _session_manager is None and app:
        _session_manager = SessionManager(app)
    return _session_manager

def init_session_manager(app: 'FicheroApp'):
    """Initialize the global session manager"""
    global _session_manager
    _session_manager = SessionManager(app)
    return _session_manager 