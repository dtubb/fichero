"""
Simplified Shared Data Manager
Just what we need: Redis for Celery, Threading for main process
"""

import logging
import threading
from typing import Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class SimpleSharedData:
    """Simplified shared data - just what we need"""
    
    def __init__(self, namespace: str = "fichero", prefer_backend: Optional[str] = None):
        self.namespace = namespace
        self.backend_name = self._select_backend(prefer_backend)
        
        if self.backend_name == "redis":
            self._init_redis()
        else:
            self._init_threading()
    
    def _select_backend(self, prefer_backend: Optional[str] = None) -> str:
        """Simple backend selection"""
        if prefer_backend == "redis":
            try:
                import redis
                # Test Redis connection
                r = redis.Redis(host='localhost', port=6379, db=0)
                r.ping()
                logger.info("Using Redis backend")
                return "redis"
            except:
                logger.warning("Redis requested but not available, using threading")
                return "threading"
        
        # Default to threading (no subprocesses)
        logger.info("Using threading backend")
        return "threading"
    
    def _init_redis(self):
        """Initialize Redis backend"""
        import redis
        self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)
    
    def _init_threading(self):
        """Initialize threading backend"""
        self.store: Dict[str, Any] = {}
        self._lock = threading.RLock()
    
    def set_setting(self, key: str, value: Any) -> bool:
        """Set a setting"""
        try:
            if self.backend_name == "redis":
                namespaced_key = f"{self.namespace}:settings:{key}"
                self.redis.set(namespaced_key, str(value))
            else:
                with self._lock:
                    namespaced_key = f"{self.namespace}:settings:{key}"
                    self.store[namespaced_key] = str(value)
            return True
        except Exception as e:
            logger.error(f"Failed to set setting {key}: {e}")
            return False
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting"""
        try:
            if self.backend_name == "redis":
                namespaced_key = f"{self.namespace}:settings:{key}"
                value = self.redis.get(namespaced_key)
                if value is None:
                    return default
                return value.decode() if isinstance(value, bytes) else value
            else:
                with self._lock:
                    namespaced_key = f"{self.namespace}:settings:{key}"
                    return self.store.get(namespaced_key, default)
        except Exception as e:
            logger.error(f"Failed to get setting {key}: {e}")
            return default
    
    def list_settings(self, pattern: str = "*") -> list:
        """List settings matching pattern"""
        try:
            if self.backend_name == "redis":
                namespaced_pattern = f"{self.namespace}:settings:{pattern}"
                keys = self.redis.keys(namespaced_pattern)
                prefix = f"{self.namespace}:settings:"
                return [key.decode().replace(prefix, "", 1) for key in keys]
            else:
                with self._lock:
                    prefix = f"{self.namespace}:settings:"
                    keys = []
                    for key in self.store.keys():
                        if key.startswith(prefix):
                            clean_key = key.replace(prefix, "", 1)
                            if pattern == "*" or pattern in clean_key:
                                keys.append(clean_key)
                    return keys
        except Exception as e:
            logger.error(f"Failed to list settings: {e}")
            return []
    
    def get_info(self) -> Dict[str, Any]:
        """Get backend info"""
        info = {
            "backend": self.backend_name,
            "namespace": self.namespace,
        }
        
        if self.backend_name == "redis":
            try:
                redis_info = self.redis.info()
                info.update({
                    "redis_version": redis_info.get("redis_version"),
                    "used_memory": redis_info.get("used_memory_human"),
                    "connected_clients": redis_info.get("connected_clients"),
                })
            except:
                pass
        else:
            with self._lock:
                info["total_keys"] = len(self.store)
        
        return info


# Global instance
_shared_data = None

def get_shared_data(namespace: str = "fichero", prefer_backend: Optional[str] = None) -> SimpleSharedData:
    """Get global shared data instance"""
    global _shared_data
    if _shared_data is None:
        _shared_data = SimpleSharedData(namespace, prefer_backend)
    return _shared_data 