"""
Document package for Fichero
Contains modular document management components
"""

from .auto_save import AutoSaveManager, AppAutoSaveManager, get_app_auto_save_manager, init_app_auto_save_manager
from .document_state import DocumentStateManager
from .window_manager import DocumentWindowManager
from .document_tracker import DocumentTracker, get_document_tracker, init_document_tracker
from .session_manager import SessionManager, get_session_manager, init_session_manager

__all__ = [
    "AutoSaveManager",
    "AppAutoSaveManager",
    "get_app_auto_save_manager",
    "init_app_auto_save_manager",
    "DocumentStateManager",
    "DocumentWindowManager",
    "DocumentTracker",
    "get_document_tracker",
    "init_document_tracker",
    "SessionManager",
    "get_session_manager",
    "init_session_manager"
] 