"""
Python Manager Backend for SharedDataManager
Provides multiprocessing.Manager-based storage with TTL and persistence
"""

import time
import logging
import srsly
import threading
import atexit
import signal
from typing import Dict, Optional, Any, List
from pathlib import Path
from multiprocessing import Manager

from .base import DataType, BaseStorageBackend

logger = logging.getLogger(__name__)


class ManagerStorageBackend(BaseStorageBackend):
    """Python Manager backend for shared data storage with persistence"""
    
    def __init__(self, namespace: str = "fichero", data_dir: Optional[Path] = None, app=None):
        super().__init__(namespace, data_dir, app)
        self.backend_name = "manager"
        self._init_manager()
        self._load_persisted_data()
    
    def _init_manager(self):
        """Initialize multiprocessing.Manager backend with fallback"""
        # Aggressively detect any bundled/packaged environment and use fallback
        if self._is_bundled_or_problematic_environment():
            logger.info("Detected bundled/packaged environment, using safe fallback dict storage")
            self.manager = None
            self.store = {}  # Regular dict as fallback
            self._lock = threading.RLock()
            self._use_fallback = True
            return
        
        # For development environments, try Manager with simple fallback
        try:
            logger.info("Attempting multiprocessing.Manager initialization...")
            self.manager = Manager()
            self.store = self.manager.dict()
            self._lock = threading.RLock()
            self._use_fallback = False
            logger.info("SharedDataManager using multiprocessing.Manager backend")
        except Exception as e:
            # Any failure immediately falls back
            logger.warning(f"Manager() failed, using fallback dict storage: {e}")
            self.manager = None
            self.store = {}  # Regular dict as fallback
            self._lock = threading.RLock()
            self._use_fallback = True
            logger.info("SharedDataManager using fallback dict backend")
    
    def _is_bundled_or_problematic_environment(self) -> bool:
        """Detect bundled apps or environments where Manager() might hang"""
        import sys
        import os
        
        # Check for any bundled app indicators
        bundled_indicators = [
            getattr(sys, 'frozen', False),  # PyInstaller, cx_Freeze
            hasattr(sys, '_MEIPASS'),  # PyInstaller
            'briefcase' in str(sys.executable).lower(),  # Briefcase
            '.app/Contents/' in str(sys.executable),  # macOS app bundle
            '.app/Contents/' in os.getcwd(),  # Running from app bundle
            os.environ.get('BRIEFCASE_MAIN_MODULE'),  # Briefcase environment
            'Fichero.app' in str(sys.executable),  # Our specific app
            'app_packages' in str(sys.path),  # Briefcase app packages
        ]
        
        if any(bundled_indicators):
            return True
        
        # Check sys.path for bundled indicators
        for path in sys.path:
            if any(indicator in str(path).lower() for indicator in 
                   ['briefcase', '.app/contents', 'app_packages', 'fichero.app']):
                return True
        
        # Check if we're in a Toga app context (additional safety)
        if self.app and hasattr(self.app, 'paths'):
            return True
        
        # Check current working directory
        cwd = os.getcwd()
        if any(indicator in cwd.lower() for indicator in 
               ['.app/contents', 'briefcase', 'fichero.app']):
            return True
        
        return False
    
    def set(self, data_type: DataType, key: str, value: Any, immediate_save: bool = False) -> bool:
        """Set data in Manager store (thread-safe)"""
        try:
            with self._lock:
                namespaced_key = self._make_key(data_type, key)
                serialized_value = self._serialize(value)
                
                self.store[namespaced_key] = serialized_value
                
                # Immediate save for critical data (like settings changes)
                if immediate_save:
                    self.save_to_disk(data_type)
            
            return True
        except Exception as e:
            logger.error(f"Failed to set {data_type.value} key {key}: {e}")
            return False
    
    def get(self, data_type: DataType, key: str, default: Any = None) -> Any:
        """Get data from Manager store (thread-safe)"""
        try:
            with self._lock:
                namespaced_key = self._make_key(data_type, key)
                
                val = self.store.get(namespaced_key, default)
                if val == default:
                    return default
                return self._deserialize(val)
        except Exception as e:
            logger.error(f"Failed to get {data_type.value} key {key}: {e}")
            return default
    
    def delete(self, data_type: DataType, key: str) -> bool:
        """Delete data from Manager store"""
        try:
            namespaced_key = self._make_key(data_type, key)
            
            if namespaced_key in self.store:
                del self.store[namespaced_key]
                return True
            
            return False
        except Exception as e:
            logger.error(f"Failed to delete {data_type.value} key {key}: {e}")
            return False
    
    def keys(self, data_type: DataType, pattern: str = "*") -> List[str]:
        """List keys for a data type in Manager store"""
        try:
            all_keys = list(self.store.keys())
            prefix = f"{self.namespace}:{data_type.value}:"
            filtered_keys = []
            
            for key in all_keys:
                if key.startswith(prefix):
                        clean_key = key.replace(prefix, "", 1)
                        if pattern == "*" or pattern in clean_key:
                            filtered_keys.append(clean_key)
            
            return filtered_keys
        except Exception as e:
            logger.error(f"Failed to get {data_type.value} keys: {e}")
            return []
    
    def get_info(self) -> Dict[str, Any]:
        """Get Manager backend information"""
        info = super().get_info()
        
        try:
            info.update({
                "total_keys": len(self.store),
                "using_fallback": getattr(self, '_use_fallback', False),
                "manager_available": self.manager is not None
            })
        except Exception as e:
            logger.error(f"Failed to get Manager info: {e}")
            info["error"] = str(e)
        
        return info
    
    def clear_data_type(self, data_type: DataType) -> bool:
        """Clear all data for a specific type in Manager store"""
        try:
            keys_to_delete = self.keys(data_type)
            for key in keys_to_delete:
                self.delete(data_type, key)
            return True
        except Exception as e:
            logger.error(f"Failed to clear {data_type.value} data: {e}")
            return False
    
    def _get_persistence_file(self, data_type: DataType) -> Path:
        """Get the file path for persisting a data type"""
        return self.data_dir / f"{self.namespace}_{data_type.value}.jsonl"
    
    def _load_persisted_data(self):
        """Load persisted data from disk on startup"""
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
                            
                            if not key:
                                continue  # Skip invalid entries
                            
                            # Store the value
                            namespaced_key = self._make_key(data_type, key)
                            self.store[namespaced_key] = self._serialize(value)
                                    
                    except Exception as e:
                        logger.warning(f"Failed to load {data_type.value} data from {persistence_file}: {e}")
        except Exception as e:
            logger.warning(f"Failed to load persisted data: {e}")
    
    def save_to_disk(self, data_type: Optional[DataType] = None):
        """Save data to disk for persistence (thread-safe)"""
        try:
            with self._lock:
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
                                    "value": value
                                }
                                entries_to_save.append(entry)
                        except Exception as e:
                            logger.warning(f"Failed to serialize {dt.value} key {key}: {e}")
                    
                    # Save to JSONL file
                    if entries_to_save:
                        srsly.write_jsonl(persistence_file, entries_to_save)
                        logger.debug(f"Saved {len(entries_to_save)} {dt.value} entries to {persistence_file}")
                    elif persistence_file.exists():
                        # Remove empty persistence files
                        persistence_file.unlink()
                        logger.debug(f"Removed empty {dt.value} persistence file")
                    
        except Exception as e:
            logger.error(f"Failed to save data to disk: {e}")
    
    def auto_save(self, interval: int = 300):
        """Enable automatic saving every interval seconds (DISABLED for stability)"""
        logger.info("Auto-save disabled for stability - using immediate saves instead")
        
        def _emergency_save(signum=None, frame=None):
            """Emergency save on crash/signal - non-blocking"""
            try:
                logger.warning(f"Emergency save triggered (signal: {signum})")
                # Use a thread to avoid blocking the signal handler
                import threading
                def _save_thread():
                    try:
                        self.save_to_disk()
                        logger.info("Emergency save completed")
                    except Exception as e:
                        logger.error(f"Emergency save failed: {e}")
                
                # Start save in background thread (non-blocking)
                save_thread = threading.Thread(target=_save_thread, daemon=True)
                save_thread.start()
                
                # Don't wait for the thread to complete - let it run in background
                
            except Exception as e:
                logger.error(f"Emergency save handler failed: {e}")
        
        # Register emergency save handlers only (no background threads)
        atexit.register(self.save_to_disk)  # Normal exit
        
        # Handle common crash signals (but don't block shutdown)
        try:
            # Only register SIGTERM and SIGHUP - let SIGINT (Ctrl+C) be handled normally
            signal.signal(signal.SIGTERM, _emergency_save)  # Termination
            if hasattr(signal, 'SIGHUP'):
                signal.signal(signal.SIGHUP, _emergency_save)   # Hangup
            # Don't register SIGINT - let CLI handle Ctrl+C normally
        except Exception as e:
            logger.warning(f"Could not register signal handlers: {e}")
        
        logger.info("Emergency save handlers registered (SIGTERM/SIGHUP only)")
    
    def cleanup(self):
        """Clean up Manager backend resources"""
        try:
            # Save data before cleanup
            self.save_to_disk()
            
            # Shutdown multiprocessing Manager if it exists
            if hasattr(self, 'manager') and self.manager is not None:
                logger.info("Shutting down multiprocessing Manager...")
                try:
                    # Close the manager to clean up background processes
                    self.manager.shutdown()
                    logger.info("Multiprocessing Manager shutdown completed")
                except Exception as e:
                    logger.warning(f"Error shutting down Manager: {e}")
                finally:
                    self.manager = None
                    self.store = {}
            
            logger.info("Manager backend cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during Manager backend cleanup: {e}") 