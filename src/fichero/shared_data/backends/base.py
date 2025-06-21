"""
Base Storage Backend for SharedDataManager
Common functionality shared by Redis and Manager backends
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any, List
from pathlib import Path
from enum import Enum

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


class BaseStorageBackend(ABC):
    """Abstract base class for storage backends"""
    
    def __init__(self, namespace: str = "fichero", default_ttl: Optional[int] = None, 
                 data_dir: Optional[Path] = None):
        self.namespace = namespace
        self.default_ttl = default_ttl
        self.data_dir = data_dir or Path.home() / ".fichero" / "shared_data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backend_name = "base"
    
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
    
    def get_info(self) -> Dict[str, Any]:
        """Get basic backend information"""
        info = {
            "backend": self.backend_name,
            "namespace": self.namespace,
            "default_ttl": self.default_ttl,
            "data_dir": str(self.data_dir),
        }
        
        # Count by data type
        for data_type in DataType:
            try:
                count = len(self.keys(data_type))
                info[f"{data_type.value}_count"] = count
            except Exception:
                info[f"{data_type.value}_count"] = 0
        
        return info
    
    # Abstract methods that backends must implement
    @abstractmethod
    def set(self, data_type: DataType, key: str, value: Any, ttl: Optional[int] = None, 
            immediate_save: bool = False) -> bool:
        """Set data"""
        pass
    
    @abstractmethod
    def get(self, data_type: DataType, key: str, default: Any = None) -> Any:
        """Get data"""
        pass
    
    @abstractmethod
    def delete(self, data_type: DataType, key: str) -> bool:
        """Delete data"""
        pass
    
    @abstractmethod
    def keys(self, data_type: DataType, pattern: str = "*") -> List[str]:
        """List keys for a data type"""
        pass
    
    @abstractmethod
    def clear_data_type(self, data_type: DataType) -> bool:
        """Clear all data for a specific type"""
        pass
    
    @abstractmethod
    def save_to_disk(self, data_type: Optional[DataType] = None):
        """Save data to disk for persistence"""
        pass
    
    @abstractmethod
    def auto_save(self, interval: int = 300):
        """Enable automatic saving"""
        pass
    
    # Convenience methods for settings (all backends support these)
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