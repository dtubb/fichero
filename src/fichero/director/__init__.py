"""
Director Module

Centralized document processing coordination system.
Manages backends, tasks, and provides unified interface for GUI and CLI.
"""

# Core director service
from .director_service import FicheroDirector

# Backend system  
from .backends.implementations.base import ProcessingBackend, FolderTask, ProcessingResult, ProcessingStatus
from .backends.implementations import PythonProcessingBackend

# Conditionally export Celery backend
try:
    from .backends.implementations import CeleryBackend
except ImportError:
    CeleryBackend = None

__all__ = [
    'FicheroDirector',
    'ProcessingBackend',
    'FolderTask', 
    'ProcessingResult',
    'ProcessingStatus',
    'PythonProcessingBackend',
]

if CeleryBackend:
    __all__.append('CeleryBackend')

__version__ = "2.0.0-alpha" 