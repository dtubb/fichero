"""
Unified Backend Selection Service

Single source of truth for backend selection across the entire application.
Ensures director (processing) and shared data (storage) use compatible backends.
"""

import logging
from typing import Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class BackendSelector:
    """
    Unified backend selection service.
    
    Ensures both processing (director) and storage (shared data) backends
    are selected together and are guaranteed to be compatible.
    
    Backend Combinations:
    - Celery/Redis preference → Celery processing + Redis storage (requires both Celery package + Redis server)
    - Python preference → Python processing + Manager storage (no external dependencies)
    - Fallback → Always Python processing + Manager storage
    """
    
    @staticmethod
    def select_backends(settings=None) -> Tuple[str, str]:
        """
        Select compatible processing and storage backends.
        
        Args:
            settings: Settings object or dict with backend preference
            
        Returns:
            Tuple of (processing_backend, storage_backend)
            - processing_backend: "celery" or "python"  
            - storage_backend: "redis" or "manager"
        """
        try:
            # Get backend preference from settings
            from .settings_extractor import SettingsExtractor
            from .availability_checker import BackendAvailabilityChecker
            
            preference = SettingsExtractor.get_backend_preference(settings)
            logger.info(f"Backend preference from settings: {preference}")
            
            if SettingsExtractor.is_celery_preferred(settings):
                # Try Celery/Redis backends
                if BackendAvailabilityChecker.can_use_celery():
                    logger.info("✅ Using Celery/Redis backends: Celery + Redis")
                    return "celery", "redis"
                else:
                    logger.warning("⚠️ Celery/Redis not available, falling back to Python-based backends")
                    return "python", "manager"
            else:
                # Use Python-based backends
                logger.info("✅ Using Python-based backends: Python + Manager")
                return "python", "manager"
                
        except Exception as e:
            logger.error(f"❌ Backend selection failed: {e}, using Python fallback")
            return "python", "manager"
    

    

    
    @staticmethod
    def get_backend_info(processing_backend: str, storage_backend: str) -> dict:
        """Get human-readable information about selected backends"""
        info = {
            "processing": {
                "backend": processing_backend,
                "description": "Celery/Redis distributed processing (requires Celery + Redis)" if processing_backend == "celery" 
                              else "Python multiprocessing (no external dependencies)"
            },
            "storage": {
                "backend": storage_backend,
                "description": "Redis key-value storage (requires Redis server)" if storage_backend == "redis"
                              else "Python Manager in-memory storage (no external dependencies)"
            },
            "coordinated": True,
            "infrastructure": "Celery/Redis (distributed)" if processing_backend == "celery" else "Python (local)"
        }
        return info 