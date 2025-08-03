"""
Backend Initializer

Handles backend initialization logic extracted from FicheroDirector.
Focuses on backend selection, creation, and initialization.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BackendInitializer:
    """
    Handles backend initialization for the director service.
    
    Extracted from FicheroDirector to improve separation of concerns.
    Handles:
    - Backend type determination
    - Backend creation (Python/Celery)
    - Backend initialization
    - Fallback logic
    """
    
    def __init__(self, director):
        self.director = director
        logger.info("BackendInitializer initialized")
    
    def initialize_backend(self) -> bool:
        """Initialize the processing backend based on settings"""
        if self._is_backend_already_initialized():
            return True
        
        try:
            # Create backend based on settings
            backend = self._create_backend()
            if not backend:
                logger.error("Failed to create backend")
                return False
            
            # Initialize the backend
            if not backend.initialize():
                logger.error("Backend initialization failed")
                return False
            
            # Set up director components
            self._setup_director_components(backend)
            
            logger.info(f"Backend initialized successfully: {backend.backend_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize backend: {e}")
            return False
    
    def _is_backend_already_initialized(self) -> bool:
        """Check if backend is already initialized"""
        if (self.director.backend and 
            hasattr(self.director.backend, 'is_initialized') and 
            self.director.backend.is_initialized):
            logger.info(f"Backend already initialized: {self.director.backend.backend_name}")
            return True
        return False
    
    def _create_backend(self):
        """Create backend based on settings"""
        from fichero.director.backends.settings_extractor import SettingsExtractor
        
        backend_preference = SettingsExtractor.get_backend_preference(self.director.settings)
        logger.info(f"Initializing backend: {backend_preference}")
        
        backend = None
        
        # Try Celery backend first if requested
        if SettingsExtractor.is_celery_preferred(self.director.settings):
            backend = self._try_create_celery_backend()
            if not backend:
                logger.warning("Celery backend not available, falling back to Python backend")
        
        # Use Python backend as default or fallback
        if backend is None:
            backend = self._create_python_backend()
        
        return backend
    
    def _try_create_celery_backend(self):
        """Try to create Celery backend"""
        try:
            from fichero.director.backends.implementations.celery_backend import CeleryBackend
            backend = CeleryBackend(self.director.settings)
            logger.info("Using Celery backend")
            return backend
        except ImportError:
            logger.warning("Celery backend not available")
            return None
    
    def _create_python_backend(self):
        """Create Python backend"""
        try:
            from fichero.director.backends.implementations.python_backend import PythonProcessingBackend
            backend = PythonProcessingBackend(self.director.settings)
            logger.info("Using Python backend")
            return backend
        except Exception as e:
            logger.error(f"Failed to create Python backend: {e}")
            return None
    
    def _setup_director_components(self, backend):
        """Set up director components after backend initialization"""
        # Set the backend
        self.director.backend = backend
        
        # Initialize task manager
        from fichero.director.task_manager import TaskManager
        self.director.task_manager = TaskManager(backend)
        self.director.task_manager.start()
        
        # Initialize processing coordinator
        from fichero.director.coordinator import ProcessingCoordinator
        self.director.processing_coordinator = ProcessingCoordinator(
            self.director.task_manager, 
            self.director.variable_generator,
            self.director.configuration_manager.load_plan_config
        )
        
        # Register progress callbacks
        for callback in self.director.progress_callbacks:
            self.director.task_manager.register_progress_callback(callback) 