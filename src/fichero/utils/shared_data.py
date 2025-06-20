import os
import json
import time
import logging
import srsly
from pathlib import Path
from typing import Dict, Optional, Any, Union, List
from enum import Enum

try:
    import redis
except ImportError:
    redis = None

from multiprocessing import Manager

logger = logging.getLogger(__name__)

class DataType(Enum):
    """Types of data that can be shared across processes"""
    SETTINGS = "settings"
    # Future data types can be added here as needed:
    # PROGRESS = "progress"
    # OUTPUT = "output"
    # TASK_STATUS = "task_status"
    # COORDINATION = "coordination"
    # CACHE = "cache"
    # LOGS = "logs"

class SharedDataManager:
    """Universal shared data manager for cross-process communication
    
    Currently supports:
    - Settings (app configuration)
    
    Designed for easy expansion to support:
    - Progress tracking, output streaming, task coordination, etc.
    """
    
    def __init__(self, namespace: str = "fichero", default_ttl: Optional[int] = None, 
                 data_dir: Optional[Path] = None):
        self.namespace = namespace
        self.default_ttl = default_ttl
        self.data_dir = data_dir or Path.home() / ".fichero" / "shared_data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._init_backend()
        self._load_persisted_data()
    
    def _init_backend(self):
        """Initialize Redis or Manager backend"""
        if redis:
            try:
                self.redis = redis.Redis()
                self.redis.ping()
                self.backend = "redis"
                logger.info("SharedDataManager using Redis backend")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self._init_manager()
        else:
            self._init_manager()
    
    def _init_manager(self):
        """Initialize multiprocessing.Manager backend"""
        self.manager = Manager()
        self.store = self.manager.dict()
        self.ttl_store = self.manager.dict()
        self.backend = "manager"
        logger.info("SharedDataManager using multiprocessing.Manager backend")
    
    def _make_key(self, data_type: DataType, key: str) -> str:
        """Create namespaced key with data type"""
        return f"{self.namespace}:{data_type.value}:{key}"
    
    def _serialize(self, value: Any) -> str:
        """Serialize value to JSON"""
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError) as e:
            logger.warning(f"Serialization failed: {e}")
            return str(value)
    
    def _deserialize(self, value: str) -> Any:
        """Deserialize JSON value"""
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    
    def _is_expired(self, key: str) -> bool:
        """Check if key is expired (Manager backend only)"""
        if self.backend != "manager":
            return False
        ttl_key = f"ttl:{key}"
        if ttl_key not in self.ttl_store:
            return False
        return time.time() > self.ttl_store[ttl_key]
    
    def _cleanup_expired(self, key: str) -> bool:
        """Remove expired key"""
        if self.backend == "manager" and self._is_expired(key):
            ttl_key = f"ttl:{key}"
            if key in self.store:
                del self.store[key]
            if ttl_key in self.ttl_store:
                del self.ttl_store[ttl_key]
            return True
        return False
    
    # Core data operations
    def set(self, data_type: DataType, key: str, value: Any, ttl: Optional[int] = None, 
            immediate_save: bool = False) -> bool:
        """Set any type of data"""
        try:
            namespaced_key = self._make_key(data_type, key)
            serialized_value = self._serialize(value)
            effective_ttl = ttl or self.default_ttl
            
            if self.backend == "redis":
                if effective_ttl:
                    result = self.redis.setex(namespaced_key, effective_ttl, serialized_value)
                else:
                    result = self.redis.set(namespaced_key, serialized_value)
                # Redis auto-persists, so immediate_save is ignored
                return result
            else:
                self.store[namespaced_key] = serialized_value
                if effective_ttl:
                    ttl_key = f"ttl:{namespaced_key}"
                    self.ttl_store[ttl_key] = time.time() + effective_ttl
                
                # Immediate save for critical data (like settings changes)
                if immediate_save:
                    self.save_to_disk(data_type)
                
                return True
        except Exception as e:
            logger.error(f"Failed to set {data_type.value} key {key}: {e}")
            return False
    
    def get(self, data_type: DataType, key: str, default: Any = None) -> Any:
        """Get any type of data"""
        try:
            namespaced_key = self._make_key(data_type, key)
            
            if self.backend == "redis":
                val = self.redis.get(namespaced_key)
                if val is None:
                    return default
                return self._deserialize(val.decode())
            else:
                if self._cleanup_expired(namespaced_key):
                    return default
                val = self.store.get(namespaced_key, default)
                if val == default:
                    return default
                return self._deserialize(val)
        except Exception as e:
            logger.error(f"Failed to get {data_type.value} key {key}: {e}")
            return default
    
    def delete(self, data_type: DataType, key: str) -> bool:
        """Delete any type of data"""
        try:
            namespaced_key = self._make_key(data_type, key)
            
            if self.backend == "redis":
                return bool(self.redis.delete(namespaced_key))
            else:
                success = False
                if namespaced_key in self.store:
                    del self.store[namespaced_key]
                    success = True
                ttl_key = f"ttl:{namespaced_key}"
                if ttl_key in self.ttl_store:
                    del self.ttl_store[ttl_key]
                return success
        except Exception as e:
            logger.error(f"Failed to delete {data_type.value} key {key}: {e}")
            return False
    
    def keys(self, data_type: DataType, pattern: str = "*") -> List[str]:
        """List keys for a data type"""
        try:
            if self.backend == "redis":
                namespaced_pattern = self._make_key(data_type, pattern)
                keys = self.redis.keys(namespaced_pattern)
                prefix = f"{self.namespace}:{data_type.value}:"
                return [key.decode().replace(prefix, "", 1) for key in keys]
            else:
                all_keys = list(self.store.keys())
                prefix = f"{self.namespace}:{data_type.value}:"
                filtered_keys = []
                for key in all_keys:
                    if key.startswith(prefix):
                        if not self._cleanup_expired(key):
                            clean_key = key.replace(prefix, "", 1)
                            if pattern == "*" or pattern in clean_key:
                                filtered_keys.append(clean_key)
                return filtered_keys
        except Exception as e:
            logger.error(f"Failed to get {data_type.value} keys: {e}")
            return []
    
    # Settings operations (convenience methods)
    def set_setting(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a setting value"""
        return self.set(DataType.SETTINGS, key, value, ttl)
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value"""
        return self.get(DataType.SETTINGS, key, default)
    
    def delete_setting(self, key: str) -> bool:
        """Delete a setting"""
        return self.delete(DataType.SETTINGS, key)
    
    def list_settings(self, pattern: str = "*") -> List[str]:
        """List all settings matching pattern"""
        return self.keys(DataType.SETTINGS, pattern)
    
    # Utility methods
    def get_info(self) -> Dict[str, Any]:
        """Get information about the shared data manager"""
        info = {
            "backend": self.backend,
            "namespace": self.namespace,
            "default_ttl": self.default_ttl,
        }
        
        try:
            if self.backend == "redis":
                redis_info = self.redis.info()
                info.update({
                    "redis_version": redis_info.get("redis_version"),
                    "used_memory": redis_info.get("used_memory_human"),
                    "connected_clients": redis_info.get("connected_clients"),
                })
            else:
                info.update({
                    "total_keys": len(self.store),
                    "total_ttl_entries": len(self.ttl_store),
                })
            
            # Count by data type
            for data_type in DataType:
                count = len(self.keys(data_type))
                info[f"{data_type.value}_count"] = count
                
        except Exception as e:
            logger.error(f"Failed to get info: {e}")
            info["error"] = str(e)
        
        return info
    
    def clear_data_type(self, data_type: DataType) -> bool:
        """Clear all data for a specific type"""
        try:
            keys_to_delete = self.keys(data_type)
            for key in keys_to_delete:
                self.delete(data_type, key)
            return True
        except Exception as e:
            logger.error(f"Failed to clear {data_type.value} data: {e}")
            return False
    
    # Persistence methods
    def _get_persistence_file(self, data_type: DataType) -> Path:
        """Get the file path for persisting a data type"""
        return self.data_dir / f"{self.namespace}_{data_type.value}.jsonl"
    
    def _load_persisted_data(self):
        """Load persisted data from disk on startup (Manager backend only)"""
        if self.backend == "redis":
            return  # Redis handles its own persistence
        
        try:
            for data_type in DataType:
                persistence_file = self._get_persistence_file(data_type)
                if persistence_file.exists():
                    try:
                        # Read JSONL format - each line is a separate entry
                        entries = list(srsly.read_jsonl(persistence_file))
                        logger.info(f"Loading {len(entries)} {data_type.value} entries from {persistence_file}")
                        
                        for entry in entries:
                            key = entry.get("key")
                            value = entry.get("value")
                            ttl = entry.get("ttl")
                            created_at = entry.get("created_at", time.time())
                            
                            if not key:
                                continue  # Skip invalid entries
                            
                            # Check if expired
                            if ttl and (time.time() - created_at) > ttl:
                                continue  # Skip expired entries
                            
                            # Store the value
                            namespaced_key = self._make_key(data_type, key)
                            self.store[namespaced_key] = self._serialize(value)
                            
                            # Set TTL if specified
                            if ttl:
                                remaining_ttl = ttl - (time.time() - created_at)
                                if remaining_ttl > 0:
                                    ttl_key = f"ttl:{namespaced_key}"
                                    self.ttl_store[ttl_key] = time.time() + remaining_ttl
                                    
                    except Exception as e:
                        logger.warning(f"Failed to load {data_type.value} data from {persistence_file}: {e}")
        except Exception as e:
            logger.warning(f"Failed to load persisted data: {e}")
    
    def save_to_disk(self, data_type: Optional[DataType] = None):
        """Save data to disk for persistence (Manager backend only)
        
        Args:
            data_type: Specific data type to save, or None to save all
        """
        if self.backend == "redis":
            logger.info("Redis backend handles persistence automatically")
            return
        
        try:
            data_types_to_save = [data_type] if data_type else list(DataType)
            
            for dt in data_types_to_save:
                persistence_file = self._get_persistence_file(dt)
                entries_to_save = []
                
                # Get all keys for this data type
                keys = self.keys(dt)
                
                for key in keys:
                    try:
                        value = self.get(dt, key)
                        if value is not None:
                            entry = {
                                "key": key,
                                "value": value,
                                "created_at": time.time()
                            }
                            
                            # Check if there's a TTL
                            namespaced_key = self._make_key(dt, key)
                            ttl_key = f"ttl:{namespaced_key}"
                            if ttl_key in self.ttl_store:
                                remaining_time = self.ttl_store[ttl_key] - time.time()
                                if remaining_time > 0:
                                    entry["ttl"] = remaining_time
                            
                            entries_to_save.append(entry)
                    except Exception as e:
                        logger.warning(f"Failed to serialize {dt.value} key {key}: {e}")
                
                # Save to JSONL file
                if entries_to_save:
                    srsly.write_jsonl(persistence_file, entries_to_save)
                    logger.info(f"Saved {len(entries_to_save)} {dt.value} entries to {persistence_file}")
                elif persistence_file.exists():
                    # Remove empty persistence files
                    persistence_file.unlink()
                    logger.info(f"Removed empty {dt.value} persistence file")
                    
        except Exception as e:
            logger.error(f"Failed to save data to disk: {e}")
    
    def auto_save(self, interval: int = 300):
        """Enable automatic saving every interval seconds (Manager backend only)
        
        Args:
            interval: Save interval in seconds (default: 5 minutes)
        """
        if self.backend == "redis":
            return  # Redis handles persistence
        
        import threading
        import atexit
        import signal
        
        def _save_periodically():
            while True:
                try:
                    time.sleep(interval)
                    self.save_to_disk()
                except Exception as e:
                    logger.error(f"Auto-save failed: {e}")
        
        def _emergency_save(signum=None, frame=None):
            """Emergency save on crash/signal"""
            try:
                logger.warning(f"Emergency save triggered (signal: {signum})")
                self.save_to_disk()
                logger.info("Emergency save completed")
            except Exception as e:
                logger.error(f"Emergency save failed: {e}")
        
        # Start background thread for periodic saving
        save_thread = threading.Thread(target=_save_periodically, daemon=True)
        save_thread.start()
        
        # Register emergency save handlers
        atexit.register(self.save_to_disk)  # Normal exit
        
        # Handle common crash signals
        try:
            signal.signal(signal.SIGTERM, _emergency_save)  # Termination
            signal.signal(signal.SIGINT, _emergency_save)   # Ctrl+C
            if hasattr(signal, 'SIGHUP'):
                signal.signal(signal.SIGHUP, _emergency_save)   # Hangup
        except Exception as e:
            logger.warning(f"Could not register signal handlers: {e}")
        
        logger.info(f"Auto-save enabled: every {interval} seconds with crash protection")

# Global shared data manager instance
_shared_data = None

def get_shared_data(namespace: str = "fichero", default_ttl: Optional[int] = None, 
                   data_dir: Optional[Path] = None, auto_save: bool = True) -> SharedDataManager:
    """Get global shared data manager instance
    
    Args:
        namespace: Namespace for keys
        default_ttl: Default time-to-live in seconds
        data_dir: Directory for persistence files
        auto_save: Enable automatic saving (Manager backend only)
    """
    global _shared_data
    if _shared_data is None:
        _shared_data = SharedDataManager(namespace, default_ttl, data_dir)
        if auto_save:
            _shared_data.auto_save()
    return _shared_data

def reload_shared_data(namespace: str = "fichero", default_ttl: Optional[int] = None,
                      data_dir: Optional[Path] = None, auto_save: bool = True) -> SharedDataManager:
    """Force reload of shared data manager"""
    global _shared_data
    _shared_data = SharedDataManager(namespace, default_ttl, data_dir)
    if auto_save:
        _shared_data.auto_save()
    return _shared_data

"""
PERSISTENCE EXAMPLE:

# Data persists automatically across app restarts
shared_data = get_shared_data()

# Set some settings
shared_data.set_setting("user_theme", "dark")
shared_data.set_setting("window_size", {"width": 1200, "height": 800})

# These are automatically saved to ~/.fichero/shared_data/fichero_settings.jsonl
# When you restart the app, the data is automatically loaded

# Manual control:
shared_data.save_to_disk()  # Save immediately
shared_data.save_to_disk(DataType.SETTINGS)  # Save only settings

# Auto-save is enabled by default (every 5 minutes)
# Disable: get_shared_data(auto_save=False)
# Custom interval: shared_data.auto_save(interval=60)  # Every minute

# Custom data directory:
custom_shared = get_shared_data(data_dir=Path("/custom/path"))
""" 