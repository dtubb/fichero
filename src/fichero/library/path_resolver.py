"""
Library Path Resolver

Centralized utility to determine the library database path.
Ensures CLI, GUI, and tests all use the same location by following a consistent hierarchy:
1. Settings file (library.path)
2. App paths (if available)
3. Standard fallback location
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_library_path(app=None) -> Path:
    """
    Get the library database path using consistent hierarchy.
    
    Priority:
    1. Settings file (library.path setting)
    2. App paths (app.paths.data/library if available)
    3. Standard fallback (~/Library/Application Support/ca.tubb.fichero/library)
    
    Args:
        app: Toga app instance (optional)
        
    Returns:
        Path to library directory (parent of library.db)
    """
    try:
        # 1. Try to get from settings first
        library_path = _get_path_from_settings(app)
        if library_path:
            logger.info(f"Using library path from settings: {library_path}")
            return library_path
        
        # 2. Try to get from app paths
        library_path = _get_path_from_app_paths(app)
        if library_path:
            logger.info(f"Using library path from app paths: {library_path}")
            return library_path
        
        # 3. Use standard fallback
        fallback_path = _get_fallback_path()
        logger.info(f"Using fallback library path: {fallback_path}")
        return fallback_path
        
    except Exception as e:
        logger.error(f"Error determining library path: {e}")
        fallback_path = _get_fallback_path()
        logger.info(f"Using fallback library path due to error: {fallback_path}")
        return fallback_path


def _get_path_from_settings(app) -> Optional[Path]:
    """Try to get library path from settings"""
    try:
        # Import here to avoid circular dependencies
        from fichero.config.core.settings import get_app_settings
        
        settings = get_app_settings(app)
        path_str = settings.get_setting('library.path')
        
        if path_str and path_str.strip():
            path = Path(path_str)
            logger.debug(f"Found library path in settings: {path}")
            return path
        
        logger.debug("No library path found in settings")
        return None
        
    except Exception as e:
        logger.debug(f"Could not get library path from settings: {e}")
        return None


def _get_path_from_app_paths(app) -> Optional[Path]:
    """Try to get library path from app paths"""
    try:
        # First check if app has a get_library_path method (for testing)
        if app and hasattr(app, 'get_library_path') and callable(app.get_library_path):
            db_path = app.get_library_path()
            if db_path:
                # If it's a .db file, return parent directory
                path = Path(db_path)
                if path.suffix == '.db':
                    path = path.parent
                logger.debug(f"Found library path from app.get_library_path(): {path}")
                return path

        if app and hasattr(app, 'paths') and hasattr(app.paths, 'data'):
            path = app.paths.data / "library"
            logger.debug(f"Found library path from app paths: {path}")
            return path

        # Try to get from Toga app if not provided
        try:
            import toga
            toga_app = toga.App.app
            if toga_app and hasattr(toga_app, 'paths') and hasattr(toga_app.paths, 'data'):
                path = toga_app.paths.data / "library"
                logger.debug(f"Found library path from Toga app paths: {path}")
                return path
        except Exception:
            pass

        logger.debug("No app paths available")
        return None

    except Exception as e:
        logger.debug(f"Could not get library path from app paths: {e}")
        return None


def _get_fallback_path() -> Path:
    """Get the standard fallback library path"""
    return Path.home() / "Library" / "Application Support" / "ca.tubb.fichero" / "library"


def get_library_database_path(app=None) -> Path:
    """
    Get the full path to the library database file.
    
    Args:
        app: Toga app instance (optional)
        
    Returns:
        Path to library.db file
    """
    library_dir = get_library_path(app)
    return library_dir / "library.db" 