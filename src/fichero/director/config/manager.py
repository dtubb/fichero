"""
Configuration Manager

Handles configuration management extracted from FicheroDirector.
Focuses on settings handling and plan configuration loading.
"""

import logging
import socket
import uuid
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """
    Handles configuration management for the director service.
    
    Extracted from FicheroDirector to improve separation of concerns.
    Handles:
    - Settings processing and normalization
    - Plan configuration loading
    - Instance ID generation
    - Configuration utilities
    """
    
    def __init__(self, director):
        self.director = director
        logger.info("ConfigurationManager initialized")
    
    def process_settings(self, settings, app):
        """Process and normalize settings from different sources"""
        # Handle both AppSettings objects and raw dicts
        if settings is None:
            processed_settings = {}
        elif hasattr(settings, 'settings'):
            # AppSettings object - use the internal settings dict
            processed_settings = settings.settings
        else:
            # Raw dict
            processed_settings = settings
        
        return processed_settings, app
    
    def generate_instance_id(self) -> str:
        """Generate unique instance ID"""
        hostname = socket.gethostname()
        return f"{hostname}_{uuid.uuid4().hex[:8]}"
    
    def load_plan_config(self, plan_name: str) -> Dict:
        """Load plan configuration by name"""
        try:
            # Import here to avoid circular dependencies
            from ...config.core.plan_manager import PlanManager
            
            plan_file = PlanManager.get_plan_file_path(plan_name, self.director.app)
            if plan_file and plan_file.exists():
                import yaml
                with open(plan_file, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
            else:
                raise FileNotFoundError(f"Plan file not found: {plan_name}")
        except Exception as e:
            logger.error(f"Failed to load plan config '{plan_name}': {e}")
            raise
    
    def validate_configuration(self) -> Dict[str, Any]:
        """Validate current configuration and return status"""
        validation = {
            "valid": True,
            "issues": [],
            "warnings": []
        }
        
        # Check if settings exist
        if not hasattr(self.director, 'settings') or not self.director.settings:
            validation["issues"].append("No settings configured")
            validation["valid"] = False
        
        # Check backend configuration
        backend_type = self.director.settings.get('workers', {}).get('backend', 'python')
        if backend_type not in ['python', 'redis', 'celery']:
            validation["issues"].append(f"Invalid backend type: {backend_type}")
            validation["valid"] = False
        
        # Check app configuration
        if not self.director.app:
            validation["warnings"].append("No app context available")
        
        return validation
    
    def get_configuration_summary(self) -> Dict[str, Any]:
        """Get summary of current configuration"""
        summary = {
            "instance_id": getattr(self.director, 'instance_id', 'unknown'),
            "backend_type": self.director.settings.get('workers', {}).get('backend', 'python'),
            "has_app_context": bool(self.director.app),
            "settings_keys": list(self.director.settings.keys()) if self.director.settings else []
        }
        
        # Add backend-specific configuration
        workers_config = self.director.settings.get('workers', {})
        if workers_config:
            summary["workers_config"] = {
                "backend": workers_config.get('backend', 'python'),
                "cpu_workers": workers_config.get('cpu_workers'),
                "io_workers": workers_config.get('io_workers'),
        
            }
        
        return summary 