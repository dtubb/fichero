"""
Backend Manager

Handles backend management functionality extracted from FicheroDirector.
Focuses on backend availability, health checking, and worker management.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BackendManager:
    """
    Handles backend management functionality for the director service.
    
    Extracted from FicheroDirector to improve separation of concerns.
    Handles:
    - Backend availability checking
    - Worker management (start/stop/restart)
    - Health monitoring
    - Task management (purge, etc.)
    """
    
    def __init__(self, director):
        self.director = director
        logger.info("BackendManager initialized")
    
    def get_backend_info(self) -> Dict[str, Any]:
        """Get comprehensive backend information including availability"""
        if not self.director.backend:
            return {"status": "not_initialized", "backend_name": "none"}
        
        try:
            info = {
                "backend_name": self.director.backend.backend_name,
                "status": "healthy" if hasattr(self.director.backend, 'is_initialized') and self.director.backend.is_initialized else "unhealthy",
                "is_initialized": hasattr(self.director.backend, 'is_initialized') and self.director.backend.is_initialized
            }
            
            # Add availability information for all backends
            from .availability_checker import BackendAvailabilityChecker
            info["availability"] = BackendAvailabilityChecker.check_all_backends()
            
            return info
        except Exception as e:
            logger.error(f"Failed to get backend info: {e}")
            return {"status": "error", "error": str(e), "backend_name": "unknown"}
    

    
    def start_backend_workers(self, cpu_workers: int = None, io_workers: int = None) -> bool:
        """Start backend workers - unified method"""
        if not self.director.backend or not hasattr(self.director.backend, 'start_workers'):
            return False
        return self.director.backend.start_workers(cpu_workers, io_workers)
    
    def stop_backend_workers(self) -> bool:
        """Stop backend workers - unified method"""
        if not self.director.backend or not hasattr(self.director.backend, 'stop_workers'):
            return False
        return self.director.backend.stop_workers()
    
    def restart_backend_workers(self, cpu_workers: int = None, io_workers: int = None) -> bool:
        """Restart backend workers - unified method"""
        if not self.director.backend or not hasattr(self.director.backend, 'restart_workers'):
            return False
        return self.director.backend.restart_workers(cpu_workers, io_workers)
    
    def get_backend_worker_status(self) -> Dict:
        """Get backend worker status - unified method"""
        if not self.director.backend or not hasattr(self.director.backend, 'get_worker_status'):
            return {}
        return self.director.backend.get_worker_status()
    
    def check_backend_health(self) -> Dict:
        """Check backend health - unified method"""
        if not self.director.backend or not hasattr(self.director.backend, 'health_check'):
            return {"healthy": False, "checks": {}}
        return self.director.backend.health_check()
    
    def purge_backend_tasks(self) -> bool:
        """Purge backend tasks - unified method"""
        if not self.director.backend or not hasattr(self.director.backend, 'purge_tasks'):
            return False
        return self.director.backend.purge_tasks() 