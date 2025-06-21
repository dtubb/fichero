"""
Shared Data System for Fichero
Inter-process communication and data sharing with Redis/Manager backends
"""

from .manager import SharedDataManager, get_shared_data, reload_shared_data
from .backends.base import DataType

__all__ = ['SharedDataManager', 'DataType', 'get_shared_data', 'reload_shared_data'] 