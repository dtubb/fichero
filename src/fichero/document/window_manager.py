"""
Document Window Position Management
Handles saving and restoring window positions for documents
"""

import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class DocumentWindowManager:
    """Manages window position and size for documents"""
    
    def __init__(self, document):
        self.document = document
    
    def save_window_position(self, position: Tuple[int, int], size: Optional[Tuple[int, int]] = None):
        """Save window position and size to document config"""
        if "window_settings" not in self.document.state_manager.document_config:
            self.document.state_manager.document_config["window_settings"] = {}
        
        self.document.state_manager.document_config["window_settings"]["position"] = list(position)
        if size:
            self.document.state_manager.document_config["window_settings"]["size"] = list(size)
        
        self.document.mark_modified()
        logger.debug(f"Saved window position: {position}")
    
    def get_window_position(self) -> Tuple[int, int]:
        """Get saved window position"""
        settings = self.document.state_manager.document_config.get("window_settings", {})
        return tuple(settings.get("position", [100, 100]))
    
    def get_window_size(self) -> Tuple[int, int]:
        """Get saved window size"""
        settings = self.document.state_manager.document_config.get("window_settings", {})
        return tuple(settings.get("size", [650, None]))
    
    def save_current_window_position(self):
        """Save current window position from the document window"""
        try:
            if hasattr(self.document, 'main_window') and self.document.main_window:
                # Get position and size from the window
                position = getattr(self.document.main_window, 'position', None)
                size = getattr(self.document.main_window, 'size', None)
                
                if position and size:
                    self.save_window_position(position, size)
                    logger.debug(f"Saved window position: {position}, size: {size}")
        except Exception as e:
            logger.warning(f"Failed to save window position: {e}")
    
    def restore_window_position(self):
        """Restore window position after reset or window creation"""
        try:
            if hasattr(self.document, 'main_window') and self.document.main_window:
                saved_position = self.get_window_position()
                saved_size = self.get_window_size()
                
                # Apply saved position and size
                if hasattr(self.document.main_window, 'position') and saved_position != (100, 100):
                    self.document.main_window.position = saved_position
                    logger.debug(f"Restored window position: {saved_position}")
                
                if hasattr(self.document.main_window, 'size') and saved_size != (650, None):
                    self.document.main_window.size = saved_size
                    logger.debug(f"Restored window size: {saved_size}")
                    
        except Exception as e:
            logger.warning(f"Failed to restore window position: {e}")
    
    def add_open_file(self, file_path: str):
        """Add a file to the open files list"""
        if "window_settings" not in self.document.state_manager.document_config:
            self.document.state_manager.document_config["window_settings"] = {}
        if "open_files" not in self.document.state_manager.document_config["window_settings"]:
            self.document.state_manager.document_config["window_settings"]["open_files"] = []
        
        # Remove if already exists to avoid duplicates
        open_files = self.document.state_manager.document_config["window_settings"]["open_files"]
        if file_path in open_files:
            open_files.remove(file_path)
        
        # Add to beginning of list
        open_files.insert(0, file_path)
        
        # Keep only last 10 open files
        self.document.state_manager.document_config["window_settings"]["open_files"] = open_files[:10]
        
        self.document.mark_modified()
        logger.debug(f"Added open file: {file_path}")
    
    def remove_open_file(self, file_path: str):
        """Remove a file from the open files list"""
        if "window_settings" in self.document.state_manager.document_config and "open_files" in self.document.state_manager.document_config["window_settings"]:
            open_files = self.document.state_manager.document_config["window_settings"]["open_files"]
            if file_path in open_files:
                open_files.remove(file_path)
                self.document.mark_modified()
                logger.debug(f"Removed open file: {file_path}")
    
    def get_open_files(self) -> list:
        """Get list of open files"""
        return self.document.state_manager.document_config.get("window_settings", {}).get("open_files", []) 