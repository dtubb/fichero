"""
Director Integration Service

Integrates Fichero Director with the Library system, enabling:
- Processing collection items using Director workflows
- Tracking processing status in Library
- Storing and retrieving Director outputs
"""

import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import shutil

from fichero.library.director_output_parser import DirectorOutputParser
from fichero.library.models import ProcessingResult
from fichero.shared.navigation.navigation_event_bus import emit_navigation_event

logger = logging.getLogger(__name__)


class DirectorIntegrationService:
    """Integrates Fichero Director with Library system"""

    def __init__(self, app, library_manager, director):
        """
        Initialize Director Integration Service

        Args:
            app: The main Toga application
            library_manager: LibraryManager instance
            director: FicheroDirector instance
        """
        self.app = app
        self.library_manager = library_manager
        self.director = director
        self.output_parser = DirectorOutputParser()

        # Track active processing tasks
        self.active_tasks: Dict[str, Dict] = {}  # task_id -> {item_id, collection_id, ...}

        # Register with TaskMonitor for progress updates
        if hasattr(director, 'task_monitor') and director.task_monitor:
            director.task_monitor.register_callback(self._on_task_monitor_update)
            logger.info("Registered with Director TaskMonitor for progress updates")

        logger.info("DirectorIntegrationService initialized")

    async def process_items(self, collection_id: str, item_ids: List[str],
                          plan_name: str, workflow_name: str = "default",
                          output_base_path: Optional[Path] = None) -> List[str]:
        """
        Process collection items using Director

        Intelligently batches multiple files together for efficient processing,
        while handling folders separately.

        Args:
            collection_id: ID of the collection
            item_ids: List of item IDs to process
            plan_name: Name of the Director plan to use
            workflow_name: Name of workflow within the plan
            output_base_path: Base path for outputs (defaults to app.paths.data)

        Returns:
            List of task IDs submitted to Director
        """
        logger.info(f"Processing {len(item_ids)} items from collection {collection_id}")

        # Default output path
        if output_base_path is None:
            output_base_path = Path(self.app.paths.data) / "processed"
        output_base_path.mkdir(parents=True, exist_ok=True)

        # Group items by type: files vs folders
        file_items = []
        folder_items = []

        for item_id in item_ids:
            item = await self.library_manager.get_item(item_id)
            if not item:
                logger.warning(f"Item {item_id} not found, skipping")
                continue

            input_path = Path(item.local_path or item.source_path)
            if not input_path.exists():
                logger.warning(f"Item path does not exist: {input_path}, skipping")
                continue

            if item.type == "folder":
                folder_items.append((item_id, item, input_path))
            else:
                file_items.append((item_id, item, input_path))

        task_ids = []

        # Process all files together in a single batch
        if file_items:
            batch_task_ids = await self._process_file_batch(
                file_items, output_base_path, plan_name, workflow_name
            )
            task_ids.extend(batch_task_ids)

        # Process folders individually (they may have subfolders)
        for item_id, item, input_path in folder_items:
            item_output_path = output_base_path / f"{item.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            item_output_path.mkdir(parents=True, exist_ok=True)

            try:
                submitted_task_ids = await self._process_folder_structure(
                    item_id, input_path, item_output_path, plan_name, workflow_name
                )
                task_ids.extend(submitted_task_ids)

                # Update item metadata
                item.metadata['director_status'] = 'pending'
                item.metadata['director_workflow'] = workflow_name
                item.metadata['director_output_path'] = str(item_output_path)
                await self.library_manager.update_item(item)

            except Exception as e:
                logger.error(f"Error processing folder {item_id}: {e}")
                item.metadata['director_status'] = 'failed'
                item.metadata['director_error'] = str(e)
                await self.library_manager.update_item(item)

        logger.info(f"Submitted {len(task_ids)} tasks to Director")
        return task_ids

    async def _process_file_batch(self, file_items: List[tuple],
                                  output_base_path: Path, plan_name: str,
                                  workflow_name: str) -> List[str]:
        """
        Process multiple files together as a single batch

        Args:
            file_items: List of (item_id, item, input_path) tuples
            output_base_path: Base output path
            plan_name: Plan name
            workflow_name: Workflow name

        Returns:
            List of task IDs (typically one for the whole batch)
        """
        logger.info(f"Processing batch of {len(file_items)} files")

        # Create batch output folder
        batch_name = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        batch_output_path = output_base_path / batch_name
        batch_output_path.mkdir(parents=True, exist_ok=True)

        # Create input folder and copy all files
        batch_input_folder = batch_output_path / "input"
        batch_input_folder.mkdir(parents=True, exist_ok=True)

        # Track which items are in this batch
        batch_item_map = {}  # filename -> item_id

        for item_id, item, input_path in file_items:
            # Copy file to batch folder
            dest_file = batch_input_folder / input_path.name

            # Handle name collisions
            counter = 1
            while dest_file.exists():
                stem = input_path.stem
                suffix = input_path.suffix
                dest_file = batch_input_folder / f"{stem}_{counter}{suffix}"
                counter += 1

            shutil.copy2(input_path, dest_file)
            batch_item_map[dest_file.name] = item_id

            # Update item metadata
            item.metadata['director_status'] = 'pending'
            item.metadata['director_workflow'] = workflow_name
            item.metadata['director_output_path'] = str(batch_output_path)
            item.metadata['director_batch_file'] = dest_file.name
            await self.library_manager.update_item(item)

        # Submit batch to Director
        task_id = self.director.processing_coordinator.process_folders(
            folders=[batch_input_folder],
            plan_name=plan_name,
            workflow_name=workflow_name,
            output_path=batch_output_path
        )

        # Track this batch task
        self.active_tasks[task_id] = {
            'item_ids': [item_id for item_id, _, _ in file_items],
            'item_map': batch_item_map,
            'type': 'batch',
            'output_path': str(batch_output_path),
            'started_at': datetime.now()
        }

        logger.info(f"Submitted batch task {task_id} for {len(file_items)} files")
        return [task_id]

    async def _process_single_file(self, item_id: str, input_path: Path,
                                   output_path: Path, plan_name: str,
                                   workflow_name: str) -> Optional[str]:
        """
        Process a single file using Director

        Args:
            item_id: Collection item ID
            input_path: Path to the file
            output_path: Output directory
            plan_name: Plan name
            workflow_name: Workflow name

        Returns:
            Task ID or None if submission failed
        """
        logger.info(f"Processing single file: {input_path}")

        # Create a temp folder structure for the single file
        # Director expects folders, so we create: temp_folder/documents/filename
        temp_input_folder = output_path / "input"
        temp_input_folder.mkdir(parents=True, exist_ok=True)

        # Copy file to temp folder
        temp_file = temp_input_folder / input_path.name
        shutil.copy2(input_path, temp_file)

        # Submit to Director using process_folders
        task_id = self.director.processing_coordinator.process_folders(
            folders=[temp_input_folder],
            plan_name=plan_name,
            workflow_name=workflow_name,
            output_path=output_path
        )

        # Track this task
        self.active_tasks[task_id] = {
            'item_id': item_id,
            'type': 'file',
            'input_path': str(input_path),
            'output_path': str(output_path),
            'started_at': datetime.now()
        }

        return task_id

    async def _process_folder_structure(self, item_id: str, input_path: Path,
                                       output_path: Path, plan_name: str,
                                       workflow_name: str) -> List[str]:
        """
        Process a folder with auto-detection (folder-of-folders)

        Args:
            item_id: Collection item ID
            input_path: Path to the folder
            output_path: Output directory
            plan_name: Plan name
            workflow_name: Workflow name

        Returns:
            List of task IDs (one per subfolder detected)
        """
        logger.info(f"Processing folder structure: {input_path}")

        # Use Director's auto-detection
        task_ids = self.director.processing_coordinator.process_with_auto_detection(
            input_path=input_path,
            output_path=output_path,
            plan_name=plan_name,
            workflow_name=workflow_name
        )

        # Track all tasks
        for task_id in task_ids:
            self.active_tasks[task_id] = {
                'item_id': item_id,
                'type': 'folder',
                'input_path': str(input_path),
                'output_path': str(output_path),
                'started_at': datetime.now()
            }

        return task_ids

    def _on_task_monitor_update(self, event_type: str, task_info):
        """
        Handle updates from Director's TaskMonitor

        Args:
            event_type: Type of event (task_created, task_updated, task_completed)
            task_info: TaskInfo object from TaskMonitor
        """
        logger.debug(f"TaskMonitor event: {event_type} for task {task_info.task_id}")

        task_id = task_info.task_id

        # Only handle our tracked tasks
        if task_id not in self.active_tasks:
            return

        # Convert TaskInfo to progress data format
        progress_data = {
            'progress': task_info.overall_progress,
            'status': task_info.status,
            'current_step': task_info.current_step,
            'completed_steps': task_info.completed_steps,
            'total_steps': task_info.total_steps
        }

        # Get our task info
        our_task_info = self.active_tasks.get(task_id)
        if not our_task_info:
            return

        # Handle batch vs single item tasks
        if our_task_info.get('type') == 'batch':
            # Update all items in batch
            item_ids = our_task_info.get('item_ids', [])
            for item_id in item_ids:
                self._update_item_progress(item_id, task_id, progress_data)
        else:
            # Single item
            item_id = our_task_info.get('item_id')
            if item_id:
                self._update_item_progress(item_id, task_id, progress_data)

        # Check if task completed
        if event_type == 'task_completed':
            # Schedule finalization
            asyncio.create_task(self._finalize_processing(task_id))

    def _update_item_progress(self, item_id: str, task_id: str, progress_data: Dict):
        """
        Update a single item's progress

        Args:
            item_id: Item ID
            task_id: Task ID
            progress_data: Progress information
        """
        try:
            # Get item (sync version for callback)
            item = self.library_manager.storage.get_item(item_id)
            if item:
                item.metadata['director_task_id'] = task_id
                item.metadata['director_progress'] = progress_data.get('progress', 0)
                item.metadata['director_status'] = progress_data.get('status', 'running')

                # Update in storage
                self.library_manager.storage.update_item(item)

                # Emit event for UI refresh
                emit_navigation_event('collection_item_updated', {
                    'item_id': item_id,
                    'progress': progress_data.get('progress', 0)
                })
        except Exception as e:
            logger.error(f"Error updating item {item_id} progress: {e}")

    async def _finalize_processing(self, task_id: str):
        """
        Finalize processing when task completes

        Args:
            task_id: Task ID that completed
        """
        logger.info(f"Finalizing processing for task {task_id}")

        task_info = self.active_tasks.get(task_id)
        if not task_info:
            logger.warning(f"Cannot finalize unknown task: {task_id}")
            return

        output_path = Path(task_info['output_path'])

        try:
            # Get task result from Director
            result = self.director.get_task_result(task_id)

            # Parse output folder
            parsed_outputs = self.output_parser.parse_output_folder(output_path)

            # Handle batch vs single item
            if task_info.get('type') == 'batch':
                await self._finalize_batch(task_id, task_info, result, parsed_outputs)
            else:
                await self._finalize_single_item(task_id, task_info, result, parsed_outputs)

            logger.info(f"Processing finalized for task {task_id}")

        except Exception as e:
            logger.error(f"Error finalizing processing for task {task_id}: {e}")

            # Update all affected items with error
            item_ids = task_info.get('item_ids', [task_info.get('item_id')])
            for item_id in item_ids:
                if item_id:
                    try:
                        item = await self.library_manager.get_item(item_id)
                        if item:
                            item.metadata['director_status'] = 'failed'
                            item.metadata['director_error'] = str(e)
                            await self.library_manager.update_item(item)
                    except Exception as update_error:
                        logger.error(f"Error updating item {item_id} after finalization error: {update_error}")

        finally:
            # Remove from active tasks
            self.active_tasks.pop(task_id, None)

    async def _finalize_single_item(self, task_id: str, task_info: Dict, result, parsed_outputs: Dict):
        """Finalize a single item task"""
        item_id = task_info['item_id']
        output_path = Path(task_info['output_path'])

        # Get item
        item = await self.library_manager.get_item(item_id)
        if not item:
            logger.error(f"Item {item_id} not found during finalization")
            return

        # Create ProcessingResult record
        processing_result = ProcessingResult(
            item_id=item_id,
            workflow=task_info.get('workflow', 'unknown'),
            status='success' if result and result.success else 'failed',
            started_at=task_info['started_at'],
            completed_at=datetime.now(),
            output_paths=[str(output_path)],
            logs_path=str(output_path / "logs") if (output_path / "logs").exists() else None,
            metadata={
                'task_id': task_id,
                'parsed_outputs': {
                    'input_files': len(parsed_outputs.get('input_files', [])),
                    'prepared_files': len(parsed_outputs.get('prepared_files', [])),
                    'transcriptions': len(parsed_outputs.get('transcriptions', [])),
                    'word_docs': len(parsed_outputs.get('word_docs', []))
                }
            },
            processing_time=(datetime.now() - task_info['started_at']).total_seconds()
        )

        # Save processing result
        await self.library_manager.add_processing_result(processing_result)

        # Update item metadata
        item.metadata['director_status'] = 'success' if result and result.success else 'failed'
        item.metadata['director_task_id'] = task_id
        item.metadata['director_progress'] = 100
        if result and not result.success:
            item.metadata['director_error'] = str(result.error_message)

        await self.library_manager.update_item(item)

        # Emit completion event
        emit_navigation_event('processing_completed', {
            'item_id': item_id,
            'task_id': task_id,
            'status': 'success' if result and result.success else 'failed'
        })

    async def _finalize_batch(self, task_id: str, task_info: Dict, result, parsed_outputs: Dict):
        """Finalize a batch task with multiple items"""
        item_ids = task_info['item_ids']
        item_map = task_info.get('item_map', {})
        output_path = Path(task_info['output_path'])

        # Get all file outputs from the batch
        all_file_outputs = self.output_parser.get_all_file_outputs(output_path)

        for item_id in item_ids:
            item = await self.library_manager.get_item(item_id)
            if not item:
                logger.warning(f"Item {item_id} not found during batch finalization")
                continue

            # Find this item's outputs by matching filename
            batch_filename = item.metadata.get('director_batch_file')
            if batch_filename:
                # Find outputs for this specific file
                item_outputs = [
                    fo for fo in all_file_outputs
                    if fo.original_file and fo.original_file.name == batch_filename
                ]
            else:
                item_outputs = []

            # Create ProcessingResult record for this item
            processing_result = ProcessingResult(
                item_id=item_id,
                workflow=task_info.get('workflow', 'unknown'),
                status='success' if result and result.success else 'failed',
                started_at=task_info['started_at'],
                completed_at=datetime.now(),
                output_paths=[str(output_path)],
                logs_path=str(output_path / "logs") if (output_path / "logs").exists() else None,
                metadata={
                    'task_id': task_id,
                    'batch_task': True,
                    'batch_file': batch_filename,
                    'item_outputs': len(item_outputs)
                },
                processing_time=(datetime.now() - task_info['started_at']).total_seconds()
            )

            # Save processing result
            await self.library_manager.add_processing_result(processing_result)

            # Update item metadata
            item.metadata['director_status'] = 'success' if result and result.success else 'failed'
            item.metadata['director_task_id'] = task_id
            item.metadata['director_progress'] = 100
            if result and not result.success:
                item.metadata['director_error'] = str(result.error_message)

            await self.library_manager.update_item(item)

            # Emit completion event for each item
            emit_navigation_event('processing_completed', {
                'item_id': item_id,
                'task_id': task_id,
                'status': 'success' if result and result.success else 'failed'
            })

    def get_processing_status(self, item_id: str) -> Optional[Dict]:
        """
        Get processing status for an item

        Args:
            item_id: Collection item ID

        Returns:
            Dict with status info or None
        """
        # Find active task for this item
        for task_id, task_info in self.active_tasks.items():
            if task_info['item_id'] == item_id:
                status = self.director.get_task_status(task_id)
                return {
                    'task_id': task_id,
                    'status': status,
                    'started_at': task_info['started_at']
                }
        return None

    async def cancel_processing(self, item_id: str) -> bool:
        """
        Cancel processing for an item

        Args:
            item_id: Collection item ID

        Returns:
            True if cancelled successfully
        """
        # Find active task for this item
        for task_id, task_info in self.active_tasks.items():
            if task_info['item_id'] == item_id:
                success = self.director.cancel_task(task_id)
                if success:
                    # Update item status
                    item = await self.library_manager.get_item(item_id)
                    if item:
                        item.metadata['director_status'] = 'cancelled'
                        await self.library_manager.update_item(item)

                    # Remove from active tasks
                    self.active_tasks.pop(task_id, None)

                return success

        return False
