"""
Variable Generator

Simple variable generation for workflow execution.
Generates system paths and passes through catalogue variables.
"""

import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class VariableGenerator:
    """
    Simple variable generator for workflow execution.
    
    Generates:
    - System paths (scripts_dir, yolo_model_path, etc.)
    - Output path
    - Passes through simple catalogue variables (no complex expansion)
    """
    
    def __init__(self):
        logger.info("VariableGenerator initialized")
    
    def generate_variables(self, plan_config: Dict, output_path: Path = None, folders: List[Path] = None) -> Dict:
        """
        Generate variables for workflow execution
        
        Args:
            plan_config: Plan configuration dictionary
            output_path: Base output directory 
            folders: List of folders being processed (unused in simplified version)
            
        Returns:
            Dictionary of variables for workflow execution
        """
        variables = {}
        
        try:
            # Generate system paths
            variables.update(self._generate_script_paths())
            
            # Add output path if provided
            if output_path:
                variables['output_path'] = str(output_path)
                variables['output_folder'] = str(output_path)  # Backward compatibility
            
            # Just copy simple vars from catalogue (no expansion needed since we hardcoded paths)
            plan_vars = plan_config.get('vars', {})
            variables.update(plan_vars)
            
            logger.info(f"Generated {len(variables)} variables for workflow execution")
            return variables
            
        except Exception as e:
            logger.error(f"Failed to generate variables: {e}")
            return {}
    
    def _generate_script_paths(self) -> Dict[str, str]:
        """Generate script and resource path variables"""
        try:
            import fichero
            package_root = Path(fichero.__file__).parent  # This is src/fichero
            project_root = package_root.parent.parent  # This is project root/
            
            return {
                'fichero_root': str(project_root),
                'scripts_dir': str(package_root / "tools"),
                'prompts_dir': str(package_root / "resources" / "config_defaults" / "prompts"),
                'models_dir': str(package_root / "resources" / "models"),
                'yolo_model_path': str(package_root / "resources" / "models" / "yolov8s-fichero.pt")
            }
            
        except Exception as e:
            logger.warning(f"Could not determine scripts directory: {e}")
            # Fallback 
            return {
                'fichero_root': ".",
                'scripts_dir': "./tools", 
                'prompts_dir': "./resources/prompts"
            }