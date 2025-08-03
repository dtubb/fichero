"""
Backend Implementations

This module contains the concrete backend implementations for the Fichero director.

Available backends:
- PythonProcessingBackend: ThreadPoolExecutor-based backend (no external dependencies, Mac app compatible)
- CeleryBackend: Celery/Redis-based distributed backend (requires Celery + Redis)
"""

from fichero.director.backends.implementations.base import ProcessingBackend, ProcessingStatus
from fichero.director.backends.implementations.python_backend import PythonProcessingBackend

# Optional Celery backend (may not be available)
try:
    from fichero.director.backends.implementations.celery_backend import CeleryBackend
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