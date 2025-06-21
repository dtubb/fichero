"""
SharedDataManager Factory
Automatically selects between Redis and Python Manager backends
"""

import logging
import yaml
from pathlib import Path
from typing import Optional

from .backends.base import DataType, BaseStorageBackend

logger = logging.getLogger(__name__)


def _get_backend_preference() -> Optional[str]:
    """Get user's backend preference from settings, avoiding circular dependencies"""
    try:
        # Try to get settings without triggering circular dependency
        # We'll read the file directly if app settings aren't available yet
        from pathlib import Path
        import platform
        import yaml
        
        # Try to get from already-loaded app settings first
        try:
            # Only import if it's safe (won't trigger circular dependency)
            from ..config.core.settings import _app_settings
            if _app_settings is not None and hasattr(_app_settings, 'settings'):
                backend_setting = _app_settings.settings.get("workers", {}).get("backend", "python")
                return _convert_backend_setting(backend_setting)
        except:
            pass  # Settings not loaded yet, continue to file read
        
        # Fallback: try to read directly from settings file
        try:
            # Use Toga-compatible path discovery for settings
            from .backends.base import discover_app_data_directory
            
            # Get proper app data directory using Toga path discovery
            app_data_dir = discover_app_data_directory(app=None)
            
            # Look for user settings files and defaults
            settings_dir = app_data_dir / "settings"
            settings_paths = []
            
            # Add all user settings files in the settings directory
            if settings_dir.exists():
                for settings_file in settings_dir.glob("*.yml"):
                    if settings_file.name != "Default Settings.yml":  # User files first
                        settings_paths.append(settings_file)
                # Add default settings as fallback
                settings_paths.append(settings_dir / "Default Settings.yml")
            
            # Add bundled defaults as final fallback
            settings_paths.append(Path(__file__).parent.parent / "resources" / "config_defaults" / "settings" / "Default Settings.yml")
            
            for settings_path in settings_paths:
                if settings_path.exists():
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        settings_data = yaml.safe_load(f)
                        backend_setting = settings_data.get("workers", {}).get("backend", "python")
                        return _convert_backend_setting(backend_setting)
        except:
            pass  # File reading failed, use defaults
        
        # Final fallback: default to Python (manager) backend
        return "manager"
        
    except Exception as e:
        logger.debug(f"Could not determine backend preference: {e}")
        return None


def _convert_backend_setting(setting: str) -> Optional[str]:
    """Convert settings value to backend preference"""
    if setting == "redis":
        return "redis"
    else:  # "python" or anything else, default to manager
        return "manager"


# Try to import Redis backend
try:
    from .backends.redis import RedisStorageBackend
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Import Manager backend (always available)
from .backends.manager import ManagerStorageBackend


class SharedDataManager:
    """Factory class that automatically selects the best available backend
    
    Backend Selection:
    1. Redis (if available and connection successful)
    2. Python Manager (always available as fallback)
    
    Both backends provide the same interface and functionality.
    """
    
    def __init__(self, namespace: str = "fichero", data_dir: Optional[Path] = None, 
                 prefer_backend: Optional[str] = None, redis_url: str = "redis://localhost:6379",
                 app=None):
        self.namespace = namespace
        self.data_dir = data_dir
        self.redis_url = redis_url
        self.app = app
        
        # Select backend
        self.backend = self._select_backend(prefer_backend)
        
        # Delegate all operations to the selected backend
        self._delegate_methods()
    
    def _select_backend(self, prefer_backend: Optional[str] = None) -> BaseStorageBackend:
        """Select the best available backend"""
        
        # Force specific backend if requested
        if prefer_backend == "manager":
            logger.info("Using Manager backend (forced)")
            return ManagerStorageBackend(self.namespace, self.data_dir, self.app)
        
        if prefer_backend == "redis":
            if not REDIS_AVAILABLE:
                raise ImportError("Redis backend requested but redis package not available")
            logger.info("Using Redis backend (forced)")
            return RedisStorageBackend(self.namespace, self.data_dir, self.redis_url, self.app)
        
        # Auto-select best backend
        if REDIS_AVAILABLE:
            try:
                logger.info("Attempting Redis backend...")
                return RedisStorageBackend(self.namespace, self.data_dir, self.redis_url, self.app)
            except Exception as e:
                logger.warning(f"Redis backend failed: {e}")
                logger.info("Falling back to Manager backend")
        else:
            logger.info("Redis not available, using Manager backend")
        
        return ManagerStorageBackend(self.namespace, self.data_dir, self.app)
    
    def _delegate_methods(self):
        """Delegate all methods to the selected backend"""
        # Core operations
        self.set = self.backend.set
        self.get = self.backend.get
        self.delete = self.backend.delete
        self.keys = self.backend.keys
        self.clear_data_type = self.backend.clear_data_type
        
        # Convenience methods
        self.set_setting = self.backend.set_setting
        self.get_setting = self.backend.get_setting
        self.delete_setting = self.backend.delete_setting
        self.list_settings = self.backend.list_settings
        
        # Utility methods
        self.get_info = self.backend.get_info
        self.save_to_disk = self.backend.save_to_disk
        self.auto_save = self.backend.auto_save
    
    @property
    def backend_name(self) -> str:
        """Get the name of the selected backend"""
        return self.backend.backend_name


# Global shared data manager instance
_shared_data = None

def get_shared_data(namespace: str = "fichero", data_dir: Optional[Path] = None, 
                   auto_save: bool = True, prefer_backend: Optional[str] = None,
                   redis_url: str = "redis://localhost:6379", app=None) -> SharedDataManager:
    """Get global shared data manager instance
    
    Args:
        namespace: Namespace for keys
        data_dir: Directory for persistence files
        auto_save: Enable automatic saving (Manager backend only)
        prefer_backend: Force specific backend ("redis" or "manager")
        redis_url: Redis connection URL
        app: Toga app instance (for proper data directory)
    """
    global _shared_data
    if _shared_data is None:
        # If no backend preference specified, try to get it from settings
        if prefer_backend is None:
            prefer_backend = _get_backend_preference()
        
        _shared_data = SharedDataManager(namespace, data_dir, prefer_backend, redis_url, app)
        if auto_save:
            _shared_data.auto_save()
    return _shared_data

def reload_shared_data(namespace: str = "fichero", data_dir: Optional[Path] = None,
                      auto_save: bool = True, prefer_backend: Optional[str] = None,
                      redis_url: str = "redis://localhost:6379", app=None) -> SharedDataManager:
    """Force reload of shared data manager"""
    global _shared_data
    _shared_data = SharedDataManager(namespace, data_dir, prefer_backend, redis_url, app)
    if auto_save:
        _shared_data.auto_save()
    return _shared_data 