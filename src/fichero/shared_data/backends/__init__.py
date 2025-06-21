"""
Shared Data Storage Backends
"""

from .base import BaseStorageBackend, DataType
from .manager import ManagerStorageBackend

# Redis backend is optional
try:
    from .redis import RedisStorageBackend
    REDIS_AVAILABLE = True
except ImportError:
    RedisStorageBackend = None
    REDIS_AVAILABLE = False

__all__ = ['BaseStorageBackend', 'DataType', 'ManagerStorageBackend', 'RedisStorageBackend', 'REDIS_AVAILABLE'] 