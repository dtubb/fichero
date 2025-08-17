"""
Version Information Manager

Handles getting version information from various sources.
"""

import logging

logger = logging.getLogger(__name__)


class VersionManager:
    """Manages version information for the about dialog"""
    
    def __init__(self, app):
        """Initialize with app reference"""
        self.app = app
    
    def get_version(self):
        """Get version from app with fallbacks"""
        try:
            # First try to get version from app
            if hasattr(self.app, 'version'):
                return self.app.version
            
            # Fallback to importing directly
            from fichero import __version__
            return __version__
            
        except Exception as e:
            logger.error(f"Failed to get version: {e}")
            return "0.0.1"  # Default version 