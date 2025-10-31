"""
Processing Coordinator

Handles processing workflow coordination - pure processing logic only.
Focuses on coordinating folder processing, auto-detection, and task submission.
Display logic is handled separately by monitoring/displays/.
"""

import logging
from typing import Dict, List, Optional, Callable
from pathlib import Path

from fichero.director.task_manager import TaskManager
from fichero.director.backends.implementations.base import ProcessingBackend

logger = logging.getLogger(__name__)


class ProcessingCoordinator:
    """
    Coordinates processing workflows for the director service.

    Pure processing logic - NO display responsibilities.

    Handles:
    - Folder processing coordination
    - Auto-detection of subfolders
    - Task submission orchestration
    - Variable generation coordination

    Display logic is handled by monitoring/displays/ modules.
    """

    def __init__(self, task_manager: TaskManager, variable_generator, plan_loader_func, director=None):
        self.task_manager = task_manager
        self.variable_generator = variable_generator
        self._load_plan_config = plan_loader_func
        self.director = director  # Store director reference to avoid circular import

        logger.info("ProcessingCoordinator initialized")
    
    def process_folders(self, folders, plan_name: str,
                       workflow_name: str = "default",
                       output_path: Path = None,
                       document_context: Dict = None) -> str:
        """
        Convenience method to process folders using a plan name

        Args:
            folders: List of folder paths OR dicts with 'output_folder' and 'documents_folder' keys
            plan_name: Name of the plan to use
            workflow_name: Name of workflow within the plan
            output_path: Base output directory
            document_context: Context from document window (optional)

        Returns:
            Task ID string
        """
        # Load plan configuration
        logger.info(f"Loading plan configuration for: {plan_name}")
        try:
            plan_config = self._load_plan_config(plan_name)
            if not plan_config:
                error_msg = f"Plan config is None for plan: {plan_name}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            else:
                logger.info(f"Successfully loaded plan config for: {plan_name}")
        except Exception as e:
            error_msg = f"Failed to load plan '{plan_name}': {e}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e

        # Generate variables from output_path and plan config if provided
        variables = self.variable_generator.generate_variables(plan_config, output_path, folders)

        # Submit task
        return self.task_manager.submit_task(
            folders=folders,
            plan_config=plan_config,
            workflow_name=workflow_name,
            variables=variables,
            document_context=document_context
        )
    
    def process_with_auto_detection(self, input_path: Path, output_path: Path, 
                                   plan_name: str, workflow_name: str = "default",
                                   document_context: Dict = None) -> List[str]:
        """
        Auto-detect subfolders and process each as separate task using proper two-phase approach
        
        Args:
            input_path: Input folder path to check for subfolders
            output_path: Base output directory
            plan_name: Name of the plan to use
            workflow_name: Name of workflow within the plan
            document_context: Context from document window (optional)
        
        Returns:
            List of task IDs for each folder being processed
        """
        logger.info(f"Processing with auto-detection: {input_path} -> {output_path}")

        # Use the proper folder processor for two-phase processing
        from fichero.director.folder_processor import FolderProcessor

        # Use the director instance passed during initialization
        if not self.director:
            raise RuntimeError("Director instance not available in ProcessingCoordinator")

        folder_processor = FolderProcessor(self.director)
        
        # Phase 1: Detect and prepare all folders (sequential)
        logger.info("Phase 1: Detecting and preparing folders...")
        prepared_folders = folder_processor.detect_and_prepare_folders([input_path], output_path)
        logger.info(f"Phase 1 complete: {len(prepared_folders)} folders prepared")
        
        # Phase 2: Submit tasks for parallel processing
        logger.info("Phase 2: Submitting tasks for parallel processing...")
        task_ids = folder_processor.submit_processing_tasks(
            prepared_folders, 
            plan_name, 
            workflow_name, 
            document_context
        )
        logger.info(f"Phase 2 complete: {len(task_ids)} tasks submitted")
        
        return task_ids