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


def _get_backend_from_settings(settings) -> Optional[str]:
    """Extract backend preference from settings object"""
    if not settings:
        return None
    
    try:
        # Handle AppSettings object
        if hasattr(settings, 'get_backend_type'):
            backend_setting = settings.get_backend_type()
            return _convert_backend_setting(backend_setting)
        
        # Handle dict-like settings
        if hasattr(settings, 'settings'):
            backend_setting = settings.settings.get("workers", {}).get("backend", "python")
            return _convert_backend_setting(backend_setting)
        
        # Handle raw dict
        if isinstance(settings, dict):
            backend_setting = settings.get("workers", {}).get("backend", "python")
            return _convert_backend_setting(backend_setting)
            
    except Exception as e:
        logger.debug(f"Could not extract backend from settings: {e}")
    
    return None


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
        """Select the best available backend, coordinating with director backend"""
        
        # Force specific backend if requested
        if prefer_backend == "manager":
            logger.info("Using Manager backend (forced)")
            return ManagerStorageBackend(self.namespace, self.data_dir, self.app)
        
        if prefer_backend == "redis":
            if not REDIS_AVAILABLE:
                logger.warning("Redis backend requested but redis package not available, falling back to Manager")
                return ManagerStorageBackend(self.namespace, self.data_dir, self.app)
            
            # Try Redis with same fallback logic as director
            try:
                logger.info("Using Redis backend (coordinated with director)")
                return RedisStorageBackend(self.namespace, self.data_dir, self.redis_url, self.app)
            except Exception as e:
                logger.warning(f"Redis backend failed: {e}, falling back to Manager (coordinated with director)")
                return ManagerStorageBackend(self.namespace, self.data_dir, self.app)
        
        # Auto-select with coordination
        if _should_coordinate_with_director_backend():
            # Check if director already made a backend choice
            director_backend = _get_director_actual_backend()
            if director_backend:
                logger.info(f"Coordinating with director's actual backend: {director_backend}")
                if director_backend == "redis" and REDIS_AVAILABLE:
                    try:
                        return RedisStorageBackend(self.namespace, self.data_dir, self.redis_url, self.app)
                    except Exception as e:
                        logger.warning(f"Redis backend failed during coordination: {e}")
                        return ManagerStorageBackend(self.namespace, self.data_dir, self.app)
                else:
                    logger.info(f"Director using {director_backend}, using Manager backend for coordination")
                    return ManagerStorageBackend(self.namespace, self.data_dir, self.app)
            
            # Director not initialized yet, try Redis first (director will coordinate later)
            elif REDIS_AVAILABLE:
                try:
                    logger.info("Attempting Redis backend (director will coordinate)...")
                    return RedisStorageBackend(self.namespace, self.data_dir, self.redis_url, self.app)
                except Exception as e:
                    logger.warning(f"Redis backend failed: {e}")
                    logger.info("Falling back to Manager backend (director will coordinate)")
            else:
                logger.info("Redis not available, using Manager backend")
        else:
            logger.info("Backend coordination disabled, using Manager backend")
        
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
                      redis_url: str = "redis://localhost:6379", app=None, 
                      settings=None) -> SharedDataManager:
    """Force reload of shared data manager
    
    Args:
        namespace: Namespace for keys
        data_dir: Directory for persistence files  
        auto_save: Enable automatic saving (Manager backend only)
        prefer_backend: Force specific backend ("redis" or "manager")
        redis_url: Redis connection URL
        app: Toga app instance (for proper data directory)
        settings: Settings object to extract backend preference from
    """
    global _shared_data
    
    # If settings provided but no backend preference, extract from settings
    if settings and prefer_backend is None:
        prefer_backend = _get_backend_from_settings(settings)
    
    _shared_data = SharedDataManager(namespace, data_dir, prefer_backend, redis_url, app)
    if auto_save:
        _shared_data.auto_save()
    return _shared_data 

def _should_coordinate_with_director_backend() -> bool:
    """
    Check if we should coordinate backend selection with director.
    
    This ensures both director and shared data use the same underlying infrastructure:
    - If director uses Celery/Redis for processing → shared data uses Redis for storage
    - If director uses Python/Manager for processing → shared data uses Manager for storage
    
    This prevents mismatched configurations where processing and storage use different systems.
    """
    return True  # Always coordinate for consistency


def _get_director_actual_backend() -> Optional[str]:
    """
    Get the actual backend that the director is using (after fallbacks).
    
    This allows shared data to coordinate with the director's actual backend choice,
    not just the settings preference. If director falls back from Redis to Python,
    shared data should also fall back from Redis to Manager.
    
    Returns:
        "redis" if director is using Celery/Redis, "manager" if using Python, None if unknown
    """
    try:
        # Try to get the director instance if it exists
        from ..director import FicheroDirector
        
        if FicheroDirector.is_initialized():
            director = FicheroDirector.get_instance()
            if director and director.backend:
                backend_name = director.backend.backend_name.lower()
                if "redis" in backend_name or "celery" in backend_name:
                    return "redis"
                elif "python" in backend_name or "multiprocessing" in backend_name:
                    return "manager"
        
        return None  # Director not initialized or backend unknown
        
    except Exception as e:
        logger.debug(f"Could not determine director backend: {e}")
        return None 