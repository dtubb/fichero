"""
StepManager - Unified step management for OutputView

This is the single source of truth for workflow output steps.
All data comes from LibraryManager - no legacy file-based paths.

PHASE 4 ENHANCEMENT: Added StepState, event callbacks, and multi-item navigation.
"""

import logging
from typing import List, Optional, Dict, Any, Callable
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Step:
    """Represents a single processing step with all its data"""
    # Core identification
    step_name: str
    tool_name: str
    step_number: int

    # File information
    file_path: Path
    file_type: str  # "image", "text", "json", "document", "folder"

    # Metadata
    description: str = ""
    parameters: Dict[str, Any] = None

    # Workflow context
    plan_name: str = ""
    workflow_name: str = ""
    prompt_used: str = ""

    # Status
    status: str = "completed"  # "completed", "failed", "partial"
    error_message: str = ""

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


@dataclass
class StepState:
    """
    Current navigation state.

    PHASE 4: Comprehensive state tracking for UI updates.
    """
    item_id: str
    step_index: int
    total_steps: int
    file_index: int
    total_files: int
    can_go_prev_step: bool
    can_go_next_step: bool
    can_go_prev_file: bool
    can_go_next_file: bool


class StepManager:
    """
    Manages workflow steps for an item with navigation and state tracking.

    Single responsibility: Get step data from LibraryManager and provide it
    in a clean, consistent format to OutputView.

    NO file scanning, NO manifest parsing - Library does that.

    PHASE 4 ENHANCEMENTS:
    - Event callbacks for state changes
    - Multi-item navigation (file list)
    - Comprehensive StepState tracking
    """

    def __init__(self, library_manager):
        """
        Args:
            library_manager: LibraryManager instance (required)
        """
        if not library_manager:
            raise ValueError("library_manager is required - Library is the source of truth")

        self.library_manager = library_manager
        self.logger = logging.getLogger(__name__)

        # Current state
        self.current_item_id: Optional[str] = None
        self.steps: List[Step] = []
        self.current_step_index: int = 0

        # PHASE 4: Multi-item navigation
        self.item_ids: List[str] = []  # List of item IDs for file navigation
        self.current_file_index: int = 0  # Current position in item_ids list

        # PHASE 4: Event callback for state changes
        self.on_state_changed: Optional[Callable[[StepState], None]] = None

        # Prevent recursive state change emissions
        self._emitting_state_change: bool = False

        # Folder state (when viewing folder outputs)
        self.is_folder: bool = False
        self.folder_steps_by_name: Dict[str, List[Step]] = {}

    async def load_item(self, item_id: str) -> bool:
        """
        Load steps for an item from the library.

        Args:
            item_id: Library item ID

        Returns:
            True if steps were loaded (including original file), False on error
        """
        try:
            self.logger.info(f"Loading steps for item: {item_id}")
            self.current_item_id = item_id

            # Get item metadata to find original file
            item_metadata = await self.library_manager.get_item(item_id)

            # Initialize steps list with the original file as step 0
            self.steps = []

            if item_metadata:
                # Add original file as first step
                # CollectionItem has: source_path (original), local_path (if copied)
                original_path = item_metadata.source_path or item_metadata.local_path
                if original_path:
                    # Determine file type from extension
                    ext = Path(original_path).suffix.lower()
                    file_type = 'image' if ext in ['.tif', '.tiff', '.jpg', '.jpeg', '.png'] else 'unknown'

                    original_step = Step(
                        step_name='Original',
                        tool_name='original',
                        step_number=0,
                        file_path=Path(original_path),
                        file_type=file_type,
                        description='Original source file'
                    )
                    self.steps.append(original_step)
                    self.logger.info(f"Added original file as step 0: {original_path}")

            # Get output data from library (single source of truth)
            output_data = await self.library_manager.get_item_output_data(item_id)

            if not output_data or not output_data.get('processing_steps'):
                self.logger.info(f"No processing outputs found for item {item_id} - showing original file only")
                self.is_folder = False
                # Still return True because we have the original file
                return True

            # Extract processing steps
            processing_steps = output_data.get('processing_steps', [])
            self.is_folder = output_data.get('is_folder', False)

            self.logger.info(f"Found {len(processing_steps)} processing steps, is_folder={self.is_folder}")

            # Convert library's ProcessingStep objects to our Step objects
            # These are appended AFTER the original file
            for ps in processing_steps:
                step = Step(
                    step_name=ps.step_name if hasattr(ps, 'step_name') else 'Unknown',
                    tool_name=ps.step_name if hasattr(ps, 'step_name') else 'unknown',
                    step_number=ps.step_number if hasattr(ps, 'step_number') else 0,
                    file_path=ps.file_path if hasattr(ps, 'file_path') else Path(),
                    file_type=ps.file_type if hasattr(ps, 'file_type') else 'unknown',
                    description=ps.description if hasattr(ps, 'description') else ''
                )
                self.steps.append(step)

            # If folder, organize steps by name
            if self.is_folder:
                self._organize_folder_steps()

            self.logger.info(f"Loaded {len(self.steps)} total steps (including original)")
            return True

        except Exception as e:
            self.logger.error(f"Error loading item steps: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.steps = []
            return False

    def _organize_folder_steps(self):
        """Organize folder steps by step name for filtering"""
        self.folder_steps_by_name = {}

        for step in self.steps:
            step_name = step.step_name
            if step_name not in self.folder_steps_by_name:
                self.folder_steps_by_name[step_name] = []
            self.folder_steps_by_name[step_name].append(step)

        self.logger.info(f"Organized folder steps: {len(self.folder_steps_by_name)} unique step names")

    def get_step(self, index: int) -> Optional[Step]:
        """Get step at index"""
        if 0 <= index < len(self.steps):
            return self.steps[index]
        return None

    def get_current_step(self) -> Optional[Step]:
        """Get currently selected step"""
        return self.get_step(self.current_step_index)

    def get_step_names(self) -> List[str]:
        """Get list of unique step names (for dropdown)"""
        if self.is_folder:
            # For folders, return unique step names in order
            seen = set()
            names = []
            for step in self.steps:
                if step.step_name not in seen:
                    names.append(step.step_name)
                    seen.add(step.step_name)
            return names
        else:
            # For files, return all step names
            return [step.step_name for step in self.steps]

    def set_current_step(self, index: int) -> bool:
        """Set current step index (PHASE 4: now emits events)"""
        if 0 <= index < len(self.steps):
            self.current_step_index = index
            self._emit_state_change()  # PHASE 4: emit event
            return True
        return False

    def next_step(self) -> bool:
        """Move to next step, returns True if successful (PHASE 4: now emits events)"""
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
            self._emit_state_change()  # PHASE 4: emit event
            return True
        return False

    def prev_step(self) -> bool:
        """Move to previous step, returns True if successful (PHASE 4: now emits events)"""
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self._emit_state_change()  # PHASE 4: emit event
            return True
        return False

    def has_next_step(self) -> bool:
        """Check if there's a next step"""
        return self.current_step_index < len(self.steps) - 1

    def has_prev_step(self) -> bool:
        """Check if there's a previous step"""
        return self.current_step_index > 0

    def get_steps_by_name(self, step_name: str) -> List[Step]:
        """Get all steps with a given name (for folder view)"""
        if self.is_folder:
            return self.folder_steps_by_name.get(step_name, [])
        return []

    def clear(self):
        """Clear all steps"""
        self.steps = []
        self.current_step_index = 0
        self.current_item_id = None
        self.is_folder = False
        self.folder_steps_by_name = {}
        # Don't clear item_ids and current_file_index - preserve file list

    # ==================== PHASE 4: NEW METHODS ====================

    async def load_item_list(self, item_ids: List[str], initial_index: int = 0):
        """
        Load a list of items for file navigation (PHASE 4).

        Args:
            item_ids: List of library item IDs to navigate between
            initial_index: Which item to load initially (default: 0)

        Example:
            await manager.load_item_list(['item-1', 'item-2', 'item-3'], initial_index=0)
        """
        self.item_ids = item_ids
        self.current_file_index = min(initial_index, len(item_ids) - 1)

        if self.item_ids:
            await self.load_item(self.item_ids[self.current_file_index])
        else:
            self.logger.warning("load_item_list called with empty list")

    def get_state(self) -> StepState:
        """
        Get current navigation state (PHASE 4).

        Returns:
            StepState with all navigation info
        """
        return StepState(
            item_id=self.current_item_id or "",
            step_index=self.current_step_index,
            total_steps=len(self.steps),
            file_index=self.current_file_index,
            total_files=len(self.item_ids),
            can_go_prev_step=self.has_prev_step(),
            can_go_next_step=self.has_next_step(),
            can_go_prev_file=self.current_file_index > 0,
            can_go_next_file=self.current_file_index < len(self.item_ids) - 1
        )

    async def next_file(self) -> bool:
        """
        Navigate to next file in list (PHASE 4).

        Returns:
            True if navigated successfully, False if at end or no file list
        """
        if self.current_file_index < len(self.item_ids) - 1:
            self.current_file_index += 1
            await self.load_item(self.item_ids[self.current_file_index])
            self._emit_state_change()
            return True
        return False

    async def prev_file(self) -> bool:
        """
        Navigate to previous file in list (PHASE 4).

        Returns:
            True if navigated successfully, False if at beginning or no file list
        """
        if self.current_file_index > 0:
            self.current_file_index -= 1
            await self.load_item(self.item_ids[self.current_file_index])
            self._emit_state_change()
            return True
        return False

    async def go_to_file(self, file_index: int) -> bool:
        """
        Jump to specific file in list (PHASE 4).

        Args:
            file_index: Index in item_ids list

        Returns:
            True if navigated successfully, False if index out of range
        """
        if 0 <= file_index < len(self.item_ids):
            self.current_file_index = file_index
            await self.load_item(self.item_ids[self.current_file_index])
            self._emit_state_change()
            return True
        return False

    async def get_current_step_data(self) -> Optional[Dict[str, Any]]:
        """
        Get current step's full data from library (PHASE 4).

        Returns:
            Dictionary with step data including metadata, or None if no current step
        """
        if not self.current_item_id:
            return None

        try:
            # Get full output data from library
            output_data = await self.library_manager.get_item_output_data(self.current_item_id)

            if not output_data:
                return None

            # Get current step from our list
            current_step = self.get_current_step()
            if not current_step:
                return None

            # Build comprehensive step data
            return {
                'item_id': self.current_item_id,
                'step_index': self.current_step_index,
                'step_name': current_step.step_name,
                'tool_name': current_step.tool_name,
                'step_number': current_step.step_number,
                'file_path': current_step.file_path,
                'file_type': current_step.file_type,
                'description': current_step.description,
                'parameters': current_step.parameters,
                'plan_name': current_step.plan_name,
                'workflow_name': current_step.workflow_name,
                'status': current_step.status,
                'error_message': current_step.error_message,
                # Include full output data for renderer
                'output_data': output_data
            }
        except Exception as e:
            self.logger.error(f"Error getting current step data: {e}")
            return None

    def _emit_state_change(self):
        """
        Emit state change event (PHASE 4).

        Called automatically after navigation changes.
        Uses a guard flag to prevent recursive calls.
        """
        # Prevent recursive state change emissions
        if self._emitting_state_change:
            return

        if self.on_state_changed:
            try:
                self._emitting_state_change = True
                state = self.get_state()
                self.on_state_changed(state)
            except Exception as e:
                self.logger.error(f"Error emitting state change: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
            finally:
                self._emitting_state_change = False
