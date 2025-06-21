"""
App Preferences Manager
Handles non-user-editable app state like active settings file, window positions, etc.
This is separate from user settings to avoid circular dependencies.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def discover_app_data_directory(app=None) -> Path:
    """
    Discover the app data directory using Toga-compatible approach
    
    This follows the same pattern as shared_data backends:
    1. Use app.paths.data if available (Toga app context)
    2. Try to find existing Toga data directory
    3. Fallback to user home directory
    """
    # 1. Use Toga app paths if available
    if app and hasattr(app, 'paths') and hasattr(app.paths, 'data'):
        return app.paths.data
    
    # 2. Try to find existing Toga data directories
    # Toga typically creates directories in platform-specific locations
    try:
        import platform
        import glob
        
        if platform.system() == "Darwin":  # macOS
            # Look for any existing Fichero app data in standard location
            app_support = Path.home() / "Library" / "Application Support"
            if app_support.exists():
                # Look for directories that might be Fichero's
                patterns = [
                    "*.fichero*",  # Any directory containing "fichero"
                    "*fichero*",   # Case variations
                    "*Fichero*"
                ]
                for pattern in patterns:
                    matches = list(app_support.glob(pattern))
                    for match in matches:
                        if match.is_dir():
                            # Check if it looks like a Fichero data directory
                            if (match / "app_preferences.json").exists() or \
                               (match / "settings").exists() or \
                               (match / "shared_data").exists():
                                return match
        
        elif platform.system() == "Windows":
            # Windows: %APPDATA%
            appdata = Path.home() / "AppData" / "Roaming"
            if appdata.exists():
                for pattern in ["*fichero*", "*Fichero*"]:
                    matches = list(appdata.glob(pattern))
                    for match in matches:
                        if match.is_dir() and (match / "app_preferences.json").exists():
                            return match
        
        elif platform.system() == "Linux":
            # Linux: ~/.local/share
            local_share = Path.home() / ".local" / "share"
            if local_share.exists():
                for pattern in ["*fichero*", "*Fichero*"]:
                    matches = list(local_share.glob(pattern))
                    for match in matches:
                        if match.is_dir() and (match / "app_preferences.json").exists():
                            return match
    
    except Exception as e:
        logger.debug(f"Could not discover existing app data directory: {e}")
    
    # 3. Fallback to user home directory (same as shared_data backend)
    return Path.home() / ".fichero"


class AppPreferences:
    """Manages app preferences and state that users don't directly edit"""
    
    def __init__(self, app=None):
        self.app = app
        self._preferences_file = self._get_preferences_file_path()
        self._preferences = self._load_preferences()
    
    def _get_preferences_file_path(self) -> Path:
        """Get the path to the app preferences file"""
        app_data_dir = discover_app_data_directory(self.app)
        return app_data_dir / "app_preferences.json"
    
    def _load_preferences(self) -> Dict[str, Any]:
        """Load preferences from file"""
        try:
            if self._preferences_file.exists():
                with open(self._preferences_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load app preferences: {e}")
        
        # Return default preferences
        return {
            "active_settings_file": None,
            "window_positions": {},
            "recent_documents": [],
            "open_documents": [],
            "last_used_directories": {}
        }
    
    def _save_preferences(self) -> bool:
        """Save preferences to file"""
        try:
            # Ensure directory exists
            self._preferences_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self._preferences_file, 'w', encoding='utf-8') as f:
                json.dump(self._preferences, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Failed to save app preferences: {e}")
            return False
    
    def get_active_settings_file(self) -> Optional[Path]:
        """Get the currently active settings file path"""
        active_file = self._preferences.get("active_settings_file")
        if active_file:
            path = Path(active_file)
            if path.exists():
                return path
        return None
    
    def set_active_settings_file(self, file_path: Optional[Path]) -> bool:
        """Set the active settings file path"""
        try:
            self._preferences["active_settings_file"] = str(file_path) if file_path else None
            return self._save_preferences()
        except Exception as e:
            logger.error(f"Failed to set active settings file: {e}")
            return False
    
    def get_window_position(self, window_id: str) -> Optional[Dict[str, Any]]:
        """Get saved window position
        
        Args:
            window_id: Unique identifier for the window (e.g., "main", "document_123", "preferences")
            
        Returns:
            Dictionary with position info like {"x": 100, "y": 100, "width": 800, "height": 600}
            or None if no position saved
        """
        return self._preferences.get("window_positions", {}).get(window_id)
    
    def set_window_position(self, window_id: str, position: Dict[str, Any]) -> bool:
        """Save window position
        
        Args:
            window_id: Unique identifier for the window
            position: Dictionary with position info like {"x": 100, "y": 100, "width": 800, "height": 600}
            
        Example usage in window class:
            # On window close/move:
            app_prefs = get_app_preferences(self.app)
            app_prefs.set_window_position("main", {
                "x": self.position[0], "y": self.position[1],
                "width": self.size[0], "height": self.size[1]
            })
            
            # On window creation:
            saved_pos = app_prefs.get_window_position("main")
            if saved_pos:
                self.position = (saved_pos["x"], saved_pos["y"])
                self.size = (saved_pos["width"], saved_pos["height"])
        """
        try:
            if "window_positions" not in self._preferences:
                self._preferences["window_positions"] = {}
            self._preferences["window_positions"][window_id] = position
            return self._save_preferences()
        except Exception as e:
            logger.error(f"Failed to save window position: {e}")
            return False
    
    def add_recent_document(self, document_path: Path) -> bool:
        """Add a document to recent documents list"""
        try:
            recent = self._preferences.get("recent_documents", [])
            doc_str = str(document_path)
            
            # Remove if already in list
            if doc_str in recent:
                recent.remove(doc_str)
            
            # Add to front
            recent.insert(0, doc_str)
            
            # Keep only last 5
            self._preferences["recent_documents"] = recent[:5]
            
            return self._save_preferences()
        except Exception as e:
            logger.error(f"Failed to add recent document: {e}")
            return False
    
    def get_recent_documents(self) -> list:
        """Get list of recent documents"""
        return self._preferences.get("recent_documents", [])
    
    def set_open_documents(self, document_paths: list) -> bool:
        """Save list of currently open documents for session restoration"""
        try:
            # Convert Path objects to strings - DON'T filter by existence here
            # We want to save ALL open documents, even auto-saved ones
            # Filtering for missing files happens in get_open_documents()
            doc_strings = []
            for doc_path in document_paths:
                if doc_path:  # Only skip None values
                    doc_strings.append(str(doc_path))
            
            self._preferences["open_documents"] = doc_strings
            return self._save_preferences()
        except Exception as e:
            logger.error(f"Failed to save open documents: {e}")
            return False
    
    def get_open_documents(self) -> list:
        """Get list of documents that should be restored on startup"""
        try:
            open_docs = self._preferences.get("open_documents", [])
            # Filter to only existing files
            existing_docs = []
            for doc_str in open_docs:
                doc_path = Path(doc_str)
                if doc_path.exists():
                    existing_docs.append(doc_path)
                else:
                    logger.info(f"Skipping missing document: {doc_path}")
            return existing_docs
        except Exception as e:
            logger.error(f"Failed to get open documents: {e}")
            return []
    
    def clear_open_documents(self) -> bool:
        """Clear the list of open documents (e.g., if user chooses not to restore)"""
        try:
            self._preferences["open_documents"] = []
            return self._save_preferences()
        except Exception as e:
            logger.error(f"Failed to clear open documents: {e}")
            return False
    
    def set_last_used_directory(self, key: str, directory: Path) -> bool:
        """Set last used directory for a specific purpose"""
        try:
            if "last_used_directories" not in self._preferences:
                self._preferences["last_used_directories"] = {}
            self._preferences["last_used_directories"][key] = str(directory)
            return self._save_preferences()
        except Exception as e:
            logger.error(f"Failed to set last used directory: {e}")
            return False
    
    def get_last_used_directory(self, key: str) -> Optional[Path]:
        """Get last used directory for a specific purpose"""
        directory = self._preferences.get("last_used_directories", {}).get(key)
        if directory:
            path = Path(directory)
            if path.exists():
                return path
        return None


# Global instance
_app_preferences = None

def get_app_preferences(app=None) -> AppPreferences:
    """Get global app preferences instance"""
    global _app_preferences
    if _app_preferences is None:
        _app_preferences = AppPreferences(app)
    return _app_preferences 