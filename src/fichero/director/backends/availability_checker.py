"""
Backend Availability Checker

Shared utility for checking backend availability to eliminate code duplication.
Used by both BackendSelector and BackendManager.
"""

import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)


class BackendAvailabilityChecker:
    """
    Shared utility for checking backend availability.
    
    Eliminates code duplication between BackendSelector and BackendManager
    by providing a single source of truth for availability checks.
    """
    
    @staticmethod
    def check_all_backends() -> Dict[str, Any]:
        """
        Check availability of all backends with detailed information.
        
        Returns:
            Dict with detailed availability info for each backend
        """
        # Python backend is always available
        availability = {
            "python": {
                "available": True,
                "details": "ThreadPoolExecutor backend (always available, Mac app compatible)"
            }
        }
        
        # Check Redis/Celery backend
        redis_available, redis_details = BackendAvailabilityChecker._check_redis()
        celery_available, celery_details = BackendAvailabilityChecker._check_celery()
        
        # Celery/Redis backend requires both
        if redis_available and celery_available:
            availability["celery"] = {
                "available": True,
                "details": f"Requires both: Celery package + Redis server. {redis_details}"
            }
        else:
            status_parts = []
            if not celery_available:
                status_parts.append(celery_details)
            if not redis_available:
                status_parts.append(f"Redis server: {redis_details}")
            
            availability["celery"] = {
                "available": False,
                "details": f"Missing: {'; '.join(status_parts)}"
            }
        
        return availability
    
    @staticmethod
    def can_use_celery() -> bool:
        """
        Simple boolean check if Celery/Redis backend is available.
        
        Returns:
            True if both Redis and Celery are available, False otherwise
        """
        try:
            redis_available, _ = BackendAvailabilityChecker._check_redis()
            celery_available, _ = BackendAvailabilityChecker._check_celery()
            
            result = redis_available and celery_available
            logger.debug(f"Celery/Redis availability check: {result}")
            return result
            
        except Exception as e:
            logger.debug(f"Celery/Redis availability check failed: {e}")
            return False
    
    @staticmethod
    def _check_redis() -> Tuple[bool, str]:
        """
        Check Redis package and server availability.
        
        Returns:
            Tuple of (is_available, details_message)
        """
        try:
            # Check Redis package
            import redis
            
            # Test Redis server connection
            try:
                r = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=2)
                r.ping()
                return True, "Redis server running on localhost:6379"
            except Exception as e:
                return False, f"Redis server not accessible: {e}"
                
        except ImportError:
            return False, "Redis package not installed"
    
    @staticmethod
    def _check_celery() -> Tuple[bool, str]:
        """
        Check Celery package availability.
        
        Returns:
            Tuple of (is_available, details_message)
        """
        try:
            import celery
            return True, "Celery package installed"
        except ImportError:
            return False, "Celery package not installed" 