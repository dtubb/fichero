"""
Workflow Executor

Executes workflows as direct function calls.
Stops on first error. Delegates logging and monitoring to separate components.
"""

import logging
import time
import importlib
from pathlib import Path
from typing import Dict, List, Callable, Optional
from contextlib import contextmanager

from fichero.director.backends.implementations.base import ProcessingResult
from fichero.director.workflow_logger import WorkflowLogger
from fichero.director.workflow_manifest import WorkflowManifest

logger = logging.getLogger(__name__)



class WorkflowExecutor:
    """
    Simple workflow executor - runs function calls, stops on error
    """
    
    def __init__(self, progress_callback: Optional[Callable] = None):
        self.progress_callback = progress_callback
        self._cancelled = False
    
    @contextmanager
    def _set_tool_logger_context(self, workflow_logger: WorkflowLogger, step_name: str):
        """Context manager to set tool logger context for workflow execution"""
        try:
            # Set workflow context for tool logger
            from fichero.tools.utils.tool_logger import set_workflow_context
            set_workflow_context(workflow_logger, step_name)
            yield
        finally:
            # Clear workflow context
            from fichero.tools.utils.tool_logger import clear_workflow_context  
            clear_workflow_context()

    def execute_workflow(self, task_id: str, folder_path: Path, output_path: Path,
                        workflow_name: str, plan_config: Dict, variables: Dict,
                        parallel_workers: int = 1, skip_processing: bool = False) -> ProcessingResult:
        """Execute workflow steps until completion or first error"""
        start_time = time.time()
        workflow_logger = None
        
        # Log which folder is being processed for order tracking
        folder_name = folder_path.name
        logger.info(f"🎯 STARTING WORKFLOW for folder: '{folder_name}' (task: {task_id[:8]}...)")
        logger.info(f"📁 Processing folder: {folder_path}")
        logger.info(f"⚙️ Workflow: '{workflow_name}' with {parallel_workers} parallel workers")
        
        try:
            if not plan_config:
                error_msg = f"No plan configuration provided"
                logger.error(error_msg)
                return ProcessingResult(
                    task_id=task_id, success=False, folder_path=folder_path,
                    output_path=output_path, execution_time=time.time() - start_time
                )

            # Get workflow steps
            workflows = plan_config.get('workflows', {})
            workflow_steps = workflows.get(workflow_name, [])

            if not workflow_steps:
                return ProcessingResult(
                    task_id=task_id, success=True, folder_path=folder_path,
                    output_path=output_path, execution_time=time.time() - start_time
                )

            # Get commands
            commands = {cmd['name']: cmd for cmd in plan_config.get('commands', [])}
            
            # Create logger
            workflow_logger = WorkflowLogger(output_path, workflow_name, task_id)

            # Create workflow manifest tracker
            plan_name = plan_config.get('title', plan_config.get('name', 'Unknown Plan'))
            manifest = WorkflowManifest(output_path, plan_name, workflow_name, task_id)

            # Log workflow steps for this folder
            logger.info(f"📋 Workflow steps for '{folder_name}': {workflow_steps}")
            
            # Notify start
            if self.progress_callback:
                self.progress_callback(task_id, {
                    "event_type": "workflow_start",
                    "workflow_steps": workflow_steps,
                    "total_steps": len(workflow_steps),
                    "folder_name": folder_name
                })
            
            # Execute each step
            for i, step_name in enumerate(workflow_steps):
                if self._cancelled:
                    return ProcessingResult(
                        task_id=task_id, success=False, folder_path=folder_path,
                        output_path=output_path, error_message="Cancelled",
                        execution_time=time.time() - start_time
                    )
                
                # Execute step
                # Get step configuration to extract output_scope
                step_config = commands.get(step_name, {})
                output_scope = step_config.get('output_scope', None)

                # Record step start in manifest
                manifest.start_step(i + 1, step_name, output_scope)

                # Notify step start
                if self.progress_callback:
                    self.progress_callback(task_id, {
                        "event_type": "step_start",
                        "step": step_name,
                        "folder_name": folder_name
                    })

                result = self._execute_step(step_name, commands[step_name], output_path, variables, workflow_logger, parallel_workers, skip_processing)

                # Record step completion in manifest
                step_success = result.get('success', True) and result.get('failed', 0) == 0
                manifest_path = self._find_tool_manifest(output_path, step_name)
                errors = [result.get('error')] if result.get('error') else None
                manifest.complete_step(i + 1, step_success, manifest_path, errors)
                
                # Stop on any error - check both success field and failed count
                if not result.get('success', True) or result.get('failed', 0) > 0:
                    if result.get('failed', 0) > 0:
                        error_msg = f"Step '{step_name}' failed: {result.get('failed', 0)} files failed to process"
                    else:
                        error_msg = f"Step '{step_name}' failed: {result.get('error', 'Unknown error')}"
                    
                    # Notify workflow completion (failed)
                    if self.progress_callback:
                        self.progress_callback(task_id, {
                            "event_type": "workflow_complete",
                            "success": False,
                            "error": error_msg,
                            "failed_step": step_name,
                            "folder_name": folder_name
                        })

                    # Finalize workflow manifest (failed)
                    manifest.finalize(success=False)

                    # Log failed completion
                    execution_time = time.time() - start_time
                    logger.error(f"❌ FAILED WORKFLOW for folder: '{folder_name}' at step '{step_name}' after {execution_time:.1f}s (task: {task_id[:8]}...)")

                    return ProcessingResult(
                        task_id=task_id, success=False, folder_path=folder_path,
                        output_path=output_path, error_message=error_msg,
                        execution_time=time.time() - start_time
                    )
                
                # Notify progress
                if self.progress_callback:
                    self.progress_callback(task_id, {
                        "event_type": "step_complete",
                        "step": step_name,
                        "progress": ((i + 1) / len(workflow_steps)) * 100,
                        "success": result.get('success', True) and result.get('failed', 0) == 0,
                        "result": result,
                        "folder_name": folder_name
                    })
            
            # Success
            # Notify workflow completion (success)
            if self.progress_callback:
                self.progress_callback(task_id, {
                    "event_type": "workflow_complete",
                    "success": True,
                    "total_steps": len(workflow_steps),
                    "folder_name": folder_name
                })

            # Finalize workflow manifest (success)
            manifest.finalize(success=True)

            # Log successful completion
            execution_time = time.time() - start_time
            logger.info(f"✅ COMPLETED WORKFLOW for folder: '{folder_name}' in {execution_time:.1f}s (task: {task_id[:8]}...)")

            return ProcessingResult(
                task_id=task_id, success=True, folder_path=folder_path,
                output_path=output_path, execution_time=time.time() - start_time
            )
            
        except Exception as e:
            error_msg = str(e)
            
            # Notify workflow completion (exception)
            if self.progress_callback:
                self.progress_callback(task_id, {
                    "event_type": "workflow_complete",
                    "success": False,
                    "error": error_msg,
                    "folder_name": folder_name
                })

            # Finalize workflow manifest (exception)
            if workflow_logger:
                manifest.finalize(success=False)

            # Log exception completion
            execution_time = time.time() - start_time
            logger.error(f"💥 EXCEPTION in workflow for folder: '{folder_name}' after {execution_time:.1f}s (task: {task_id[:8]}...): {error_msg}")

            return ProcessingResult(
                task_id=task_id, success=False, folder_path=folder_path,
                output_path=output_path, error_message=error_msg,
                execution_time=time.time() - start_time
            )
    
    def cancel(self):
        """Cancel execution"""
        self._cancelled = True
    
    def _execute_step(self, step_name: str, command_config: Dict, output_path: Path,
                     variables: Dict, workflow_logger: WorkflowLogger, parallel_workers: int = 1,
                     skip_processing: bool = False) -> Dict:
        """Execute a single step"""
        step_start = time.time()
        
        try:
            function_path = command_config['function']
            args = command_config.get('args', {})
            
            # Expand arguments
            expanded_args = {}
            for key, value in args.items():
                if isinstance(value, str) and '{' in value:
                    for var_key, var_value in variables.items():
                        value = value.replace(f'{{{var_key}}}', str(var_value))
                
                # Convert paths - but only if the value is actually a string path
                if (isinstance(value, str) and 
                    any(keyword in key.lower() for keyword in ['folder', 'path', 'manifest', 'config'])):
                    # Handle shared resources (yolo_models, prompts, etc.)
                    if value.startswith(('yolo_models/', 'prompts/')):
                        # Simple path resolution - no Toga app creation
                        resources_dir = Path(__file__).parent.parent / 'resources'
                        
                        # Map yolo_document.pt to the actual model file
                        if value.endswith('yolo_document.pt'):
                            expanded_args[key] = resources_dir / 'yolo_models' / 'yolov8s-fichero.pt'
                        else:
                            expanded_args[key] = resources_dir / value
                    # Handle resource files by filename (smart lookup)
                    elif any(keyword in key.lower() for keyword in ['config', 'model']):
                        # Simple path resolution - no Toga app creation
                        resources_dir = Path(__file__).parent.parent / 'resources'
                        
                        # Try to find the file in prompts/ or yolo_models/ directories
                        if key.lower() == 'prompt_config':
                            # Look for prompt config files
                            potential_paths = [
                                resources_dir / 'prompts' / value,
                                resources_dir / 'config_defaults' / 'prompts' / value
                            ]
                        elif 'model' in key.lower():
                            # Look for model files
                            potential_paths = [
                                resources_dir / 'yolo_models' / value,
                                resources_dir / 'models' / value
                            ]
                        else:
                            # Generic resource lookup
                            potential_paths = [
                                resources_dir / 'prompts' / value,
                                resources_dir / 'yolo_models' / value,
                                resources_dir / value
                            ]
                        
                        # Find the first existing path
                        for path in potential_paths:
                            if path.exists():
                                expanded_args[key] = path
                                break
                        else:
                            # If not found, use the first potential path as default
                            expanded_args[key] = potential_paths[0]
                    # Regular path handling
                    elif not value.startswith('/'):
                        # Special handling for "documents" folder - use documents_folder variable if available
                        if value == "documents" and 'documents_folder' in variables:
                            expanded_args[key] = Path(variables['documents_folder'])
                        else:
                            expanded_args[key] = output_path / value
                    else:
                        expanded_args[key] = Path(value)
                else:
                    # For non-string values (like booleans, integers), pass through as-is
                    expanded_args[key] = value
            
            # Add parallel processing parameter only for image processing tools and transcription that support it
            # Text processing tools (fuzzy_clean, recombine_segments) and post-transcription steps don't need this
            if any(keyword in function_path.lower() for keyword in ['crop', 'split', 'rotate', 'enhance', 'remove_background', 'segment', 'transcribe']):
                expanded_args['parallel_workers'] = parallel_workers

            # Add skip_processing parameter for tools that support fast testing mode
            if any(keyword in function_path.lower() for keyword in ['enhance', 'transcribe', 'segment', 'recombine', 'convert_to_word']):
                expanded_args['skip_processing'] = skip_processing
            
            # Log step start
            workflow_logger.log_step_start(step_name, function_path, expanded_args)
            
            # Import and call function
            module_path, function_name = function_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            function = getattr(module, function_name)
            
            # Execute with tool logger context set for workflow logging
            with self._set_tool_logger_context(workflow_logger, step_name):
                result = function(**expanded_args)
            
            execution_time = time.time() - step_start
            
            # Log completion
            workflow_logger.log_step_complete(step_name, result or {}, execution_time)
            
            return result or {'success': True}
            
        except Exception as e:
            execution_time = time.time() - step_start
            error_msg = str(e)
            
            # Log error
            workflow_logger.log_step_error(step_name, error_msg, execution_time)

            return {'success': False, 'error': error_msg}

    def _find_tool_manifest(self, output_path: Path, step_name: str) -> Optional[str]:
        """Find the tool manifest file for a given step

        Args:
            output_path: Root output directory for this processing run
            step_name: Name of the step (e.g., "transcribe_qwen_max")

        Returns:
            Relative path to the tool's manifest file (e.g., "assets/transcriptions/transcriptions_manifest.jsonl")
            or None if not found
        """
        # Look for manifest files matching the pattern *_manifest.jsonl or *_manifest.json
        manifest_files = list(output_path.rglob("*_manifest.jsonl")) + list(output_path.rglob("*_manifest.json"))

        if not manifest_files:
            return None

        # If there's only one manifest, return it
        if len(manifest_files) == 1:
            return str(manifest_files[0].relative_to(output_path))

        # If there are multiple manifests, try to match based on step name
        # For example, "transcribe_qwen_max" should match "transcriptions_manifest.jsonl"
        step_keywords = step_name.lower().split('_')

        for manifest_file in manifest_files:
            manifest_name = manifest_file.stem.lower()  # Get filename without extension
            # Check if any keyword from step name appears in manifest name
            if any(keyword in manifest_name for keyword in step_keywords):
                return str(manifest_file.relative_to(output_path))

        # Fallback: return the first manifest found
        return str(manifest_files[0].relative_to(output_path))