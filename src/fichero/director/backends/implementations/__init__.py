"""
Backend Implementations

This module contains the concrete backend implementations for the Fichero director.

Available backends:
- PythonProcessingBackend: Multiprocessing-based backend (no external dependencies)
- CeleryBackend: Celery/Redis-based distributed backend (requires Celery + Redis)
"""

from .base import ProcessingBackend, ProcessingStatus
from .python_backend import PythonProcessingBackend

# Optional Celery backend (may not be available)
try:
    from .celery_backend import CeleryBackend
    CELERY_AVAILABLE = True
except ImportError:
    CeleryBackend = None
    CELERY_AVAILABLE = False

__all__ = [
    'ProcessingBackend',
    'ProcessingStatus', 
    'PythonProcessingBackend',
    'CeleryBackend',
    'CELERY_AVAILABLE'
] 