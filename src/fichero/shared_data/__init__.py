"""
Simplified Shared Data System for Fichero
Just what we need: Redis for Celery, Threading for main process
"""

from .simple_manager import SimpleSharedData, get_shared_data

__all__ = ['SimpleSharedData', 'get_shared_data'] 