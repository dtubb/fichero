"""
Processing Backends

Unified backend system with organized structure:

Implementations:
- Python: Local processing using ThreadPoolExecutor (always available, Mac app compatible)
- Celery: Distributed processing with Redis (optional dependency)

Management:
- BackendSelector: Chooses compatible backends
- BackendInitializer: Sets up backends
- BackendManager: Runtime management operations

Configuration:
- WorkerSizing: Optimal worker configuration for system resources
"""

# Import from implementations
from fichero.director.backends.implementations.base import ProcessingBackend, FolderTask, ProcessingResult, ProcessingStatus, create_folder_task
from fichero.director.backends.implementations import PythonProcessingBackend, CeleryBackend, CELERY_AVAILABLE

# Import management components
from fichero.director.backends.backend_selector import BackendSelector
from fichero.director.backends.backend_initializer import BackendInitializer
from fichero.director.backends.backend_manager import BackendManager
from fichero.director.backends.availability_checker import BackendAvailabilityChecker
from fichero.director.backends.settings_extractor import SettingsExtractor
from fichero.director.backends.worker_sizing import get_optimal_workers, suggest_backend, WorkerConfig

__all__ = [
    # Implementations
    'ProcessingBackend',
    'FolderTask', 
    'ProcessingResult',
    'ProcessingStatus',
    'create_folder_task',
    'PythonProcessingBackend',
    'CeleryBackend',
    'CELERY_AVAILABLE',
    # Management
    'BackendSelector',
    'BackendInitializer', 
    'BackendManager',
    'BackendAvailabilityChecker',
    'SettingsExtractor',
    # Worker Configuration
    'get_optimal_workers',
    'suggest_backend',
    'WorkerConfig',
] 