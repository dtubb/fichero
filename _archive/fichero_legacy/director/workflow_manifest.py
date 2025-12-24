"""
Workflow Manifest Writer

Writes a master manifest file that records:
- Workflow metadata (plan, workflow name, timestamps)
- Steps executed (in order)
- Success/failure status for each step
- Exact output file paths for each step

This manifest is used by the library backend for ingestion - no file searching needed!
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkflowManifest:
    """
    Tracks workflow execution and writes master manifest
    """

    def __init__(self, output_path: Path, plan_name: str, workflow_name: str, task_id: str,
                 library_item_id: Optional[str] = None, library_collection_id: Optional[str] = None,
                 library_item_map: Optional[Dict[str, str]] = None):
        """Initialize workflow manifest tracker

        Args:
            output_path: Root output directory for this processing run
            plan_name: Name of the plan being executed
            workflow_name: Name of the workflow being executed
            task_id: Unique task identifier
            library_item_id: Optional Library item_id (folder/file being processed)
            library_collection_id: Optional Library collection_id
            library_item_map: Optional mapping of filename -> item_id for file-level routing
        """
        self.output_path = output_path
        self.plan_name = plan_name
        self.workflow_name = workflow_name
        self.task_id = task_id
        self.started_at = datetime.now()
        self.completed_at = None
        self.success = None
        self.steps = []

        # Library integration fields (for proper metadata routing)
        self.library_item_id = library_item_id
        self.library_collection_id = library_collection_id
        self.library_item_map = library_item_map or {}

    def start_step(self, step_order: int, step_name: str, output_scope: Optional[str] = None):
        """Record start of a processing step

        Args:
            step_order: Order number of this step (1-indexed)
            step_name: Name of the step
            output_scope: Scope of outputs - where outputs should be routed:
                - "file": Route each output to corresponding source file (e.g., transcriptions)
                - "folder": Route all outputs to the parent folder (e.g., catalogues, summaries)
                - None: Use heuristic detection based on step name patterns
        """
        step_record = {
            "order": step_order,
            "name": step_name,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "outputs": [],
            "errors": [],
            "output_scope": output_scope  # "file", "folder", or None for heuristic
        }
        self.steps.append(step_record)
        logger.debug(f"📝 Manifest: Started step {step_order}: {step_name} (scope: {output_scope})")

    def complete_step(self, step_order: int, success: bool, manifest_path: Optional[str] = None,
                     errors: Optional[List[str]] = None, model_info: Optional[Dict] = None):
        """Record completion of a processing step

        Args:
            step_order: Order number of this step (1-indexed)
            success: Whether the step completed successfully
            manifest_path: Relative path to the tool's manifest file (e.g. "assets/transcriptions/transcriptions_manifest.jsonl")
            errors: List of error messages
            model_info: Optional dict with AI model/provider details:
                {
                    'model': 'qwen-vl-ocr',           # Model name
                    'provider': 'dashscope',          # Provider name
                    'model_version': '2.0',           # Model version
                    'api_endpoint': 'https://...',    # API endpoint used
                    'api_parameters': {               # Parameters used
                        'temperature': 0.7,
                        'max_tokens': 4096,
                        'top_p': 0.95
                    },
                    'usage': {                        # Token usage stats
                        'prompt_tokens': 1250,
                        'completion_tokens': 430,
                        'total_tokens': 1680,
                        'estimated_cost_usd': 0.0034
                    }
                }
        """
        # Find the step record
        step = self.steps[step_order - 1]  # Convert to 0-indexed

        step["status"] = "success" if success else "failed"
        step["completed_at"] = datetime.now().isoformat()

        if manifest_path:
            step["manifest_file"] = manifest_path

        if errors:
            step["errors"] = errors

        if model_info:
            step["model_info"] = model_info

        logger.debug(f"📝 Manifest: Completed step {step_order}: {step['name']} ({'success' if success else 'failed'})")

    def finalize(self, success: bool):
        """Finalize workflow and write manifest to disk

        Args:
            success: Whether the overall workflow completed successfully
        """
        self.completed_at = datetime.now()
        self.success = success

        manifest = {
            "version": "1.1",  # Version bump to indicate library fields
            "workflow": {
                "plan_name": self.plan_name,
                "workflow_name": self.workflow_name,
                "task_id": self.task_id,
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat(),
                "success": success,
                "duration_seconds": (self.completed_at - self.started_at).total_seconds()
            },
            "steps": self.steps,
            # Library integration fields - enables proper metadata routing
            # Include library section even if only item_map is available (critical for routing)
            "library": {
                "item_id": self.library_item_id,
                "collection_id": self.library_collection_id,
                "item_map": self.library_item_map  # filename -> item_id mapping
            } if (self.library_item_id or self.library_collection_id or self.library_item_map) else None
        }

        # Write to file
        manifest_path = self.output_path / "workflow_manifest.json"

        try:
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ Wrote workflow manifest to: {manifest_path}")
        except Exception as e:
            logger.error(f"❌ Failed to write workflow manifest: {e}")

    @staticmethod
    def read_manifest(output_path: Path) -> Optional[Dict]:
        """Read a workflow manifest from disk

        Args:
            output_path: Root output directory containing the manifest

        Returns:
            Manifest dict or None if not found/invalid
        """
        manifest_path = output_path / "workflow_manifest.json"

        if not manifest_path.exists():
            logger.warning(f"Workflow manifest not found: {manifest_path}")
            return None

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            # Validate manifest structure
            if not WorkflowManifest._validate_manifest_structure(manifest, manifest_path):
                return None

            return manifest
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in workflow manifest {manifest_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to read workflow manifest: {e}")
            return None

    @staticmethod
    def _validate_manifest_structure(manifest: Dict, manifest_path: Path) -> bool:
        """Validate workflow manifest has required structure

        Args:
            manifest: Parsed manifest dict
            manifest_path: Path for error messages

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(manifest, dict):
            logger.error(f"Workflow manifest is not a dict: {manifest_path}")
            return False

        # Check for required 'workflow' key
        if 'workflow' not in manifest:
            logger.error(f"Workflow manifest missing 'workflow' key: {manifest_path}")
            return False

        workflow_info = manifest['workflow']
        if not isinstance(workflow_info, dict):
            logger.error(f"Workflow manifest 'workflow' is not a dict: {manifest_path}")
            return False

        # Check for required 'steps' key
        if 'steps' not in manifest:
            logger.error(f"Workflow manifest missing 'steps' key: {manifest_path}")
            return False

        steps = manifest['steps']
        if not isinstance(steps, list):
            logger.error(f"Workflow manifest 'steps' is not a list: {manifest_path}")
            return False

        # Validate each step has required fields
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                logger.error(f"Workflow manifest step {idx} is not a dict: {manifest_path}")
                return False

            # Required fields for each step
            if 'name' not in step:
                logger.warning(f"Workflow manifest step {idx} missing 'name' field: {manifest_path}")
            if 'status' not in step:
                logger.warning(f"Workflow manifest step {idx} missing 'status' field: {manifest_path}")

        logger.debug(f"Workflow manifest validation passed: {manifest_path}")
        return True
