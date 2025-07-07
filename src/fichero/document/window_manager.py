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