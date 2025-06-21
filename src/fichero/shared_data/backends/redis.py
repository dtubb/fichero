"""
Redis Backend for SharedDataManager
Provides Redis-based storage for cross-process communication
"""

import json
import logging
from typing import Dict, Optional, Any, List
from pathlib import Path

try:
    import redis
except ImportError:
    redis = None

from .base import DataType, BaseStorageBackend

logger = logging.getLogger(__name__)


class RedisStorageBackend(BaseStorageBackend):
    """Redis backend for shared data storage"""
    
    def __init__(self, namespace: str = "fichero", default_ttl: Optional[int] = None, 
                 data_dir: Optional[Path] = None, redis_url: str = "redis://localhost:6379"):
        super().__init__(namespace, default_ttl, data_dir)
        self.redis_url = redis_url
        self.backend_name = "redis"
        self._connect()
    
    def _connect(self):
        """Connect to Redis"""
        if not redis:
            raise ImportError("Redis package not available. Install with: pip install redis")
        
        try:
            self.redis = redis.Redis.from_url(self.redis_url, decode_responses=False)
            self.redis.ping()
            logger.info(f"Connected to Redis at {self.redis_url}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}")
    
    def set(self, data_type: DataType, key: str, value: Any, ttl: Optional[int] = None, 
            immediate_save: bool = False) -> bool:
        """Set data in Redis"""
        try:
            namespaced_key = self._make_key(data_type, key)
            serialized_value = self._serialize(value)
            effective_ttl = ttl or self.default_ttl
            
            if effective_ttl:
                result = self.redis.setex(namespaced_key, effective_ttl, serialized_value)
            else:
                result = self.redis.set(namespaced_key, serialized_value)
            
            # Redis auto-persists, so immediate_save is ignored
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to set {data_type.value} key {key}: {e}")
            return False
    
    def get(self, data_type: DataType, key: str, default: Any = None) -> Any:
        """Get data from Redis"""
        try:
            namespaced_key = self._make_key(data_type, key)
            val = self.redis.get(namespaced_key)
            if val is None:
                return default
            return self._deserialize(val.decode() if isinstance(val, bytes) else val)
        except Exception as e:
            logger.error(f"Failed to get {data_type.value} key {key}: {e}")
            return default
    
    def delete(self, data_type: DataType, key: str) -> bool:
        """Delete data from Redis"""
        try:
            namespaced_key = self._make_key(data_type, key)
            return bool(self.redis.delete(namespaced_key))
        except Exception as e:
            logger.error(f"Failed to delete {data_type.value} key {key}: {e}")
            return False
    
    def keys(self, data_type: DataType, pattern: str = "*") -> List[str]:
        """List keys for a data type in Redis"""
        try:
            namespaced_pattern = self._make_key(data_type, pattern)
            keys = self.redis.keys(namespaced_pattern)
            prefix = f"{self.namespace}:{data_type.value}:"
            return [key.decode().replace(prefix, "", 1) for key in keys]
        except Exception as e:
            logger.error(f"Failed to get {data_type.value} keys: {e}")
            return []
    
    def get_info(self) -> Dict[str, Any]:
        """Get Redis backend information"""
        info = super().get_info()
        
        try:
            redis_info = self.redis.info()
            info.update({
                "redis_url": self.redis_url,
                "redis_version": redis_info.get("redis_version"),
                "used_memory": redis_info.get("used_memory_human"),
                "connected_clients": redis_info.get("connected_clients"),
            })
        except Exception as e:
            logger.error(f"Failed to get Redis info: {e}")
            info["error"] = str(e)
        
        return info
    
    def clear_data_type(self, data_type: DataType) -> bool:
        """Clear all data for a specific type in Redis"""
        try:
            keys_to_delete = self.keys(data_type)
            if keys_to_delete:
                namespaced_keys = [self._make_key(data_type, key) for key in keys_to_delete]
                self.redis.delete(*namespaced_keys)
            return True
        except Exception as e:
            logger.error(f"Failed to clear {data_type.value} data: {e}")
            return False
    
    def save_to_disk(self, data_type: Optional[DataType] = None):
        """Redis handles persistence automatically"""
        logger.info("Redis backend handles persistence automatically")
    
    def auto_save(self, interval: int = 300):
        """Redis handles persistence automatically"""
        logger.info("Redis backend handles persistence automatically") 