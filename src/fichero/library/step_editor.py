"""
Step Editor - Handle editing and saving workflow step data

This module provides functionality to:
- View step data (files, metadata, parameters)
- Edit step content (text, JSON, images)
- Save edits back to manifest files
- Support reprocessing from edited steps
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
import shutil

logger = logging.getLogger(__name__)


@dataclass
class StepData:
    """Complete data for a single processing step"""
    # Identification
    item_id: str
    step_index: int
    step_name: str
    tool_name: str

    # Files
    file_path: Path
    file_type: str  # "image", "text", "json", "document", "folder"

    # Manifest data
    manifest_path: Optional[Path] = None
    manifest_entry: Optional[Dict[str, Any]] = None

    # Content (lazy loaded)
    _file_content: Optional[Any] = None

    @property
    def file_content(self) -> Optional[Any]:
        """Lazy load file content"""
        if self._file_content is None and self.file_path and self.file_path.exists():
            self._file_content = self._load_content()
        return self._file_content

    def _load_content(self) -> Optional[Any]:
        """Load file content based on file type"""
        if self.file_type == "text":
            return self.file_path.read_text(encoding='utf-8')
        elif self.file_type == "json":
            return json.loads(self.file_path.read_text(encoding='utf-8'))
        # Images and documents are not loaded into memory
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CLI display/editing"""
        result = {
            'item_id': self.item_id,
            'step_index': self.step_index,
            'step_name': self.step_name,
            'tool_name': self.tool_name,
            'file_path': str(self.file_path),
            'file_type': self.file_type,
            'manifest_path': str(self.manifest_path) if self.manifest_path else None,
        }

        if self.manifest_entry:
            result['manifest_entry'] = self.manifest_entry

        # Include content for text/json files
        if self.file_type in ['text', 'json'] and self.file_content is not None:
            result['content'] = self.file_content

        return result


class StepEditor:
    """Handle step editing operations"""

    def __init__(self, library_manager):
        """
        Args:
            library_manager: LibraryManager instance
        """
        self.library_manager = library_manager
        self.logger = logging.getLogger(__name__)

    async def get_step_data(self, item_id: str, step_index: int) -> Optional[StepData]:
        """
        Get complete data for a specific step

        Args:
            item_id: Library item ID
            step_index: Step index (0-based)

        Returns:
            StepData object or None if not found
        """
        try:
            # Get all output data for the item
            output_data = await self.library_manager.get_item_output_data(item_id)

            if not output_data or not output_data.get('processing_steps'):
                self.logger.error(f"No processing steps found for item {item_id}")
                return None

            processing_steps = output_data['processing_steps']

            if step_index < 0 or step_index >= len(processing_steps):
                self.logger.error(f"Step index {step_index} out of range (0-{len(processing_steps)-1})")
                return None

            step = processing_steps[step_index]

            # Find manifest file for this step
            manifest_path = self._find_manifest_for_step(
                step.step_name,
                output_data.get('output_root')
            )

            # Get manifest entry if manifest exists
            manifest_entry = None
            if manifest_path and manifest_path.exists():
                manifest_entry = self._find_manifest_entry(
                    manifest_path,
                    step.file_path
                )

            # Create StepData object
            step_data = StepData(
                item_id=item_id,
                step_index=step_index,
                step_name=step.step_name,
                tool_name=step.step_name,
                file_path=step.file_path,
                file_type=step.file_type,
                manifest_path=manifest_path,
                manifest_entry=manifest_entry
            )

            self.logger.info(f"Retrieved step data: {step.step_name} at index {step_index}")
            return step_data

        except Exception as e:
            self.logger.error(f"Error getting step data: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    def _find_manifest_for_step(self, step_name: str, output_root: Path) -> Optional[Path]:
        """Find the manifest file for a given step"""
        if not output_root or not output_root.exists():
            return None

        # Common manifest naming patterns
        manifest_names = [
            f"{step_name}_manifest.jsonl",
            f"{step_name.lower()}_manifest.jsonl",
            "manifest.jsonl"
        ]

        for manifest_name in manifest_names:
            manifest_path = output_root / manifest_name
            if manifest_path.exists():
                return manifest_path

        return None

    def _find_manifest_entry(self, manifest_path: Path, file_path: Path) -> Optional[Dict[str, Any]]:
        """Find the manifest entry for a specific file"""
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        # Check if this entry matches the file
                        entry_file = entry.get('output_file') or entry.get('file')
                        if entry_file and Path(entry_file).name == file_path.name:
                            return entry
        except Exception as e:
            self.logger.error(f"Error reading manifest {manifest_path}: {e}")

        return None

    async def save_step_text(self, item_id: str, step_index: int, new_text: str) -> bool:
        """
        Save edited text content for a step

        Args:
            item_id: Library item ID
            step_index: Step index
            new_text: New text content

        Returns:
            True if successful
        """
        try:
            step_data = await self.get_step_data(item_id, step_index)

            if not step_data:
                self.logger.error("Could not find step data")
                return False

            if step_data.file_type != "text":
                self.logger.error(f"Step is not a text file (type: {step_data.file_type})")
                return False

            # Backup original file
            backup_path = step_data.file_path.with_suffix(step_data.file_path.suffix + '.backup')
            shutil.copy2(step_data.file_path, backup_path)
            self.logger.info(f"Created backup at {backup_path}")

            # Write new content
            step_data.file_path.write_text(new_text, encoding='utf-8')
            self.logger.info(f"Saved edited text to {step_data.file_path}")

            return True

        except Exception as e:
            self.logger.error(f"Error saving step text: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    async def save_step_json(self, item_id: str, step_index: int, new_json: Dict[str, Any]) -> bool:
        """
        Save edited JSON content for a step

        Args:
            item_id: Library item ID
            step_index: Step index
            new_json: New JSON data

        Returns:
            True if successful
        """
        try:
            step_data = await self.get_step_data(item_id, step_index)

            if not step_data:
                self.logger.error("Could not find step data")
                return False

            if step_data.file_type != "json":
                self.logger.error(f"Step is not a JSON file (type: {step_data.file_type})")
                return False

            # Backup original file
            backup_path = step_data.file_path.with_suffix(step_data.file_path.suffix + '.backup')
            shutil.copy2(step_data.file_path, backup_path)
            self.logger.info(f"Created backup at {backup_path}")

            # Write new content
            with open(step_data.file_path, 'w', encoding='utf-8') as f:
                json.dump(new_json, f, indent=2, ensure_ascii=False)

            self.logger.info(f"Saved edited JSON to {step_data.file_path}")

            return True

        except Exception as e:
            self.logger.error(f"Error saving step JSON: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    async def update_manifest_entry(
        self,
        item_id: str,
        step_index: int,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update metadata in the manifest file for a step

        Args:
            item_id: Library item ID
            step_index: Step index
            updates: Dictionary of fields to update in manifest entry

        Returns:
            True if successful
        """
        try:
            step_data = await self.get_step_data(item_id, step_index)

            if not step_data or not step_data.manifest_path:
                self.logger.error("No manifest found for this step")
                return False

            # Read all manifest entries
            entries = []
            with open(step_data.manifest_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))

            # Find and update the relevant entry
            updated = False
            for entry in entries:
                entry_file = entry.get('output_file') or entry.get('file')
                if entry_file and Path(entry_file).name == step_data.file_path.name:
                    entry.update(updates)
                    updated = True
                    break

            if not updated:
                self.logger.error("Could not find matching entry in manifest")
                return False

            # Backup original manifest
            backup_path = step_data.manifest_path.with_suffix('.jsonl.backup')
            shutil.copy2(step_data.manifest_path, backup_path)

            # Write updated manifest
            with open(step_data.manifest_path, 'w', encoding='utf-8') as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')

            self.logger.info(f"Updated manifest entry in {step_data.manifest_path}")
            return True

        except Exception as e:
            self.logger.error(f"Error updating manifest: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    async def update_step_parameters(
        self,
        item_id: str,
        step_index: int,
        new_parameters: Dict[str, Any]
    ) -> bool:
        """
        Update tool parameters for a specific step.

        This saves the edited parameters back to the manifest so the step
        can be reprocessed with the new parameters.

        Args:
            item_id: Library item ID
            step_index: Step index
            new_parameters: New tool parameters dictionary

        Returns:
            True if successful

        Example:
            # Update enhance parameters
            new_params = {
                'contrast_factor': 2.0,
                'brightness_adjustment': 0.1
            }
            success = await editor.update_step_parameters(
                'item-123',
                step_index=1,
                new_parameters=new_params
            )
        """
        try:
            self.logger.info(f"Updating parameters for item {item_id}, step {step_index}")
            self.logger.debug(f"New parameters: {new_parameters}")

            step_data = await self.get_step_data(item_id, step_index)

            if not step_data:
                self.logger.error("Could not find step data")
                return False

            if not step_data.manifest_path or not step_data.manifest_path.exists():
                self.logger.error("No manifest found for this step")
                return False

            # Read all manifest entries
            entries = []
            with open(step_data.manifest_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))

            # Find and update the relevant entry's parameters
            updated = False
            for entry in entries:
                # Match by output file or file path
                entry_file = entry.get('output_file') or entry.get('file')
                if entry_file and Path(entry_file).name == step_data.file_path.name:
                    # Update or add parameters field
                    if 'parameters' not in entry:
                        entry['parameters'] = {}
                    entry['parameters'].update(new_parameters)

                    # Add timestamp for tracking
                    entry['parameters_updated_at'] = datetime.now().isoformat()

                    updated = True
                    self.logger.info(f"Updated parameters for {entry_file}")
                    break

            if not updated:
                self.logger.error("Could not find matching entry in manifest")
                return False

            # Backup original manifest
            backup_path = step_data.manifest_path.with_suffix('.jsonl.backup')
            shutil.copy2(step_data.manifest_path, backup_path)
            self.logger.info(f"Created backup at {backup_path}")

            # Write updated manifest atomically
            temp_path = step_data.manifest_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            temp_path.replace(step_data.manifest_path)

            self.logger.info(f"Successfully updated step parameters in {step_data.manifest_path}")
            return True

        except Exception as e:
            self.logger.error(f"Error updating step parameters: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    def create_render_context(
        self,
        step_data: StepData,
        show_metadata: bool = True,
        show_content: bool = True,
        interactive: bool = False
    ):
        """
        Create a RenderContext from StepData for rendering.

        Args:
            step_data: StepData object
            show_metadata: Whether to show metadata
            show_content: Whether to show content
            interactive: Whether rendering for interactive GUI

        Returns:
            RenderContext object
        """
        from fichero.library.renderers import RenderContext

        return RenderContext(
            item_id=step_data.item_id,
            step_index=step_data.step_index,
            step_name=step_data.step_name,
            tool_name=step_data.tool_name,
            file_path=step_data.file_path,
            file_type=step_data.file_type,
            manifest_entry=step_data.manifest_entry,
            file_content=step_data.file_content,
            show_metadata=show_metadata,
            show_content=show_content,
            interactive=interactive
        )
