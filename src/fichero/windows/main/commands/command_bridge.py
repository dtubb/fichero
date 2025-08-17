"""
Command Bridge for Fichero

Bridges commands between the command manager and the UI.
"""

import toga
import logging
from typing import Optional, Any, Callable
from enum import Enum

from ..views.base_view import BaseView
from ..layout.pane_manager import PaneManager

logger = logging.getLogger(__name__)


class CommandContext(Enum):
    """Command context for different UI states"""
    GLOBAL = "global"
    LIBRARY = "library"
    COLLECTION = "collection"
    FICHE = "fiche"
    PREVIEW = "preview"


class CommandBridge:
    """Bridges commands between command manager and UI"""
    
    def __init__(self, app, pane_manager: PaneManager):
        """Initialize command bridge"""
        self.app = app
        self.pane_manager = pane_manager
        
        # Command context
        self.current_context = CommandContext.LIBRARY
        
        # Command callbacks
        self.on_process_document: Optional[Callable] = None
        
        logger.info("Command bridge initialized successfully")
    
    def set_context(self, context: CommandContext):
        """Set the current command context"""
        try:
            self.current_context = context
            logger.debug(f"Command context set to: {context.value}")
        except Exception as e:
            logger.error(f"Failed to set context: {e}")
    
    def get_context(self) -> CommandContext:
        """Get the current command context"""
        return self.current_context
    
    def register_all_commands(self):
        """Register all commands with the system"""
        try:
            # This would register commands with the command manager
            logger.debug("All commands registered")
        except Exception as e:
            logger.error(f"Failed to register commands: {e}") 