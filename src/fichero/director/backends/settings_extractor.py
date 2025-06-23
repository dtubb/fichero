"""
Settings Extractor

Shared utility for extracting backend preferences from settings.
"""

import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class SettingsExtractor:
    """
    Shared utility for extracting backend preferences from settings.
    
    Handles different settings formats:
    - AppSettings objects (with .get_backend_type() method)
    - AppSettings objects (with .settings dict)
    - Raw dict objects
    - None/missing settings
    """
    
    @staticmethod
    def get_backend_preference(settings: Optional[Any]) -> str:
        """
        Extract backend preference from settings object.
        
        Args:
            settings: Settings object (AppSettings, dict, or None)
            
        Returns:
            Backend preference string: "python", "redis", "celery"
            Defaults to "python" if not found or invalid
        """
        if not settings:
            logger.debug("No settings provided, defaulting to python backend")
            return "python"
        
        try:
            # Method 1: AppSettings object with get_backend_type() method
            if hasattr(settings, 'get_backend_type'):
                preference = settings.get_backend_type()
                logger.debug(f"Extracted backend preference via get_backend_type(): {preference}")
                return SettingsExtractor._normalize_backend_name(preference)
            
            # Method 2: AppSettings object with internal .settings dict
            if hasattr(settings, 'settings'):
                preference = settings.settings.get("workers", {}).get("backend", "python")
                logger.debug(f"Extracted backend preference via settings.settings: {preference}")
                return SettingsExtractor._normalize_backend_name(preference)
            
            # Method 3: Raw dict
            if isinstance(settings, dict):
                preference = settings.get("workers", {}).get("backend", "python")
                logger.debug(f"Extracted backend preference via raw dict: {preference}")
                return SettingsExtractor._normalize_backend_name(preference)
                
        except Exception as e:
            logger.debug(f"Could not extract backend preference: {e}")
        
        logger.debug("Could not extract backend preference, defaulting to python")
        return "python"
    
    @staticmethod
    def _normalize_backend_name(preference: str) -> str:
        """
        Normalize backend name to standard values.
        
        Args:
            preference: Raw backend preference string
            
        Returns:
            Normalized backend name: "python", "celery"
            Note: "redis" is normalized to "celery" for consistency
        """
        if not preference or not isinstance(preference, str):
            return "python"
        
        # Normalize to lowercase
        normalized = preference.lower().strip()
        
        # Map variations to standard names
        if normalized in ["redis", "celery"]:
            return "celery"  # "redis" is alias for "celery"
        elif normalized == "python":
            return "python"
        else:
            logger.debug(f"Unknown backend preference '{preference}', defaulting to python")
            return "python"
    
    @staticmethod
    def is_celery_preferred(settings: Optional[Any]) -> bool:
        """
        Check if Celery/Redis backend is preferred in settings.
        
        Args:
            settings: Settings object
            
        Returns:
            True if Celery/Redis is preferred, False otherwise
        """
        preference = SettingsExtractor.get_backend_preference(settings)
        return preference == "celery"
    
    @staticmethod
    def extract_worker_config(settings: Optional[Any]) -> dict:
        """
        Extract worker configuration from settings.
        
        Args:
            settings: Settings object
            
        Returns:
            Dict with worker configuration (cpu_workers, io_workers, etc.)
        """
        if not settings:
            return {}
        
        try:
            # Try to get workers config
            if hasattr(settings, 'settings'):
                return settings.settings.get("workers", {})
            elif isinstance(settings, dict):
                return settings.get("workers", {})
        except Exception as e:
            logger.debug(f"Could not extract worker config: {e}")
        
        return {} 