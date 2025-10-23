"""
Director Integration Service

Integrates Fichero Director with the Library system, enabling:
- Processing collection items using Director workflows
- Tracking processing status in Library
- Storing and retrieving Director outputs
"""

import logging
import asyncio
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

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

    def _generate_output_structure(self, collection_name: str, collection_id: str,
                                   item_name: str, workflow_name: str, plan_name: str,
                                   base_path: Path) -> Path:
        """
        Generate hierarchical, human-readable output structure for large-scale processing

        For 800 folders with 100,000 files, creates organized structure:

        output_base/
        └── [collection_name]/
            └── [date]/
                └── [workflow_name]/
                    └── [item_name]/

        This makes it easy to:
        - Find processing by collection
        - Group by date
        - Separate workflows
        - Identify individual items

        Args:
            collection_name: Human-readable collection name
            collection_id: Collection UUID
            item_name: Name of item being processed
            workflow_name: Workflow being used
            plan_name: Plan being used
            base_path: Base output directory

        Returns:
            Full path to item output directory
        """
        # Sanitize names for filesystem
        def sanitize(name: str, max_length: int = 100) -> str:
            # Keep only safe characters
            safe = "".join(c if c.isalnum() or c in (' ', '-', '_', '.') else '_' for c in name)
            # Replace multiple underscores/spaces with single
            safe = ' '.join(safe.split())
            safe = safe.replace(' ', '_')
            return safe[:max_length]

        safe_collection = sanitize(collection_name)
        safe_item = sanitize(item_name)
        safe_workflow = sanitize(workflow_name, 50)

        # Date-based organization (YYYY-MM-DD format for human readability)
        date_folder = datetime.now().strftime('%Y-%m-%d')

        # Build hierarchical path
        output_path = (
            base_path /
            safe_collection /  # Collection level
            date_folder /      # Date level (groups processing runs)
            safe_workflow /    # Workflow level (Catalogue, Quotations, etc.)
            safe_item          # Item level (individual folder/batch)
        )

        # If path already exists (rare duplicate), append counter
        if output_path.exists():
            counter = 1
            while output_path.with_name(f"{safe_item}_{counter}").exists():
                counter += 1
            output_path = output_path.with_name(f"{safe_item}_{counter}")

        return output_path

    async def process_collection(self, collection_id: str, plan_name: str,
                                workflow_name: str = "Catalogue",
                                progress_callback=None,
                                output_base_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Process an entire collection using Director (GUI-compatible wrapper)

        This is a convenience wrapper that processes all items in a collection.
        Used by GUI (library_service.py) to maintain API compatibility.

        Args:
            collection_id: ID of the collection to process
            plan_name: Name of the Director plan to use
            workflow_name: Name of workflow within the plan
            progress_callback: Optional callback for progress updates
            output_base_path: Optional custom output path (defaults to library storage)

        Returns:
            Dict with processing results: {'success': bool, 'task_ids': List[str], ...}
        """
        try:
            # Get all items in collection
            items = await self.library_manager.get_collection_items(collection_id)
            if not items:
                logger.warning(f"No items found in collection {collection_id}")
                return {
                    'success': False,
                    'error': 'No items in collection',
                    'task_ids': []
                }

            item_ids = [item.id for item in items]
            logger.info(f"Processing {len(item_ids)} items from collection {collection_id}")

            # Call the existing process_items method
            task_ids = await self.process_items(
                collection_id=collection_id,
                item_ids=item_ids,
                plan_name=plan_name,
                workflow_name=workflow_name,
                output_base_path=output_base_path  # Pass through output path (None = use library storage)
            )

            if task_ids:
                return {
                    'success': True,
                    'task_ids': task_ids,
                    'item_count': len(item_ids)
                }
            else:
                return {
                    'success': False,
                    'error': 'No tasks were submitted',
                    'task_ids': []
                }

        except Exception as e:
            logger.error(f"Failed to process collection {collection_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'task_ids': []
            }

    async def process_items(self, collection_id: str, item_ids: List[str],
                          plan_name: str, workflow_name: str = "Catalogue",
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

        # Get collection info for naming
        collection = await self.library_manager.get_collection(collection_id)
        if not collection:
            logger.error(f"Collection {collection_id} not found")
            return []

        collection_name = collection.name

        # Default output path - PRIORITY: Use library storage (collection's local_path)
        if output_base_path is None:
            # FIRST: Try to use collection's local_path within library (matches CLI behavior)
            if collection.local_path:
                # Store outputs within collection's library directory
                collection_base = Path(collection.local_path)
                output_base_path = collection_base / "outputs"
                logger.info(f"Using collection's library path for outputs: {output_base_path}")
            else:
                # FALLBACK: Check settings for custom processing output path
                custom_path = None
                if hasattr(self.app, 'settings') and self.app.settings:
                    try:
                        # Check if settings is not a Mock
                        from unittest.mock import Mock
                        if not isinstance(self.app.settings, Mock):
                            custom_path = self.app.settings.get_setting('library.processing_output_path', '')
                    except:
                        pass

                # Use custom path if valid, otherwise use library default
                if custom_path and isinstance(custom_path, str) and custom_path.strip():
                    try:
                        custom_path_obj = Path(custom_path)
                        if custom_path_obj.exists():
                            output_base_path = custom_path_obj
                        else:
                            logger.warning(f"Custom processing path does not exist: {custom_path}, using library default")
                            output_base_path = Path(self.app.paths.data) / "library" / "outputs"
                    except Exception as e:
                        logger.warning(f"Invalid custom path: {custom_path}, using library default: {e}")
                        output_base_path = Path(self.app.paths.data) / "library" / "outputs"
                else:
                    # Final fallback: Library outputs directory
                    output_base_path = Path(self.app.paths.data) / "library" / "outputs"
                    logger.info(f"Using library default for outputs: {output_base_path}")

        output_base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using output base path: {output_base_path}")

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

        # Process files
        # IMPORTANT: If only ONE file is being processed (single selection), process just that file
        # Otherwise, batch multiple files together for efficiency
        if file_items:
            single_file_selection = len(file_items) == 1 and len(item_ids) == 1

            if single_file_selection:
                # Single selected file - process only that file
                item_id, item, input_path = file_items[0]
                logger.info(f"Processing single selected file: {input_path}")

                # Generate output path for single file
                item_output_path = self._generate_output_structure(
                    collection_name=collection_name,
                    collection_id=collection_id,
                    item_name=item.name,
                    workflow_name=workflow_name,
                    plan_name=plan_name,
                    base_path=output_base_path
                )
                item_output_path.mkdir(parents=True, exist_ok=True)

                # Process single file
                task_id = await self._process_single_file(
                    item_id, input_path, item_output_path, plan_name, workflow_name
                )
                if task_id:
                    task_ids.append(task_id)

                    # Update item metadata
                    item.metadata['director_status'] = 'pending'
                    item.metadata['director_workflow'] = workflow_name
                    item.metadata['director_output_path'] = str(item_output_path)
                    await self.library_manager.update_item(item)
            else:
                # Multiple files - process as batch
                logger.info(f"Processing {len(file_items)} files as batch")
                batch_task_ids = await self._process_file_batch(
                    file_items, output_base_path, plan_name, workflow_name,
                    collection_name, collection_id
                )
                task_ids.extend(batch_task_ids)

        # Process folders
        # IMPORTANT: If only ONE folder is being processed (single selection), don't use auto-detection
        # Auto-detection would find all subfolders and process them separately
        # When user selects a single folder, they want THAT FOLDER processed as a unit
        single_folder_selection = len(folder_items) == 1 and len(item_ids) == 1

        for item_id, item, input_path in folder_items:
            # Generate hierarchical output structure
            item_output_path = self._generate_output_structure(
                collection_name=collection_name,
                collection_id=collection_id,
                item_name=item.name,
                workflow_name=workflow_name,
                plan_name=plan_name,
                base_path=output_base_path
            )
            item_output_path.mkdir(parents=True, exist_ok=True)

            try:
                if single_folder_selection:
                    # Single selected folder - process directly without auto-detection
                    logger.info(f"Processing single selected folder (no auto-detection): {input_path}")
                    submitted_task_ids = await self._process_single_folder(
                        item_id, input_path, item_output_path, plan_name, workflow_name
                    )
                else:
                    # Multiple folders or "Process All" - use auto-detection
                    logger.info(f"Processing folder with auto-detection: {input_path}")
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
                                  workflow_name: str, collection_name: str,
                                  collection_id: str) -> List[str]:
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

        # Create hierarchical batch output structure
        batch_output_path = self._generate_output_structure(
            collection_name=collection_name,
            collection_id=collection_id,
            item_name=f"batch_{len(file_items)}_files",
            workflow_name=workflow_name,
            plan_name=plan_name,
            base_path=output_base_path
        )
        batch_output_path.mkdir(parents=True, exist_ok=True)

        # NO COPYING - Process files from their original locations
        # Collect unique parent directories of all files
        parent_dirs = set()
        batch_item_map = {}  # filename -> item_id

        for item_id, item, input_path in file_items:
            parent_dir = input_path.parent
            parent_dirs.add(parent_dir)
            batch_item_map[input_path.name] = item_id

            # Update item metadata
            item.metadata['director_status'] = 'pending'
            item.metadata['director_workflow'] = workflow_name
            item.metadata['director_output_path'] = str(batch_output_path)
            item.metadata['director_source_file'] = str(input_path)
            await self.library_manager.update_item(item)

        # If all files are in the same parent directory, process that folder
        # Otherwise, we need to process files from their individual locations
        if len(parent_dirs) == 1:
            # All files are in the same folder - process the folder
            source_folder = list(parent_dirs)[0]
            task_id = self.director.processing_coordinator.process_folders(
                folders=[source_folder],
                plan_name=plan_name,
                workflow_name=workflow_name,
                output_path=batch_output_path
            )
        else:
            # Files are in different folders - process each parent folder
            # This is a batch of files from different locations
            logger.warning(f"Batch contains files from {len(parent_dirs)} different folders - processing individually")
            task_ids_list = []
            for parent_dir in parent_dirs:
                task_id = self.director.processing_coordinator.process_folders(
                    folders=[parent_dir],
                    plan_name=plan_name,
                    workflow_name=workflow_name,
                    output_path=batch_output_path / parent_dir.name
                )
                task_ids_list.append(task_id)
            # For now, return the first task ID (we'll improve this later)
            task_id = task_ids_list[0] if task_ids_list else None
            if not task_id:
                logger.error("Failed to submit any tasks")
                return []

        # Track this batch task
        self.active_tasks[task_id] = {
            'item_ids': [item_id for item_id, _, _ in file_items],
            'item_map': batch_item_map,
            'type': 'batch',
            'output_path': str(batch_output_path),
            'plan_name': plan_name,
            'workflow': workflow_name,
            'started_at': datetime.now()
        }

        logger.info(f"✅ Submitted batch task {task_id} for {len(file_items)} files")
        logger.info(f"   Output path: {batch_output_path}")
        logger.info(f"   Active tasks: {len(self.active_tasks)}")

        # Log TaskMonitor status
        if hasattr(self.director, 'task_monitor') and self.director.task_monitor:
            task_count = len(self.director.task_monitor.tasks)
            logger.info(f"   TaskMonitor tracking {task_count} task(s)")
            if task_id in self.director.task_monitor.tasks:
                logger.info(f"   ✅ Task {task_id[:8]}... registered in TaskMonitor")
            else:
                logger.warning(f"   ⚠️  Task {task_id[:8]}... NOT in TaskMonitor yet")

        return [task_id]

    async def _process_single_file(self, item_id: str, input_path: Path,
                                   output_path: Path, plan_name: str,
                                   workflow_name: str) -> Optional[str]:
        """
        Process a single file using Director

        Creates a staging folder in the library's output directory containing only
        the specified file (via symlink), then processes it from there. All outputs
        stay in the library folder for reliable tracking.

        Args:
            item_id: Collection item ID
            input_path: Path to the file
            output_path: Output directory (in library)
            plan_name: Plan name
            workflow_name: Workflow name

        Returns:
            Task ID or None if submission failed
        """
        logger.info(f"Processing single file: {input_path}")

        # Create staging folder WITHIN the library's output directory
        # This ensures all processing happens in library-controlled space
        import os

        staging_dir = output_path / "_staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Create symlink to the file in staging directory
            staging_file_link = staging_dir / input_path.name

            # Remove existing symlink if present (from previous runs)
            if staging_file_link.exists() or staging_file_link.is_symlink():
                staging_file_link.unlink()

            os.symlink(input_path, staging_file_link)
            logger.info(f"Created staging folder in library: {staging_dir}")

            # Submit to Director using the staging folder
            # Pass actual filename as display_name so Activity Monitor shows it instead of staging folder name
            task_id = self.director.processing_coordinator.process_folders(
                folders=[staging_dir],
                plan_name=plan_name,
                workflow_name=workflow_name,
                output_path=output_path,
                document_context={'display_name': input_path.name}  # Show actual filename, not staging folder
            )

            # Track this task (NO temp dir - everything stays in library)
            self.active_tasks[task_id] = {
                'item_id': item_id,
                'type': 'file',
                'input_path': str(input_path),
                'output_path': str(output_path),
                'staging_dir': str(staging_dir),  # Track for cleanup
                'plan_name': plan_name,
                'workflow': workflow_name,
                'started_at': datetime.now()
            }

            logger.info(f"✅ Submitted single file task {task_id} for {input_path.name}")
            logger.info(f"   Library output path: {output_path}")
            return task_id

        except Exception as e:
            logger.error(f"Failed to process single file {input_path}: {e}")
            raise

    async def _process_single_folder(self, item_id: str, input_path: Path,
                                     output_path: Path, plan_name: str,
                                     workflow_name: str) -> List[str]:
        """
        Process a single folder directly (no auto-detection)

        Used when user explicitly selects a single folder to process.
        Processes the folder as a unit, without detecting subfolders.

        Args:
            item_id: Collection item ID
            input_path: Path to the folder
            output_path: Output directory
            plan_name: Plan name
            workflow_name: Workflow name

        Returns:
            List with single task ID
        """
        logger.info(f"Processing single folder (no auto-detection): {input_path}")

        # Library already created the right output path - use it directly
        # For in-place mode: documents_folder = source location, output_folder = library path
        # For copy mode: would need to copy files first (not implemented yet)

        # In-place processing: source files stay where they are
        documents_folder = input_path

        # Create required subdirectories in the library output path
        (output_path / "assets").mkdir(parents=True, exist_ok=True)
        (output_path / "logs").mkdir(parents=True, exist_ok=True)

        logger.info(f"Library processing - output: {output_path}, documents: {documents_folder}")

        # Process the folder using process_folders with properly formatted dict
        task_id = self.director.processing_coordinator.process_folders(
            folders=[{
                'output_folder': output_path,
                'documents_folder': documents_folder
            }],
            plan_name=plan_name,
            workflow_name=workflow_name,
            output_path=output_path
        )

        # Track this task
        self.active_tasks[task_id] = {
            'item_id': item_id,
            'type': 'folder',
            'input_path': str(input_path),
            'output_path': str(output_path),
            'plan_name': plan_name,
            'workflow': workflow_name,
            'started_at': datetime.now()
        }

        logger.info(f"✅ Submitted single folder task {task_id} for {input_path}")
        return [task_id]

    async def _process_folder_structure(self, item_id: str, input_path: Path,
                                       output_path: Path, plan_name: str,
                                       workflow_name: str) -> List[str]:
        """
        Process a folder with auto-detection (folder-of-folders)

        Used when processing multiple folders or "Process All".
        Auto-detection finds subfolders and processes them separately.

        Args:
            item_id: Collection item ID
            input_path: Path to the folder
            output_path: Output directory
            plan_name: Plan name
            workflow_name: Workflow name

        Returns:
            List of task IDs (one per subfolder detected)
        """
        logger.info(f"Processing folder structure with auto-detection: {input_path}")

        # Use Director's auto-detection
        task_ids = self.director.processing_coordinator.process_with_auto_detection(
            input_path=input_path,
            output_path=output_path,
            plan_name=plan_name,
            workflow_name=workflow_name
        )

        logger.info(f"📊 Auto-detection returned {len(task_ids) if task_ids else 0} task IDs: {task_ids}")

        # Track all tasks
        if task_ids:
            for task_id in task_ids:
                self.active_tasks[task_id] = {
                    'item_id': item_id,
                    'type': 'folder',
                    'input_path': str(input_path),
                    'output_path': str(output_path),
                    'plan_name': plan_name,
                    'workflow': workflow_name,
                    'started_at': datetime.now()
                }
                logger.info(f"📊 Tracked task {task_id} in active_tasks for item {item_id}")
        else:
            logger.warning(f"⚠️ No task IDs returned from auto-detection for {input_path}")

        return task_ids if task_ids else []

    def _on_task_monitor_update(self, event_type: str, task_info):
        """
        Handle updates from Director's TaskMonitor

        Args:
            event_type: Type of event (task_created, task_updated, task_completed)
            task_info: TaskInfo object from TaskMonitor
        """
        logger.info(f"📊 Received TaskMonitor event: {event_type} for task {task_info.task_id}")

        task_id = task_info.task_id

        # Only handle our tracked tasks
        if task_id not in self.active_tasks:
            logger.info(f"📊 Task {task_id} not in active_tasks, ignoring (active: {list(self.active_tasks.keys())})")
            return

        logger.info(f"📊 Task {task_id} IS in active_tasks, processing event")

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
            # Check if already finalizing (prevents duplicate finalization)
            if task_id not in self.active_tasks:
                logger.info(f"📊 Task {task_id} already being finalized, skipping duplicate")
                return

            # Remove from active tasks IMMEDIATELY to prevent duplicate finalization
            task_info_copy = self.active_tasks.pop(task_id, None)
            if not task_info_copy:
                logger.warning(f"Task {task_id} not in active_tasks during completion")
                return

            logger.info(f"📊 Task {task_id} COMPLETED - starting finalization")
            # Schedule finalization in a background thread to avoid event loop conflicts
            # This is safe because _finalize_processing creates its own event loop
            def finalize_in_thread():
                try:
                    logger.info(f"📊 Finalization thread started for {task_id}")
                    # Call synchronous finalization directly (no event loop needed)
                    # Pass task_info copy since we removed it from active_tasks
                    self._finalize_processing_with_info(task_id, task_info_copy)
                    logger.info(f"📊 Finalization completed for {task_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to finalize processing for {task_id}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # Run finalization in background thread
            thread = threading.Thread(target=finalize_in_thread, daemon=True)
            thread.start()
            logger.info(f"📊 Finalization thread launched for {task_id}")

    def _update_item_progress(self, item_id: str, task_id: str, progress_data: Dict):
        """
        Update a single item's progress (THREAD-SAFE)

        This is called from TaskMonitor callbacks which run in background threads.
        GUI updates MUST be dispatched to the main thread to avoid crashes.

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

                # Update in storage (thread-safe database operation)
                self.library_manager.storage.update_item(item)

                # CRITICAL: Dispatch GUI update to main thread
                # emit_navigation_event triggers GUI updates (NSTableView) which MUST happen on main thread
                # Using call_soon_threadsafe ensures thread safety
                if hasattr(self.app, 'loop') and self.app.loop:
                    self.app.loop.call_soon_threadsafe(
                        emit_navigation_event,
                        'collection_item_updated',
                        {
                            'item_id': item_id,
                            'progress': progress_data.get('progress', 0)
                        }
                    )
                else:
                    # Fallback: skip GUI update if loop not available
                    logger.debug(f"Skipping GUI update (no event loop): item {item_id}")
        except Exception as e:
            logger.error(f"Error updating item {item_id} progress: {e}")

    def _finalize_processing_with_info(self, task_id: str, task_info: Dict):
        """
        Finalize processing when task completes (synchronous version)

        Args:
            task_id: Task ID that completed
            task_info: Task information (passed as parameter since task is removed from active_tasks)
        """
        logger.info(f"📊 _finalize_processing STARTED for task {task_id}")

        if not task_info:
            logger.warning(f"Cannot finalize task {task_id}: no task_info provided")
            return

        logger.info(f"📊 Task info retrieved: {task_info}")
        output_path = Path(task_info['output_path'])
        logger.info(f"📊 Output path: {output_path}")

        try:
            # Get task result from Director
            logger.info(f"📊 Getting task result from Director")
            result = self.director.get_task_result(task_id)
            logger.info(f"📊 Task result retrieved: {result}")

            # Parse output folder
            logger.info(f"📊 Parsing output folder")
            parsed_outputs = self.output_parser.parse_output_folder(output_path)
            logger.info(f"📊 Output folder parsed")

            # Handle batch vs single item
            if task_info.get('type') == 'batch':
                self._finalize_batch(task_id, task_info, result, parsed_outputs)
            else:
                self._finalize_single_item(task_id, task_info, result, parsed_outputs)

            logger.info(f"📊 Processing finalized for task {task_id}")

        except Exception as e:
            logger.error(f"Error finalizing processing for task {task_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Update all affected items with error
            item_ids = task_info.get('item_ids', [task_info.get('item_id')])
            for item_id in item_ids:
                if item_id:
                    try:
                        item = self.library_manager.storage.get_item(item_id)
                        if item:
                            item.metadata['director_status'] = 'failed'
                            item.metadata['director_error'] = str(e)
                            self.library_manager.storage.update_item(item)
                    except Exception as update_error:
                        logger.error(f"Error updating item {item_id} after finalization error: {update_error}")

        # Note: Task was already removed from active_tasks before finalization started

    def _finalize_single_item(self, task_id: str, task_info: Dict, result, parsed_outputs: Dict):
        """Finalize a single item task (synchronous version)"""
        item_id = task_info['item_id']
        output_path = Path(task_info['output_path'])

        logger.info(f"📊 Finalizing single item {item_id}")

        # Get item (use storage directly for sync access)
        item = self.library_manager.storage.get_item(item_id)
        if not item:
            logger.error(f"Item {item_id} not found during finalization")
            return

        logger.info(f"📊 Item retrieved, creating comprehensive ProcessingResult")

        # Build comprehensive artifact tracking metadata
        artifacts_metadata = self._build_artifacts_metadata(output_path, parsed_outputs, task_info, result)

        # Create ProcessingResult record with comprehensive tracking
        processing_result = ProcessingResult(
            item_id=item_id,
            workflow=task_info.get('workflow', 'unknown'),
            status='success' if result and result.success else 'failed',
            started_at=task_info['started_at'],
            completed_at=datetime.now(),
            output_paths=[str(output_path)],
            logs_path=str(output_path / "logs") if (output_path / "logs").exists() else None,
            metadata=artifacts_metadata,
            processing_time=(datetime.now() - task_info['started_at']).total_seconds()
        )

        # Save processing result (use storage directly for sync access)
        logger.info(f"📊 Saving ProcessingResult to database")
        self.library_manager.storage.add_processing_result(processing_result)
        logger.info(f"📊 ProcessingResult saved")

        # Update item metadata
        item.metadata['director_status'] = 'success' if result and result.success else 'failed'
        item.metadata['director_task_id'] = task_id
        item.metadata['director_progress'] = 100
        if result and not result.success:
            item.metadata['director_error'] = str(result.error_message)

        logger.info(f"📊 Updating item metadata")
        self.library_manager.storage.update_item(item)
        logger.info(f"📊 Item updated")

        # Clean up staging directory if this was a single file task
        # Staging dir is inside library, so cleanup is safe
        staging_dir = task_info.get('staging_dir')
        if staging_dir:
            try:
                import shutil
                staging_path = Path(staging_dir)
                if staging_path.exists():
                    shutil.rmtree(staging_path)
                    logger.info(f"🗑️  Cleaned up staging directory: {staging_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up staging directory {staging_dir}: {e}")

        # CRITICAL: Dispatch GUI update to main thread
        # emit_navigation_event triggers GUI updates which MUST happen on main thread
        if hasattr(self.app, 'loop') and self.app.loop:
            self.app.loop.call_soon_threadsafe(
                emit_navigation_event,
                'processing_completed',
                {
                    'item_id': item_id,
                    'task_id': task_id,
                    'status': 'success' if result and result.success else 'failed'
                }
            )
            logger.info(f"📊 Completion event dispatched to main thread")
        else:
            logger.debug(f"Skipping completion event (no event loop): item {item_id}")

    def _build_artifacts_metadata(self, output_path: Path, parsed_outputs: Dict,
                                   task_info: Dict, result) -> Dict[str, Any]:
        """
        Build comprehensive artifact tracking metadata for UI display

        Systematically tracks:
        - Plan and workflow used
        - All processing steps executed
        - Logs for each step
        - Success/failure status per step
        - All manifest files
        - Output files per step

        Args:
            output_path: Path to processing output directory
            parsed_outputs: Parsed outputs from DirectorOutputParser
            task_info: Task information dictionary
            result: Processing result from Director

        Returns:
            Dict with comprehensive artifact metadata
        """
        logger.info("📦 Building comprehensive artifacts metadata")

        metadata = {
            'task_id': task_info.get('task_id'),
            'plan_name': task_info.get('plan_name', 'unknown'),
            'workflow_name': task_info.get('workflow', 'unknown'),
            'input_path': task_info.get('input_path'),
            'steps': [],
            'manifests': {},
            'logs': {},
            'summary': {
                'total_steps': 0,
                'successful_steps': 0,
                'failed_steps': 0,
                'skipped_steps': 0
            }
        }

        # Track all manifests systematically
        assets_dir = output_path / "assets"
        if assets_dir.exists():
            # 1. Documents manifest
            manifests_dir = assets_dir / "manifests"
            if manifests_dir.exists():
                docs_manifest = manifests_dir / "documents_manifest.jsonl"
                if docs_manifest.exists():
                    metadata['manifests']['documents'] = str(docs_manifest)
                    step_data = self._parse_manifest_for_step(
                        'build_documents_manifest', docs_manifest, output_path
                    )
                    if step_data:
                        metadata['steps'].append(step_data)

            # 2. Prepared images step
            prepared_dir = assets_dir / "prepared"
            if prepared_dir.exists():
                prep_manifest = prepared_dir / "prepare_images_manifest.jsonl"
                if prep_manifest.exists():
                    metadata['manifests']['prepare_images'] = str(prep_manifest)
                    step_data = self._parse_manifest_for_step(
                        'prepare_images', prep_manifest, output_path
                    )
                    if step_data:
                        metadata['steps'].append(step_data)

            # 3. Transcription step
            transcriptions_dir = assets_dir / "transcriptions"
            if transcriptions_dir.exists():
                trans_manifest = transcriptions_dir / "transcriptions_manifest.jsonl"
                if trans_manifest.exists():
                    metadata['manifests']['transcriptions'] = str(trans_manifest)
                    step_data = self._parse_manifest_for_step(
                        'transcribe', trans_manifest, output_path
                    )
                    if step_data:
                        metadata['steps'].append(step_data)

            # 4. Word conversion step
            word_dir = assets_dir / "word"
            if word_dir.exists():
                word_manifest = word_dir / "convert_to_word_manifest.jsonl"
                if word_manifest.exists():
                    metadata['manifests']['convert_to_word'] = str(word_manifest)
                    step_data = self._parse_manifest_for_step(
                        'convert_to_word', word_manifest, output_path
                    )
                    if step_data:
                        metadata['steps'].append(step_data)

            # 5. LLM catalogue step
            llm_dir = assets_dir / "llm_catalogue"
            if llm_dir.exists():
                llm_manifest = llm_dir / "llm_process_manifest.jsonl"
                if llm_manifest.exists():
                    metadata['manifests']['llm_catalogue'] = str(llm_manifest)
                    step_data = self._parse_manifest_for_step(
                        'catalogue_folder', llm_manifest, output_path
                    )
                    if step_data:
                        metadata['steps'].append(step_data)

        # Track logs
        logs_dir = output_path / "logs"
        if logs_dir.exists():
            for log_file in logs_dir.glob("*.log"):
                metadata['logs'][log_file.stem] = str(log_file)

        # Calculate summary
        metadata['summary']['total_steps'] = len(metadata['steps'])
        for step in metadata['steps']:
            if step['status'] == 'success':
                metadata['summary']['successful_steps'] += 1
            elif step['status'] == 'failed':
                metadata['summary']['failed_steps'] += 1
            elif step['status'] == 'skipped':
                metadata['summary']['skipped_steps'] += 1

        # Add file counts from parsed outputs
        metadata['file_counts'] = {
            'input_files': len(parsed_outputs.get('input_files', [])),
            'prepared_files': len(parsed_outputs.get('prepared_files', [])),
            'transcriptions': len(parsed_outputs.get('transcriptions', [])),
            'word_docs': len(parsed_outputs.get('word_docs', []))
        }

        logger.info(f"📦 Built metadata: {metadata['summary']['total_steps']} steps tracked")
        return metadata

    def _parse_manifest_for_step(self, step_name: str, manifest_path: Path,
                                  output_path: Path) -> Optional[Dict[str, Any]]:
        """
        Parse a manifest file to extract step execution details

        Args:
            step_name: Name of the processing step
            manifest_path: Path to manifest.jsonl file
            output_path: Base output path

        Returns:
            Dict with step details or None if parsing fails
        """
        import json

        try:
            step_data = {
                'step_name': step_name,
                'manifest_path': str(manifest_path),
                'status': 'unknown',
                'processed_files': 0,
                'successful_files': 0,
                'failed_files': 0,
                'skipped_files': 0,
                'outputs': [],
                'errors': []
            }

            with open(manifest_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                        step_data['processed_files'] += 1

                        # Check status
                        if entry.get('success'):
                            if entry.get('skipped'):
                                step_data['skipped_files'] += 1
                            else:
                                step_data['successful_files'] += 1
                        else:
                            step_data['failed_files'] += 1
                            if 'error' in entry:
                                step_data['errors'].append({
                                    'file': entry.get('source', 'unknown'),
                                    'error': entry['error']
                                })

                        # Track outputs
                        if 'outputs' in entry and entry['outputs']:
                            step_data['outputs'].extend(entry['outputs'])

                    except json.JSONDecodeError:
                        continue

            # Determine overall step status
            if step_data['failed_files'] > 0:
                step_data['status'] = 'partial' if step_data['successful_files'] > 0 else 'failed'
            elif step_data['skipped_files'] == step_data['processed_files']:
                step_data['status'] = 'skipped'
            elif step_data['successful_files'] > 0:
                step_data['status'] = 'success'

            return step_data

        except Exception as e:
            logger.warning(f"Failed to parse manifest {manifest_path}: {e}")
            return None

    def _finalize_batch(self, task_id: str, task_info: Dict, result, parsed_outputs: Dict):
        """Finalize a batch task with multiple items (synchronous version)"""
        item_ids = task_info['item_ids']
        item_map = task_info.get('item_map', {})
        output_path = Path(task_info['output_path'])

        logger.info(f"📊 Finalizing batch with {len(item_ids)} items")

        # Get all file outputs from the batch
        all_file_outputs = self.output_parser.get_all_file_outputs(output_path)

        for item_id in item_ids:
            # Get item (use storage directly for sync access)
            item = self.library_manager.storage.get_item(item_id)
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

            # Save processing result (use storage directly for sync access)
            self.library_manager.storage.add_processing_result(processing_result)
            logger.debug(f"📊 Saved ProcessingResult for batch item {item_id}")

            # Update item metadata
            item.metadata['director_status'] = 'success' if result and result.success else 'failed'
            item.metadata['director_task_id'] = task_id
            item.metadata['director_progress'] = 100
            if result and not result.success:
                item.metadata['director_error'] = str(result.error_message)

            # Update in storage (use storage directly for sync access)
            self.library_manager.storage.update_item(item)
            logger.debug(f"📊 Updated batch item {item_id}")

            # CRITICAL: Dispatch GUI update to main thread
            # emit_navigation_event triggers GUI updates which MUST happen on main thread
            if hasattr(self.app, 'loop') and self.app.loop:
                self.app.loop.call_soon_threadsafe(
                    emit_navigation_event,
                    'processing_completed',
                    {
                        'item_id': item_id,
                        'task_id': task_id,
                        'status': 'success' if result and result.success else 'failed'
                    }
                )
            else:
                logger.debug(f"Skipping completion event (no event loop): item {item_id}")

        logger.info(f"📊 Batch finalization complete for {len(item_ids)} items")

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
