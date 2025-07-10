"""
Shared Data Storage Backends
"""

from .base import BaseStorageBackend, DataType
from .threading_backend import ThreadingStorageBackend

# Redis backend is optional
try:
    from .redis import RedisStorageBackend
    REDIS_AVAILABLE = True
except ImportError:
    RedisStorageBackend = None
    REDIS_AVAILABLE = False

__all__ = ['BaseStorageBackend', 'DataType', 'ThreadingStorageBackend', 'RedisStorageBackend', 'REDIS_AVAILABLE'] 