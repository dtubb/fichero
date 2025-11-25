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

    def __init__(self, output_path: Path, plan_name: str, workflow_name: str, task_id: str):
        """Initialize workflow manifest tracker

        Args:
            output_path: Root output directory for this processing run
            plan_name: Name of the plan being executed
            workflow_name: Name of the workflow being executed
            task_id: Unique task identifier
        """
        self.output_path = output_path
        self.plan_name = plan_name
        self.workflow_name = workflow_name
        self.task_id = task_id
        self.started_at = datetime.now()
        self.completed_at = None
        self.success = None
        self.steps = []

    def start_step(self, step_order: int, step_name: str, output_scope: Optional[str] = None):
        """Record start of a processing step

        Args:
            step_order: Order number of this step (1-indexed)
            step_name: Name of the step
            output_scope: Scope of outputs ("leaf", "node", "intermediate")
        """
        step_record = {
            "order": step_order,
            "name": step_name,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "outputs": [],
            "errors": [],
            "output_scope": output_scope
        }
        self.steps.append(step_record)
        logger.debug(f"📝 Manifest: Started step {step_order}: {step_name} (scope: {output_scope})")

    def complete_step(self, step_order: int, success: bool, manifest_path: Optional[str] = None,
                     errors: Optional[List[str]] = None):
        """Record completion of a processing step

        Args:
            step_order: Order number of this step (1-indexed)
            success: Whether the step completed successfully
            manifest_path: Relative path to the tool's manifest file (e.g. "assets/transcriptions/transcriptions_manifest.jsonl")
            errors: List of error messages
        """
        # Find the step record
        step = self.steps[step_order - 1]  # Convert to 0-indexed

        step["status"] = "success" if success else "failed"
        step["completed_at"] = datetime.now().isoformat()

        if manifest_path:
            step["manifest_file"] = manifest_path

        if errors:
            step["errors"] = errors

        logger.debug(f"📝 Manifest: Completed step {step_order}: {step['name']} ({'success' if success else 'failed'})")

    def finalize(self, success: bool):
        """Finalize workflow and write manifest to disk

        Args:
            success: Whether the overall workflow completed successfully
        """
        self.completed_at = datetime.now()
        self.success = success

        manifest = {
            "version": "1.0",
            "workflow": {
                "plan_name": self.plan_name,
                "workflow_name": self.workflow_name,
                "task_id": self.task_id,
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat(),
                "success": success,
                "duration_seconds": (self.completed_at - self.started_at).total_seconds()
            },
            "steps": self.steps
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
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read workflow manifest: {e}")
            return None
