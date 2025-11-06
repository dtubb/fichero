"""
Workflow Chaining System

Enables incremental processing by chaining tool outputs.
Tracks processing history and generates chained plans that use previous outputs as inputs.
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List

from .models import CollectionItem

logger = logging.getLogger(__name__)


class WorkflowChainer:
    """
    Manages workflow chaining for incremental processing.

    Tracks processing history and generates chained plans
    that use previous outputs as inputs.
    """

    def __init__(self, config_manager=None):
        """
        Initialize WorkflowChainer.

        Args:
            config_manager: ConfigManager instance for loading plans
        """
        self.config_manager = config_manager
        self.temp_dir = Path('/tmp/fichero_chained_plans')
        self.temp_dir.mkdir(exist_ok=True, parents=True)
        logger.info(f"WorkflowChainer initialized with temp dir: {self.temp_dir}")

    def get_last_output(self, item: CollectionItem) -> Dict[str, Optional[str]]:
        """
        Get the last processing output for an item.

        Args:
            item: CollectionItem to check

        Returns:
            dict with 'folder', 'manifest', and 'step' keys
        """
        metadata = item.metadata

        return {
            'folder': metadata.get('director_output_path', 'documents'),
            'manifest': metadata.get('director_manifest_path', 'assets/manifests/documents_manifest.jsonl'),
            'step': metadata.get('director_last_step', None)
        }

    def update_output_tracking(
        self,
        item: CollectionItem,
        output_folder: str,
        manifest_path: str,
        step_name: str
    ):
        """
        Update item metadata with latest output location.

        This is called after successful workflow completion.

        Args:
            item: CollectionItem to update
            output_folder: Path to output folder
            manifest_path: Path to output manifest
            step_name: Name of completed step
        """
        if 'completed_steps' not in item.metadata:
            item.metadata['completed_steps'] = []

        item.metadata['completed_steps'].append(step_name)
        item.metadata['director_output_path'] = output_folder
        item.metadata['director_manifest_path'] = manifest_path
        item.metadata['director_last_step'] = step_name

        logger.info(f"Updated output tracking for item {item.id}:")
        logger.info(f"  Output folder: {output_folder}")
        logger.info(f"  Manifest: {manifest_path}")
        logger.info(f"  Last step: {step_name}")

    def create_chained_plan(
        self,
        base_plan_path: str,
        workflow_name: str,
        source_folder: str,
        source_manifest: str,
        output_suffix: str = ''
    ) -> str:
        """
        Create a temporary chained plan file.

        Args:
            base_plan_path: Path to base plan YAML file
            workflow_name: Workflow to run (e.g., 'CropTest')
            source_folder: Previous output folder to use as input
            source_manifest: Previous manifest to use as input
            output_suffix: Optional suffix for output folder (for versioning)

        Returns:
            Path to generated temporary plan file
        """
        # Load base plan
        with open(base_plan_path, 'r') as f:
            plan_data = yaml.safe_load(f)

        # Verify workflow exists
        if workflow_name not in plan_data.get('workflows', {}):
            raise ValueError(f"Workflow '{workflow_name}' not found in plan '{base_plan_path}'")

        workflow_steps = plan_data['workflows'][workflow_name]

        # Modify all commands in the workflow to use chained source
        for cmd in plan_data.get('commands', []):
            if cmd['name'] in workflow_steps:
                # Skip manifest builders - they always use original documents
                if 'build_documents_manifest' in cmd['name']:
                    continue

                # Update source folder and manifest
                if 'source_folder' in cmd['args']:
                    logger.info(f"Updating command '{cmd['name']}' source_folder: {source_folder}")
                    cmd['args']['source_folder'] = source_folder

                if 'source_manifest' in cmd['args']:
                    logger.info(f"Updating command '{cmd['name']}' source_manifest: {source_manifest}")
                    cmd['args']['source_manifest'] = source_manifest

                # Update output folder with suffix if provided
                if output_suffix and 'output_folder' in cmd['args']:
                    original_output = cmd['args']['output_folder']
                    cmd['args']['output_folder'] = f"{original_output}{output_suffix}"

        # Write temporary plan
        base_name = Path(base_plan_path).stem
        temp_plan_name = f"{base_name}_Chained_{output_suffix or 'tmp'}.yml"
        temp_plan_path = self.temp_dir / temp_plan_name

        with open(temp_plan_path, 'w') as f:
            yaml.dump(plan_data, f, default_flow_style=False, allow_unicode=True)

        logger.info(f"✅ Created chained plan: {temp_plan_path}")
        logger.info(f"  Source folder: {source_folder}")
        logger.info(f"  Source manifest: {source_manifest}")
        logger.info(f"  Workflow: {workflow_name}")

        return str(temp_plan_path)

    def should_chain(self, item: CollectionItem) -> bool:
        """
        Determine if item has previous processing that can be chained.

        Args:
            item: CollectionItem to check

        Returns:
            True if item has previous outputs to chain from
        """
        has_output = (
            'director_output_path' in item.metadata and
            item.metadata['director_output_path'] != 'documents'
        )

        if has_output:
            logger.info(f"Item {item.id} has previous output, will chain from: {item.metadata['director_output_path']}")
        else:
            logger.info(f"Item {item.id} has no previous output, will start from documents")

        return has_output

    def reset_chain(self, item: CollectionItem):
        """
        Reset chaining for an item, starting fresh from documents folder.

        Args:
            item: CollectionItem to reset
        """
        logger.info(f"Resetting workflow chain for item {item.id}")

        # Clear chaining metadata
        item.metadata.pop('director_output_path', None)
        item.metadata.pop('director_manifest_path', None)
        item.metadata.pop('director_last_step', None)
        item.metadata.pop('completed_steps', None)

    def get_completed_steps(self, item: CollectionItem) -> List[str]:
        """
        Get list of completed processing steps for an item.

        Args:
            item: CollectionItem to check

        Returns:
            List of completed step names
        """
        return item.metadata.get('completed_steps', [])
