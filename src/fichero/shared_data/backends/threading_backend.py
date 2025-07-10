"""
Threading Backend for SharedDataManager
Provides thread-safe dict storage with TTL and persistence - no subprocess needed!
"""

import time
import logging
import srsly
import threading
import atexit
from typing import Dict, Optional, Any, List
from pathlib import Path
from collections import defaultdict

from .base import DataType, BaseStorageBackend

logger = logging.getLogger(__name__)


class ThreadingStorageBackend(BaseStorageBackend):
    """Thread-safe backend for shared data storage with persistence"""
    
    def __init__(self, namespace: str = "fichero", data_dir: Optional[Path] = None, app=None):
        # Don't call super().__init__ to avoid creating shared_data directory
        self.namespace = namespace
        self.app = app
        self.backend_name = "threading"
        
        # No data_dir needed for in-memory only backend
        self.data_dir = None
        
        # Thread-safe storage - just a regular dict with RLock
        self.store: Dict[str, Any] = {}
        self._lock = threading.RLock()
        
        # TTL tracking
        self._ttl_data: Dict[str, float] = {}  # key -> expiry_time
        
        # For Python backend: no persistence needed (in-memory only)
        # self._load_persisted_data()  # Disabled for security
        
        # Auto-cleanup of expired keys
        self._start_cleanup_thread()
        
        # Register cleanup on exit
        atexit.register(self.cleanup)
        
        logger.info("SharedDataManager using thread-safe dict backend (no subprocess, no persistence!)")
    
    def _start_cleanup_thread(self):
        """Start background thread to clean up expired keys"""
        def cleanup_expired():
            while True:
                try:
                    current_time = time.time()
                    with self._lock:
                        expired_keys = [
                            key for key, expiry in self._ttl_data.items() 
                            if expiry <= current_time
                        ]
                        for key in expired_keys:
                            if key in self.store:
                                del self.store[key]
                            del self._ttl_data[key]
                        
                        if expired_keys:
                            logger.debug(f"Cleaned up {len(expired_keys)} expired keys")
                    
                    time.sleep(30)  # Check every 30 seconds
                except Exception as e:
                    logger.error(f"Error in cleanup thread: {e}")
                    time.sleep(60)  # Back off on error
        
        cleanup_thread = threading.Thread(target=cleanup_expired, daemon=True, name="shared-data-cleanup")
        cleanup_thread.start()
    
    def set(self, data_type: DataType, key: str, value: Any, immediate_save: bool = False, ttl: Optional[int] = None) -> bool:
        """Set data in thread-safe store"""
        try:
            with self._lock:
                namespaced_key = self._make_key(data_type, key)
                serialized_value = self._serialize(value)
                
                self.store[namespaced_key] = serialized_value
                
                # Set TTL if provided
                if ttl:
                    self._ttl_data[namespaced_key] = time.time() + ttl
                
                # Immediate save for critical data
                if immediate_save:
                    self.save_to_disk(data_type)
            
            return True
        except Exception as e:
            logger.error(f"Failed to set {data_type.value} key {key}: {e}")
            return False
    
    def get(self, data_type: DataType, key: str, default: Any = None) -> Any:
        """Get data from thread-safe store"""
        try:
            with self._lock:
                namespaced_key = self._make_key(data_type, key)
                
                # Check if expired
                if namespaced_key in self._ttl_data:
                    if time.time() > self._ttl_data[namespaced_key]:
                        # Key expired, remove it
                        if namespaced_key in self.store:
                            del self.store[namespaced_key]
                        del self._ttl_data[namespaced_key]
                        return default
                
                val = self.store.get(namespaced_key, default)
                if val == default:
                    return default
                return self._deserialize(val)
        except Exception as e:
            logger.error(f"Failed to get {data_type.value} key {key}: {e}")
            return default
    
    def delete(self, data_type: DataType, key: str) -> bool:
        """Delete data from thread-safe store"""
        try:
            with self._lock:
                namespaced_key = self._make_key(data_type, key)
                
                deleted = False
                if namespaced_key in self.store:
                    del self.store[namespaced_key]
                    deleted = True
                
                if namespaced_key in self._ttl_data:
                    del self._ttl_data[namespaced_key]
                    deleted = True
                
                return deleted
        except Exception as e:
            logger.error(f"Failed to delete {data_type.value} key {key}: {e}")
            return False
    
    def keys(self, data_type: DataType, pattern: str = "*") -> List[str]:
        """List keys for a data type in thread-safe store"""
        try:
            with self._lock:
                all_keys = list(self.store.keys())
                prefix = f"{self.namespace}:{data_type.value}:"
                filtered_keys = []
                
                for key in all_keys:
                    if key.startswith(prefix):
                        clean_key = key.replace(prefix, "", 1)
                        if pattern == "*" or pattern in clean_key:
                            # Check if expired
                            if key in self._ttl_data and time.time() > self._ttl_data[key]:
                                continue
                            filtered_keys.append(clean_key)
                
                return filtered_keys
        except Exception as e:
            logger.error(f"Failed to get {data_type.value} keys: {e}")
            return []
    
    def get_info(self) -> Dict[str, Any]:
        """Get threading backend information"""
        info = {
            "backend": self.backend_name,
            "namespace": self.namespace,
            "data_dir": "in-memory only",
            "persistence": False,
            "subprocess_count": 0  # No subprocesses!
        }
        
        try:
            with self._lock:
                info.update({
                    "total_keys": len(self.store),
                    "ttl_keys": len(self._ttl_data),
                })
                
                # Count by data type
                from .base import DataType
                for data_type in DataType:
                    try:
                        count = len(self.keys(data_type))
                        info[f"{data_type.value}_count"] = count
                    except Exception:
                        info[f"{data_type.value}_count"] = 0
                        
        except Exception as e:
            logger.error(f"Failed to get threading info: {e}")
            info["error"] = str(e)
        
        return info
    
    def clear_data_type(self, data_type: DataType) -> bool:
        """Clear all data for a specific type"""
        try:
            with self._lock:
                keys_to_delete = self.keys(data_type)
                for key in keys_to_delete:
                    self.delete(data_type, key)
                return True
        except Exception as e:
            logger.error(f"Failed to clear {data_type.value} data: {e}")
            return False
    
    def _get_persistence_file(self, data_type: DataType) -> Path:
        """Get the file path for persisting a data type - DISABLED"""
        raise NotImplementedError("Threading backend doesn't support persistence")
    
    def _load_persisted_data(self):
        """Load persisted data from disk on startup"""
        try:
            for data_type in DataType:
                persistence_file = self._get_persistence_file(data_type)
                if persistence_file.exists():
                    try:
                        entries = list(srsly.read_jsonl(persistence_file))
                        logger.info(f"Loading {len(entries)} {data_type.value} entries from {persistence_file}")
                        
                        for entry in entries:
                            key = entry.get("key")
                            value = entry.get("value")
                            
                            if not key:
                                continue
                            
                            namespaced_key = self._make_key(data_type, key)
                            self.store[namespaced_key] = self._serialize(value)
                                    
                    except Exception as e:
                        logger.warning(f"Failed to load {data_type.value} data from {persistence_file}: {e}")
        except Exception as e:
            logger.warning(f"Failed to load persisted data: {e}")
    
    def save_to_disk(self, data_type: Optional[DataType] = None):
        """Save data to disk - DISABLED for security (in-memory only)"""
        logger.debug("Threading backend: disk persistence disabled for security")
        pass
    
    def auto_save(self, interval: int = 300):
        """Auto-save - DISABLED for security (in-memory only)"""
        logger.debug("Threading backend: auto-save disabled for security")
        pass
    
    def cleanup(self):
        """Clean up on shutdown - no persistence needed"""
        try:
            logger.info("Cleaning up thread-safe shared data (in-memory only)...")
            with self._lock:
                self.store.clear()
                self._ttl_data.clear()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}") 