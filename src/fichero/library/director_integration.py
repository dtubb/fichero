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
from fichero.library.models import ProcessingResult, ProcessingOutput, ExtractedMetadata
from fichero.library.metadata_extractors import UniversalExtractor
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
        self.metadata_extractor = UniversalExtractor(library_manager.storage)

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

        collection_id/outputs/    <- base_path already points here
        └── [date]/
            └── [workflow_name]/
                └── [item_name]/

        This makes it easy to:
        - Group by date
        - Separate workflows
        - Identify individual items

        Args:
            collection_name: Human-readable collection name (not used in path)
            collection_id: Collection UUID
            item_name: Name of item being processed
            workflow_name: Workflow being used
            plan_name: Plan being used
            base_path: Base output directory (already collection_id/outputs)

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

        safe_item = sanitize(item_name)
        safe_workflow = sanitize(workflow_name, 50)

        # Date and time-based organization (YYYY-MM-DD_HH-MM-SS for multiple runs per day)
        date_folder = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

        # Build hierarchical path (base_path is already collection_id/outputs)
        output_path = (
            base_path /
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
                # FALLBACK: Construct path from library base + collection_id (handles legacy data)
                # For internal/local collections without local_path set, construct from library path
                library_base = Path(self.app.paths.data) / "library" / "collections"
                collection_path = library_base / collection_id

                # Check if collection folder exists (indicates internal collection)
                if collection_path.exists():
                    output_base_path = collection_path / "outputs"
                    logger.info(f"Using constructed collection path for outputs: {output_base_path}")
                else:
                    # External collection or other case - check settings for custom output path
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
        # IMPORTANT: Group files by their parent folder
        # Files in the same parent folder = ONE catalogue
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
                    item_id, input_path, item_output_path, plan_name, workflow_name, collection_id
                )
                if task_id:
                    task_ids.append(task_id)

                    # Update item status (processing will be tracked in ProcessingResult table)
                    item.status = 'processing'
                    await self.library_manager.update_item(item)
            else:
                # Multiple files - group them by parent_id
                # Files with same parent_id = one catalogue
                from collections import defaultdict
                files_by_parent = defaultdict(list)

                for item_id, item, input_path in file_items:
                    parent_key = item.parent_id if item.parent_id else "_root_"
                    files_by_parent[parent_key].append((item_id, item, input_path))

                logger.info(f"Grouped {len(file_items)} files into {len(files_by_parent)} catalogue groups by parent folder")

                # Process each group as one catalogue
                import tempfile
                import os
                import shutil

                for parent_key, group_files in files_by_parent.items():
                    if len(group_files) == 1:
                        # Single file in this group - process as individual file
                        item_id, item, input_path = group_files[0]
                        logger.info(f"Processing single file from group '{parent_key}': {input_path}")

                        item_output_path = self._generate_output_structure(
                            collection_name=collection_name,
                            collection_id=collection_id,
                            item_name=item.name,
                            workflow_name=workflow_name,
                            plan_name=plan_name,
                            base_path=output_base_path
                        )
                        item_output_path.mkdir(parents=True, exist_ok=True)

                        task_id = await self._process_single_file(
                            item_id, input_path, item_output_path, plan_name, workflow_name, collection_id
                        )
                        if task_id:
                            task_ids.append(task_id)
                            item.status = 'processing'
                            await self.library_manager.update_item(item)
                    else:
                        # Multiple files in same parent - process as ONE catalogue
                        group_name = f"{'root' if parent_key == '_root_' else parent_key}"
                        logger.info(f"Processing {len(group_files)} files in '{group_name}' as one catalogue")

                        # Create temporary directory with symlinks
                        temp_dir = Path(tempfile.mkdtemp(prefix=f"fichero_catalogue_{parent_key}_"))
                        logger.info(f"Created temporary directory for catalogue: {temp_dir}")

                        try:
                            # Create symlinks to all files in the group
                            for _, item, input_path in group_files:
                                symlink_path = temp_dir / input_path.name
                                os.symlink(input_path, symlink_path)
                                logger.debug(f"Created symlink: {symlink_path} -> {input_path}")

                            # Generate catalogue name
                            if parent_key == "_root_":
                                catalogue_name = collection_name  # Use collection name for root files
                            else:
                                # Get parent folder name
                                parent_item = await self.library_manager.get_item(parent_key)
                                catalogue_name = parent_item.name if parent_item else f"folder_{parent_key[:8]}"

                            # Generate output path
                            catalogue_output_path = self._generate_output_structure(
                                collection_name=collection_name,
                                collection_id=collection_id,
                                item_name=catalogue_name,
                                workflow_name=workflow_name,
                                plan_name=plan_name,
                                base_path=output_base_path
                            )
                            catalogue_output_path.mkdir(parents=True, exist_ok=True)

                            # Process as a single folder
                            first_item_id = group_files[0][0]
                            task_id_list = await self._process_single_folder(
                                first_item_id, temp_dir, catalogue_output_path,
                                plan_name, workflow_name, collection_id
                            )
                            task_ids.extend(task_id_list)

                            # Update status for all files in group
                            for item_id, item, _ in group_files:
                                item.status = 'processing'
                                # Keep catalogue metadata for cleanup
                                item.metadata['catalogue_temp_dir'] = str(temp_dir)
                                item.metadata['catalogue_group'] = parent_key
                                await self.library_manager.update_item(item)

                            logger.info(f"Submitted catalogue task for {len(group_files)} files in group '{group_name}'")

                        except Exception as e:
                            # Cleanup temp directory if something fails
                            logger.error(f"Failed to create catalogue for group '{group_name}', cleaning up temp dir: {e}")
                            shutil.rmtree(temp_dir, ignore_errors=True)
                            raise

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
                        item_id, input_path, item_output_path, plan_name, workflow_name, collection_id
                    )
                else:
                    # Multiple folders or "Process All" - use auto-detection
                    logger.info(f"Processing folder with auto-detection: {input_path}")
                    submitted_task_ids = await self._process_folder_structure(
                        item_id, input_path, item_output_path, plan_name, workflow_name, collection_id
                    )

                task_ids.extend(submitted_task_ids)

                # Update item status
                item.status = 'processing'
                await self.library_manager.update_item(item)

            except Exception as e:
                logger.error(f"Error processing folder {item_id}: {e}")
                item.status = 'error'
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

            # Update item status
            item.status = 'processing'
            await self.library_manager.update_item(item)

        # If all files are in the same parent directory, process that folder
        # Otherwise, we need to process files from their individual locations
        try:
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
        except Exception as e:
            # Failed to submit tasks - update all items with error
            error_msg = str(e)
            logger.error(f"Failed to submit batch processing task: {error_msg}")
            for item_id, item, input_path in file_items:
                try:
                    item.status = 'error'
                    await self.library_manager.update_item(item)
                except Exception as update_error:
                    logger.error(f"Failed to update item {item_id} with error: {update_error}")
            return []

        # Track this batch task
        self.active_tasks[task_id] = {
            'item_ids': [item_id for item_id, _, _ in file_items],
            'item_map': batch_item_map,
            'type': 'batch',
            'output_path': str(batch_output_path),
            'plan_name': plan_name,
            'workflow': workflow_name,
            'collection_id': collection_id,
            'started_at': datetime.now()
        }

        logger.debug(f"Submitted batch task {task_id} for {len(file_items)} files")
        logger.info(f"   Output path: {batch_output_path}")
        logger.info(f"   Active tasks: {len(self.active_tasks)}")

        # Log TaskMonitor status
        if hasattr(self.director, 'task_monitor') and self.director.task_monitor:
            task_count = len(self.director.task_monitor.tasks)
            logger.info(f"   TaskMonitor tracking {task_count} task(s)")
            if task_id in self.director.task_monitor.tasks:
                logger.debug(f"   Task {task_id[:8]}... registered in TaskMonitor")
            else:
                logger.warning(f"   Task {task_id[:8]}... NOT in TaskMonitor yet")

        return [task_id]

    async def _process_single_file(self, item_id: str, input_path: Path,
                                   output_path: Path, plan_name: str,
                                   workflow_name: str, collection_id: str,
                                   skip_processing: bool = False) -> Optional[str]:
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
            collection_id: Collection ID
            skip_processing: If True, create empty files instead of processing (default: False)

        Returns:
            Task ID or None if submission failed
        """
        logger.info(f"Processing single file: {input_path}")

        # Use shared folder preparation utility to create staging structure
        from fichero.director.utils.folder_preparation import prepare_single_file_staging

        try:
            # Create staging structure using shared helper
            staging_dir, documents_dir = prepare_single_file_staging(input_path, output_path)

            # Submit to Director using the staging folder
            # Use dict format to explicitly separate documents_folder (input) from output_folder (output)
            # Pass actual filename as display_name so Activity Monitor shows it instead of staging folder name
            # IMPORTANT: Pass documents_dir (staging/documents) not staging_dir (staging) because workflows expect files in documents/
            task_id = self.director.processing_coordinator.process_folders(
                folders=[{
                    'output_folder': output_path,
                    'documents_folder': documents_dir
                }],
                plan_name=plan_name,
                workflow_name=workflow_name,
                output_path=output_path,
                document_context={'display_name': input_path.name},  # Show actual filename, not staging folder
                skip_processing=skip_processing
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
                'collection_id': collection_id,
                'started_at': datetime.now()
            }

            logger.debug(f"Submitted single file task {task_id} for {input_path.name}")
            logger.info(f"   Library output path: {output_path}")
            return task_id

        except Exception as e:
            logger.error(f"Failed to process single file {input_path}: {e}")
            raise

    async def _process_single_folder(self, item_id: str, input_path: Path,
                                     output_path: Path, plan_name: str,
                                     workflow_name: str, collection_id: str,
                                     skip_processing: bool = False) -> List[str]:
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
            collection_id: Collection ID
            skip_processing: If True, create empty files instead of processing (default: False)

        Returns:
            List with single task ID
        """
        logger.info(f"Processing single folder (no auto-detection): {input_path}")

        # Library already created the right output path - use it directly
        # For in-place mode: documents_folder = source location, output_folder = library path
        # For copy mode: would need to copy files first (not implemented yet)

        # In-place processing: source files stay where they are
        documents_folder = input_path

        # Create required subdirectories using shared helper
        from fichero.director.utils.folder_preparation import create_output_subdirectories
        create_output_subdirectories(output_path)

        logger.info(f"Library processing - output: {output_path}, documents: {documents_folder}")

        # Process the folder using process_folders with properly formatted dict
        try:
            task_id = self.director.processing_coordinator.process_folders(
                folders=[{
                    'output_folder': output_path,
                    'documents_folder': documents_folder
                }],
                plan_name=plan_name,
                workflow_name=workflow_name,
                output_path=output_path,
                skip_processing=skip_processing
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to submit folder processing task: {error_msg}")
            raise

        # Track this task
        self.active_tasks[task_id] = {
            'item_id': item_id,
            'type': 'folder',
            'input_path': str(input_path),
            'output_path': str(output_path),
            'plan_name': plan_name,
            'workflow': workflow_name,
            'collection_id': collection_id,
            'started_at': datetime.now()
        }

        logger.debug(f"Submitted single folder task {task_id} for {input_path}")
        return [task_id]

    async def _process_folder_structure(self, item_id: str, input_path: Path,
                                       output_path: Path, plan_name: str,
                                       workflow_name: str, collection_id: str,
                                       skip_processing: bool = False) -> List[str]:
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
            collection_id: Collection ID
            skip_processing: If True, create empty files instead of processing (default: False)

        Returns:
            List of task IDs (one per subfolder detected)
        """
        logger.info(f"Processing folder structure with auto-detection: {input_path}")

        # Use Director's auto-detection
        task_ids = self.director.processing_coordinator.process_with_auto_detection(
            input_path=input_path,
            output_path=output_path,
            plan_name=plan_name,
            workflow_name=workflow_name,
            skip_processing=skip_processing
        )

        logger.debug(f"Auto-detection returned {len(task_ids) if task_ids else 0} task IDs: {task_ids}")

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
                    'collection_id': collection_id,
                    'started_at': datetime.now()
                }
                logger.debug(f"Tracked task {task_id} in active_tasks for item {item_id}")
        else:
            logger.warning(f"No task IDs returned from auto-detection for {input_path}")

        return task_ids if task_ids else []

    def _on_task_monitor_update(self, event_type: str, task_info):
        """
        Handle updates from Director's TaskMonitor

        Args:
            event_type: Type of event (task_created, task_updated, task_completed)
            task_info: TaskInfo object from TaskMonitor
        """
        logger.debug(f"Received TaskMonitor event: {event_type} for task {task_info.task_id}")

        task_id = task_info.task_id

        # Only handle our tracked tasks
        if task_id not in self.active_tasks:
            logger.debug(f"Task {task_id} not in active_tasks, ignoring (active: {list(self.active_tasks.keys())})")
            return

        logger.debug(f"Task {task_id} IS in active_tasks, processing event")

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
                logger.debug(f"Task {task_id} already being finalized, skipping duplicate")
                return

            # Remove from active tasks IMMEDIATELY to prevent duplicate finalization
            task_info_copy = self.active_tasks.pop(task_id, None)
            if not task_info_copy:
                logger.warning(f"Task {task_id} not in active_tasks during completion")
                return

            logger.debug(f"Task {task_id} COMPLETED - starting finalization")
            # Schedule finalization in a background thread to avoid event loop conflicts
            # This is safe because _finalize_processing creates its own event loop
            def finalize_in_thread():
                try:
                    logger.debug(f"Finalization thread started for {task_id}")
                    # Call synchronous finalization directly (no event loop needed)
                    # Pass task_info copy since we removed it from active_tasks
                    self._finalize_processing_with_info(task_id, task_info_copy)
                    logger.debug(f"Finalization completed for {task_id}")
                except Exception as e:
                    logger.error(f"Failed to finalize processing for {task_id}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # Run finalization in background thread
            thread = threading.Thread(target=finalize_in_thread, daemon=True)
            thread.start()
            logger.debug(f"Finalization thread launched for {task_id}")

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
            # CRITICAL: Dispatch GUI update to main thread
            # emit_navigation_event triggers GUI updates (NSTableView) which MUST happen on main thread
            # Using call_soon_threadsafe ensures thread safety
            # Progress data is passed in the event, no need to store in metadata
            if hasattr(self.app, 'loop') and self.app.loop:
                self.app.loop.call_soon_threadsafe(
                    emit_navigation_event,
                    'collection_item_updated',
                    {
                        'item_id': item_id,
                        'task_id': task_id,
                        'progress': progress_data.get('progress', 0),
                        'status': progress_data.get('status', 'running')
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
        logger.debug(f"_finalize_processing STARTED for task {task_id}")

        if not task_info:
            logger.warning(f"Cannot finalize task {task_id}: no task_info provided")
            return

        logger.debug(f"Task info retrieved: {task_info}")
        output_path = Path(task_info['output_path'])
        logger.debug(f"Output path: {output_path}")

        try:
            # Get task result from Director
            logger.debug(f"Getting task result from Director")
            result = self.director.get_task_result(task_id)
            logger.debug(f"Task result retrieved: {result}")

            # Parse output folder
            logger.debug(f"Parsing output folder")
            parsed_outputs = self.output_parser.parse_output_folder(output_path)
            logger.debug(f"Output folder parsed")

            # Handle batch vs single item
            if task_info.get('type') == 'batch':
                self._finalize_batch(task_id, task_info, result, parsed_outputs)
            else:
                self._finalize_single_item(task_id, task_info, result, parsed_outputs)

            logger.debug(f"Processing finalized for task {task_id}")

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
                            item.status = 'error'
                            self.library_manager.storage.update_item(item)
                    except Exception as update_error:
                        logger.error(f"Error updating item {item_id} after finalization error: {update_error}")

        # Note: Task was already removed from active_tasks before finalization started

    def _finalize_single_item(self, task_id: str, task_info: Dict, result, parsed_outputs: Dict):
        """Finalize a single item task (synchronous version)"""
        item_id = task_info['item_id']
        output_path = Path(task_info['output_path'])
        workflow_name = task_info.get('workflow', 'unknown')

        # Skip Interactive_* workflows - they're handled by ToolExecutionService
        if workflow_name.startswith('Interactive_'):
            logger.debug(f"Skipping Interactive workflow (handled by ToolExecutionService): {workflow_name}")
            return

        logger.debug(f"Finalizing single item {item_id}")

        # Get item (use storage directly for sync access)
        item = self.library_manager.storage.get_item(item_id)
        if not item:
            logger.error(f"Item {item_id} not found during finalization")
            return

        logger.debug(f"Item retrieved, creating comprehensive ProcessingResult")

        # Build comprehensive artifact tracking metadata
        artifacts_metadata = self._build_artifacts_metadata(output_path, parsed_outputs, task_info, result)

        # Determine overall workflow status from parsed manifests (more accurate than result.success)
        summary = artifacts_metadata.get('summary', {})
        failed_steps = summary.get('failed_steps', 0)
        successful_steps = summary.get('successful_steps', 0)

        if failed_steps > 0:
            workflow_status = 'partial' if successful_steps > 0 else 'failed'
        elif successful_steps > 0:
            workflow_status = 'success'
        else:
            # Fallback to Director's result if no steps parsed
            workflow_status = 'success' if result and result.success else 'failed'

        # Create ProcessingResult record with comprehensive tracking
        processing_result = ProcessingResult(
            item_id=item_id,
            workflow=task_info.get('workflow', 'unknown'),
            status=workflow_status,
            started_at=task_info['started_at'],
            completed_at=datetime.now(),
            output_paths=[str(output_path)],
            logs_path=str(output_path / "logs") if (output_path / "logs").exists() else None,
            metadata=artifacts_metadata,
            processing_time=(datetime.now() - task_info['started_at']).total_seconds()
        )

        # Save processing result (use storage directly for sync access)
        logger.debug(f"Saving ProcessingResult to database")

        try:
            add_success = self.library_manager.storage.add_processing_result(processing_result)
            if add_success:
                logger.debug(f"ProcessingResult saved successfully with ID: {processing_result.id}")

                # Validate that the record was actually saved
                try:
                    saved_result = self.library_manager.storage.get_processing_result(processing_result.id)
                    if saved_result:
                        logger.debug(f"ProcessingResult validation passed: record found in database")
                    else:
                        logger.error(f"ProcessingResult validation failed: record not found in database after save")
                        # Continue processing but log the issue
                except Exception as validation_e:
                    logger.error(f"Failed to validate ProcessingResult in database: {validation_e}")
            else:
                logger.error(f"Failed to save ProcessingResult to database")
                # Continue with processing even if database save failed

        except Exception as save_e:
            logger.error(f"Exception while saving ProcessingResult: {save_e}")
            import traceback
            logger.error(traceback.format_exc())
            # Continue with processing even if database save failed

        # Ingest outputs from manifests into ProcessingOutput records
        logger.debug(f"Ingesting processing outputs for item {item_id}")
        collection_id = task_info.get('collection_id')

        # Fallback: retrieve collection_id from item if missing from task_info
        if not collection_id and item_id:
            try:
                item = self.library_manager.storage.get_item(item_id)
                if item:
                    collection_id = item.collection_id
                    logger.info(f"Retrieved collection_id '{collection_id}' from item {item_id} (missing from task_info)")
                else:
                    logger.error(f"Could not retrieve item {item_id} to get collection_id")
            except Exception as e:
                logger.error(f"Failed to retrieve collection_id from item {item_id}: {e}")

        # Track ingestion success/failure for validation
        ingestion_success = False
        metadata_success = False

        if collection_id:
            logger.info(f"Processing outputs for item {item_id} in collection {collection_id}")

            try:
                self._ingest_processing_outputs(
                    processing_result_id=processing_result.id,
                    collection_id=collection_id,
                    item_id=item_id,
                    output_path=output_path,
                    item_map=None  # Single item processing doesn't use item_map
                )
                ingestion_success = True
                logger.debug(f"Output ingestion completed successfully for item {item_id}")
            except Exception as e:
                logger.error(f"Output ingestion failed for item {item_id}: {e}")
                import traceback
                logger.error(traceback.format_exc())

            # Extract metadata from outputs (transcriptions, catalogues, etc.)
            # Run even if ingestion partially failed to extract from existing outputs
            try:
                logger.debug(f"Extracting metadata from outputs for item {item_id}")
                self._extract_metadata_from_outputs(
                    processing_result_id=processing_result.id,
                    collection_id=collection_id,
                    output_path=output_path
                )
                metadata_success = True
                logger.debug(f"Metadata extraction completed successfully for item {item_id}")
            except Exception as e:
                logger.error(f"Metadata extraction failed for item {item_id}: {e}")
                import traceback
                logger.error(traceback.format_exc())

            # Log final status summary
            if ingestion_success and metadata_success:
                logger.info(f"Full processing finalization completed for item {item_id}")
            elif ingestion_success:
                logger.warning(f"Output ingestion succeeded but metadata extraction failed for item {item_id}")
            elif metadata_success:
                logger.warning(f"Metadata extraction succeeded but output ingestion failed for item {item_id}")
            else:
                logger.error(f"Both output ingestion and metadata extraction failed for item {item_id}")

        else:
            logger.error(f"No collection_id available (neither from task_info nor item {item_id}), skipping output ingestion and metadata extraction")

        # Update item status based on workflow result (use workflow_status from manifest parsing, not result.success)
        # ProcessingResult table is the source of truth for detailed status
        if workflow_status in ['success', 'partial']:
            item.status = 'completed'
        else:
            item.status = 'error'

        logger.debug(f"Updating item status to '{item.status}' and metadata")
        self.library_manager.storage.update_item(item)
        logger.debug(f"Item updated")

        # Final validation and summary statistics
        try:
            logger.info(f"[FINALIZATION] Generating processing summary for item {item_id}")

            # Count ProcessingOutputs created
            output_count = 0
            if collection_id:
                try:
                    outputs = self.library_manager.storage.get_processing_outputs(processing_result.id)
                    output_count = len(outputs) if outputs else 0
                except Exception as e:
                    logger.warning(f"[FINALIZATION] Could not count ProcessingOutputs: {e}")

            # Count ExtractedMetadata created
            metadata_count = 0
            if collection_id:
                try:
                    # Count metadata for this processing result
                    all_metadata = self.library_manager.storage.get_extracted_metadata(
                        collection_id=collection_id,
                        item_id=item_id
                    )
                    # Filter to just this processing session
                    metadata_count = len([m for m in all_metadata if m.processing_output_id and
                                         any(o.id == m.processing_output_id for o in (outputs or []))])
                except Exception as e:
                    logger.warning(f"[FINALIZATION] Could not count ExtractedMetadata: {e}")

            # Log comprehensive summary
            processing_duration = task_info.get('started_at')
            duration_str = "unknown"
            if processing_duration:
                duration = (datetime.now() - processing_duration).total_seconds()
                duration_str = f"{duration:.1f}s"

            logger.info(f"[FINALIZATION] Processing completed for item {item_id}")
            logger.info(f"[FINALIZATION] ├── Item status: {item.status}")
            logger.info(f"[FINALIZATION] ├── Workflow status: {workflow_status}")
            logger.info(f"[FINALIZATION] ├── Processing duration: {duration_str}")
            logger.info(f"[FINALIZATION] ├── ProcessingOutputs created: {output_count}")
            logger.info(f"[FINALIZATION] ├── ExtractedMetadata created: {metadata_count}")
            logger.info(f"[FINALIZATION] ├── Output ingestion: {'✓' if ingestion_success else '✗'}")
            logger.info(f"[FINALIZATION] └── Metadata extraction: {'✓' if metadata_success else '✗'}")

            # Alert if expected data is missing
            if item.status == 'completed' and output_count == 0:
                logger.error(f"[FINALIZATION] ALERT: Item marked as completed but no ProcessingOutputs found")
            if item.status == 'completed' and metadata_count == 0 and output_count > 0:
                logger.warning(f"[FINALIZATION] ALERT: ProcessingOutputs exist but no metadata extracted")

        except Exception as summary_e:
            logger.error(f"[FINALIZATION] Failed to generate processing summary: {summary_e}")

        # Clean up staging directory if this was a single file task
        # Staging dir is inside library, so cleanup is safe
        staging_dir = task_info.get('staging_dir')
        if staging_dir:
            try:
                import shutil
                staging_path = Path(staging_dir)
                if staging_path.exists():
                    shutil.rmtree(staging_path)
                    logger.debug(f"Cleaned up staging directory: {staging_dir}")
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
            logger.debug(f"Completion event dispatched to main thread")
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
        logger.debug("Building comprehensive artifacts metadata")

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

        # Dynamically discover all manifests in assets directory
        # This works with ANY tool, ANY plan, ANY workflow - no hardcoding needed!
        assets_dir = output_path / "assets"
        if assets_dir.exists():
            # Recursively find all *_manifest.jsonl files
            for manifest_file in assets_dir.rglob("*_manifest.jsonl"):
                # Extract step name from filename
                # Examples: "enhance_manifest.jsonl" → "enhance"
                #           "crop_manifest.jsonl" → "crop"
                #           "documents_manifest.jsonl" → "build_documents_manifest"
                manifest_name = manifest_file.stem  # e.g., "enhance_manifest"
                step_name = manifest_name.replace('_manifest', '')  # e.g., "enhance"

                # Special case: documents_manifest → build_documents_manifest
                if step_name == 'documents':
                    step_name = 'build_documents_manifest'

                # Add to manifests dict
                metadata['manifests'][step_name] = str(manifest_file)

                # Parse manifest to extract step details
                step_data = self._parse_manifest_for_step(
                    step_name, manifest_file, output_path
                )
                if step_data:
                    metadata['steps'].append(step_data)
                    logger.debug(f"📋 Found manifest for step '{step_name}': {manifest_file.name}")

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

        logger.debug(f"Built metadata: {metadata['summary']['total_steps']} steps tracked")
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
                        # A manifest entry is successful if:
                        # 1. It has explicit success=True, OR
                        # 2. It has outputs and no error field (implicit success)
                        # 3. It has error field = failed
                        has_error = 'error' in entry and entry['error']
                        has_outputs = 'outputs' in entry and entry['outputs']
                        explicit_success = entry.get('success', False)

                        if has_error:
                            step_data['failed_files'] += 1
                            step_data['errors'].append({
                                'file': entry.get('source', 'unknown'),
                                'error': entry['error']
                            })
                        elif explicit_success or has_outputs:
                            if entry.get('skipped'):
                                step_data['skipped_files'] += 1
                            else:
                                step_data['successful_files'] += 1
                        else:
                            # No outputs, no error, no explicit success = failed
                            step_data['failed_files'] += 1

                        # Track outputs
                        if has_outputs:
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

        logger.debug(f"Finalizing batch with {len(item_ids)} items")

        # Get all file outputs from the batch
        all_file_outputs = self.output_parser.get_all_file_outputs(output_path)

        # IMPORTANT: Process outputs ONCE for the entire batch with proper item_map
        # This ensures transcriptions go to individual files, catalogs to collection
        collection_id = task_info.get('collection_id')
        if collection_id:
            logger.info(f"Processing outputs for batch with {len(item_ids)} items using item_map")

            # Create a single ProcessingResult for the batch operation
            batch_processing_result = ProcessingResult(
                item_id=None,  # Batch-level, not tied to a specific item
                workflow=task_info.get('workflow', 'unknown'),
                status='success' if result and result.success else 'failed',
                started_at=task_info['started_at'],
                completed_at=datetime.now(),
                output_paths=[str(output_path)],
                logs_path=str(output_path / "logs") if (output_path / "logs").exists() else None,
                metadata={
                    'task_id': task_id,
                    'batch_task': True,
                    'item_count': len(item_ids),
                    'item_map': item_map
                },
                processing_time=(datetime.now() - task_info['started_at']).total_seconds()
            )

            # Save batch processing result
            self.library_manager.storage.add_processing_result(batch_processing_result)
            logger.debug(f"Saved batch ProcessingResult with ID: {batch_processing_result.id}")

            try:
                # Ingest ALL outputs ONCE with item_map for proper routing
                self._ingest_processing_outputs(
                    processing_result_id=batch_processing_result.id,
                    collection_id=collection_id,
                    item_id=None,  # Will be resolved per output using item_map
                    output_path=output_path,
                    item_map=item_map
                )
                logger.debug("Batch output ingestion completed successfully")

                # Extract metadata from outputs (transcriptions, catalogues, etc.)
                self._extract_metadata_from_outputs(
                    processing_result_id=batch_processing_result.id,
                    collection_id=collection_id,
                    output_path=output_path
                )
                logger.debug("Batch metadata extraction completed successfully")
            except Exception as e:
                logger.error(f"Batch output processing failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.warning("No collection_id in task_info, skipping batch output processing")

        # Now update individual item statuses
        for item_id in item_ids:
            # Get item (use storage directly for sync access)
            item = self.library_manager.storage.get_item(item_id)
            if not item:
                logger.warning(f"Item {item_id} not found during batch finalization")
                continue

            # Update item status based on batch result
            # For batch tasks, use result.success since we don't parse per-item manifests
            # ProcessingResult table is the source of truth for detailed status
            batch_status = 'success' if result and result.success else 'failed'
            if batch_status == 'success':
                item.status = 'completed'
            else:
                item.status = 'error'

            # Update in storage (use storage directly for sync access)
            self.library_manager.storage.update_item(item)
            logger.debug(f"Updated batch item {item_id} status to '{item.status}'")

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

        logger.debug(f"Batch finalization complete for {len(item_ids)} items")

    def _get_expected_outputs_for_plan(self, plan_name: str, workflow_name: str) -> Dict[str, List[str]]:
        """
        Return expected output types for a plan/workflow combination

        Args:
            plan_name: Name of the processing plan
            workflow_name: Name of the workflow within the plan

        Returns:
            Dict mapping step names to expected output types
        """
        # Plan-based output expectations - based on actual plan configurations
        plan_expectations = {
            # "Transcribir y Catalogar" plan (Default.yml)
            "Transcribir y Catalogar": {
                "Catalogue": {
                    "build_documents_manifest": ["json_data"],
                    "prepare_images": ["prepared_image"],
                    "transcribe_qwen_max_direct": ["transcription"],
                    "catalogue_folder": ["catalogue", "json_data"],
                    "convert_to_word": ["word_doc"],
                    "catalogue_to_word": ["word_doc"]
                }
            },
            # "Default (English)" plan
            "Default (English)": {
                "Catalogue": {
                    "build_documents_manifest": ["json_data"],
                    "prepare_images": ["prepared_image"],
                    "transcribe_qwen_max_direct": ["transcription"],
                    "catalogue_folder": ["catalogue", "json_data"],
                    "convert_to_word": ["word_doc"],
                    "catalogue_to_word": ["word_doc"]
                }
            },
            # "Prepare Images" plan
            "Prepare Images": {
                "PrepareTest": {
                    "build_documents_manifest": ["json_data"],
                    "prepare_images": ["prepared_image"]
                }
            },
            # "Transcribe" plan
            "Transcribe": {
                "TranscribeTest": {
                    "build_documents_manifest": ["json_data"],
                    "transcribe": ["transcription"]
                }
            }
        }

        # Get plan-specific expectations
        plan_config = plan_expectations.get(plan_name, {})
        workflow_config = plan_config.get(workflow_name, {})

        logger.debug(f"[PLAN_EXPECTATIONS] Plan: {plan_name}, Workflow: {workflow_name}")
        logger.debug(f"[PLAN_EXPECTATIONS] Expected outputs: {workflow_config}")

        return workflow_config

    def _detect_processing_intent(self, task_info: Dict, output_path: Path) -> str:
        """
        Detect if this was file, folder, or batch processing based on task info and outputs

        Args:
            task_info: Task information dictionary
            output_path: Path to processing outputs

        Returns:
            Processing type: "single_file", "single_folder", "batch_files", "folder_structure"
        """
        # Check task info for type hints
        task_type = task_info.get('type', 'unknown')

        # For explicitly tracked types, use them
        if task_type == 'file':
            return 'single_file'
        elif task_type == 'folder':
            # Need to distinguish single folder vs folder structure
            # Check if staging dir exists (indicates single file processing)
            if task_info.get('staging_dir'):
                return 'single_file'  # Single file processed through staging
            else:
                return 'single_folder'
        elif task_type == 'batch':
            return 'batch_files'

        # Fallback: analyze output structure to infer processing type
        try:
            # Look for staging directories (indicates single file)
            staging_patterns = ['staging', 'temp']
            if any(pattern in str(output_path) for pattern in staging_patterns):
                return 'single_file'

            # Check workflow manifest for hints
            workflow_manifest = self._read_workflow_manifest(output_path)
            if workflow_manifest:
                # Single file processing typically has fewer input files
                input_count = self._estimate_input_file_count(workflow_manifest)
                if input_count == 1:
                    return 'single_file'
                elif input_count > 10:
                    return 'folder_structure'
                else:
                    return 'batch_files'

            # Default fallback
            return 'single_folder'

        except Exception as e:
            logger.warning(f"[PROCESSING_INTENT] Could not detect processing intent: {e}")
            return 'unknown'

    def _read_workflow_manifest(self, output_path: Path) -> Optional[Dict]:
        """Read workflow manifest if available"""
        try:
            from fichero.director.workflow_manifest import WorkflowManifest
            return WorkflowManifest.read_manifest(output_path)
        except Exception as e:
            logger.debug(f"[WORKFLOW_MANIFEST] Could not read manifest: {e}")
            return None

    def _estimate_input_file_count(self, workflow_manifest: Dict) -> int:
        """Estimate input file count from workflow manifest"""
        try:
            steps = workflow_manifest.get('steps', [])
            for step in steps:
                if step.get('name') == 'build_documents_manifest':
                    manifest_file = step.get('manifest_file')
                    if manifest_file:
                        # Count entries in documents manifest
                        manifest_path = Path(workflow_manifest.get('output_path', '.')) / manifest_file
                        if manifest_path.exists():
                            with open(manifest_path, 'r') as f:
                                return len(f.readlines())
            return 0
        except Exception:
            return 0

    def _validate_outputs_for_processing_type(self, processing_type: str, outputs: List,
                                            plan_name: str, workflow_name: str,
                                            task_info: Dict) -> Dict[str, Any]:
        """
        Validate that outputs match expectations for processing type and plan

        Args:
            processing_type: Detected processing type
            outputs: List of ProcessingOutput objects
            plan_name: Name of the plan used
            workflow_name: Name of the workflow used
            task_info: Task information dictionary

        Returns:
            Dict with comprehensive validation results
        """
        validation_result = {
            'processing_type': processing_type,
            'plan_name': plan_name,
            'workflow_name': workflow_name,
            'expected_outputs': {},
            'actual_outputs': {},
            'missing_outputs': [],
            'unexpected_outputs': [],
            'completeness_score': 0.0,
            'issues': [],
            'recommendations': []
        }

        try:
            # Get expected outputs for this plan/workflow
            expected_by_step = self._get_expected_outputs_for_plan(plan_name, workflow_name)
            validation_result['expected_outputs'] = expected_by_step

            # Group actual outputs by step
            actual_by_step = {}
            for output in outputs:
                step_name = output.step_name
                if step_name not in actual_by_step:
                    actual_by_step[step_name] = []
                actual_by_step[step_name].append(output.output_type)

            validation_result['actual_outputs'] = actual_by_step

            # Validate each step
            total_expected = 0
            total_found = 0

            for step_name, expected_types in expected_by_step.items():
                actual_types = actual_by_step.get(step_name, [])

                total_expected += len(expected_types)

                # Check for missing outputs
                for expected_type in expected_types:
                    if expected_type in actual_types:
                        total_found += 1
                    else:
                        validation_result['missing_outputs'].append(f"{step_name}: {expected_type}")

                # Check for unexpected outputs
                for actual_type in actual_types:
                    if actual_type not in expected_types and actual_type != 'unknown':
                        validation_result['unexpected_outputs'].append(f"{step_name}: {actual_type}")

            # Calculate completeness score
            if total_expected > 0:
                validation_result['completeness_score'] = total_found / total_expected
            else:
                validation_result['completeness_score'] = 1.0 if len(outputs) > 0 else 0.0

            # Processing type specific validation
            if processing_type == 'single_file':
                self._validate_single_file_outputs(validation_result, outputs, task_info)
            elif processing_type == 'single_folder':
                self._validate_single_folder_outputs(validation_result, outputs, task_info)
            elif processing_type == 'batch_files':
                self._validate_batch_file_outputs(validation_result, outputs, task_info)
            elif processing_type == 'folder_structure':
                self._validate_folder_structure_outputs(validation_result, outputs, task_info)

            # Generate issues and recommendations
            if validation_result['completeness_score'] < 0.5:
                validation_result['issues'].append("Low completeness: Many expected outputs are missing")
                validation_result['recommendations'].append("Check step execution logs for errors")

            if validation_result['missing_outputs']:
                validation_result['issues'].append(f"Missing {len(validation_result['missing_outputs'])} expected outputs")

            if validation_result['unexpected_outputs']:
                validation_result['issues'].append(f"Found {len(validation_result['unexpected_outputs'])} unexpected outputs")

            logger.info(f"[OUTPUT_VALIDATION] Completeness: {validation_result['completeness_score']:.2%}")
            logger.info(f"[OUTPUT_VALIDATION] Missing outputs: {len(validation_result['missing_outputs'])}")
            logger.info(f"[OUTPUT_VALIDATION] Unexpected outputs: {len(validation_result['unexpected_outputs'])}")

        except Exception as e:
            logger.error(f"[OUTPUT_VALIDATION] Validation failed: {e}")
            validation_result['issues'].append(f"Validation error: {str(e)}")
            validation_result['completeness_score'] = 0.0

        return validation_result

    def _validate_single_file_outputs(self, validation_result: Dict, outputs: List, task_info: Dict):
        """Validate outputs for single file processing"""
        # Single file should have at least one output per step that ran
        if len(outputs) == 0:
            validation_result['issues'].append("Single file processing produced no outputs")

        # Check for staging cleanup
        staging_dir = task_info.get('staging_dir')
        if staging_dir and Path(staging_dir).exists():
            validation_result['recommendations'].append("Staging directory still exists and should be cleaned up")

    def _validate_single_folder_outputs(self, validation_result: Dict, outputs: List, task_info: Dict):
        """Validate outputs for single folder processing"""
        # Folder processing should produce collection-level outputs (catalogues, summaries)
        has_collection_output = any(output.output_type in ['catalogue', 'word_doc'] for output in outputs)
        if not has_collection_output:
            validation_result['issues'].append("Folder processing should produce collection-level outputs (catalogue, word doc)")

    def _validate_batch_file_outputs(self, validation_result: Dict, outputs: List, task_info: Dict):
        """Validate outputs for batch file processing"""
        # Batch processing should have outputs for multiple files
        item_ids = task_info.get('item_ids', [])
        if len(item_ids) > 1 and len(outputs) < len(item_ids):
            validation_result['issues'].append(f"Batch processing for {len(item_ids)} files but only {len(outputs)} outputs found")

    def _validate_folder_structure_outputs(self, validation_result: Dict, outputs: List, task_info: Dict):
        """Validate outputs for folder structure processing"""
        # Folder structure processing should have comprehensive outputs
        if len(outputs) < 3:  # Expecting at least manifest, prepared images, and one other output
            validation_result['issues'].append("Folder structure processing produced fewer outputs than expected")

    def _resolve_target_item_id(self, source: str, step_name: str, output_type: str,
                                default_item_id: Optional[str],
                                item_map: Optional[Dict[str, str]] = None) -> Optional[str]:
        """
        Resolve the correct target item_id for a processing output.

        Rules:
        1. Collection-level outputs (catalogs, summaries) -> use default_item_id (collection/folder)
        2. File-level outputs (transcriptions) -> lookup source filename in item_map
        3. Fallback to default_item_id if mapping fails

        Args:
            source: Source filename from manifest
            step_name: Processing step name
            output_type: Type of output (transcription, catalogue, etc.)
            default_item_id: Default item_id (collection/folder level)
            item_map: Optional mapping of filename -> item_id

        Returns:
            Resolved item_id for this output
        """
        # Determine if this should be collection-level or file-level
        is_collection_level = self._is_output_collection_level(step_name, output_type)

        if is_collection_level:
            # Collection-level outputs go to default_item_id (collection/folder)
            logger.debug(f"[RESOLVE] Collection-level output: {output_type} -> {default_item_id}")
            return default_item_id

        # File-level outputs: try to resolve to specific file item_id
        if item_map and source:
            # Extract filename from source (handle paths)
            from pathlib import Path
            source_filename = Path(source).name

            # Look up the specific item_id for this source file
            target_item_id = item_map.get(source_filename)
            if target_item_id:
                logger.debug(f"[RESOLVE] File-level output: {source_filename} -> {target_item_id}")
                return target_item_id
            else:
                logger.warning(f"[RESOLVE] Source file '{source_filename}' not found in item_map, using default: {default_item_id}")

        # Fallback to default_item_id
        logger.debug(f"[RESOLVE] Fallback to default: {default_item_id}")
        return default_item_id

    def _is_output_collection_level(self, step_name: str, output_type: str) -> bool:
        """
        Determine if an output should be collection-level vs file-level.

        Collection-level outputs: catalogs, summaries, collection metadata
        File-level outputs: transcriptions, individual file processing results
        """
        step_lower = step_name.lower()
        type_lower = output_type.lower()

        # Collection-level indicators
        collection_step_patterns = [
            "catalogue_folder", "collection_summary", "batch_process",
            "folder_summary", "aggregate", "batch", "collection", "folder"
        ]

        collection_output_types = [
            "catalogue", "collection_catalogue", "folder_catalogue",
            "batch_summary", "collection_summary", "collection_word_doc", "summary_word_doc"
        ]

        # Check step name patterns
        for pattern in collection_step_patterns:
            if pattern in step_lower:
                return True

        # Check output type
        if type_lower in collection_output_types:
            return True

        # Default: file-level (transcriptions, individual processing results)
        return False

    def _ingest_processing_outputs(self, processing_result_id: str, collection_id: str,
                                   item_id: Optional[str], output_path: Path,
                                   item_map: Optional[Dict[str, str]] = None):
        """
        Ingest processing outputs from manifest files into ProcessingOutput records
        with intelligent plan-aware validation and proper item_id routing.

        Scans the output folder for manifest files, parses them, and creates
        ProcessingOutput records tracking each output file. Now includes:
        - Plan-aware validation and processing type detection
        - Proper item_id routing: transcriptions to files (leafs), catalogs to collections (nodes)
        - Source filename to item_id mapping for batch processing

        Args:
            processing_result_id: ID of the ProcessingResult this belongs to
            collection_id: Collection ID
            item_id: Default item ID (used for collection-level outputs or single-item processing)
            output_path: Path to output directory containing manifests
            item_map: Optional mapping of source filename -> item_id for batch processing
        """
        try:
            logger.info(f"[INGEST] Starting intelligent output ingestion from {output_path}")
            logger.debug(f"[INGEST] Parameters: processing_result_id={processing_result_id}, collection_id={collection_id}, item_id={item_id}")
            if item_map:
                logger.debug(f"[INGEST] Item mapping available: {len(item_map)} files -> {list(item_map.keys())}")

            # Validate required parameters
            if not collection_id or collection_id.strip() == "":
                logger.warning(f"[INGEST] Missing or empty collection_id for processing result {processing_result_id} - this may cause metadata association issues")

            import json
            from fichero.director.workflow_manifest import WorkflowManifest

            # Read the master workflow manifest first
            logger.debug(f"[INGEST] Reading workflow manifest from {output_path}")
            workflow_manifest = WorkflowManifest.read_manifest(output_path)

            if not workflow_manifest:
                logger.warning(f"[INGEST] No workflow_manifest.json found in {output_path} - cannot ingest outputs")
                return

            logger.debug(f"[INGEST] Successfully read workflow manifest: {workflow_manifest.keys()}")

            # Extract plan and workflow information
            workflow_info = workflow_manifest.get('workflow', {})
            plan_name = workflow_info.get('plan_name', 'unknown')
            workflow_name = workflow_info.get('workflow_name', 'unknown')

            logger.info(f"[INGEST] Plan: {plan_name}, Workflow: {workflow_name}")

            # Get task info for processing type detection
            task_info = self._get_task_info_from_processing_result(processing_result_id)

            # Detect processing intent
            processing_type = self._detect_processing_intent(task_info, output_path)
            logger.info(f"[INGEST] Detected processing type: {processing_type}")

            # Extract steps from manifest
            steps = workflow_manifest.get('steps', [])
            logger.info(f"[INGEST] Found {len(steps)} steps in workflow manifest")

            outputs_created = 0
            step_order = 0

            # Process each step in order
            for step_idx, step_record in enumerate(steps, 1):
                step_order = step_record.get('order', 0)
                step_name = step_record.get('name', '')
                step_status = step_record.get('status', '')
                manifest_file_rel = step_record.get('manifest_file')

                logger.debug(f"[INGEST] Step {step_idx}/{len(steps)}: {step_name} (order={step_order}, status={step_status})")

                # Skip failed steps
                if step_status != 'success':
                    logger.debug(f"[INGEST] Skipping step {step_name} (status: {step_status})")
                    continue

                # Skip steps without manifests
                if not manifest_file_rel:
                    logger.debug(f"[INGEST] No manifest file for step {step_name}, skipping")
                    continue

                # Get absolute path to tool manifest
                manifest_file = output_path / manifest_file_rel
                logger.debug(f"[INGEST] Looking for tool manifest at: {manifest_file}")

                if not manifest_file.exists():
                    logger.warning(f"[INGEST] Tool manifest not found: {manifest_file}")
                    continue

                logger.debug(f"[INGEST] Reading tool manifest: {manifest_file.name}")

                # Read tool manifest (JSONL format)
                try:
                    logger.debug(f"[INGEST] Opening manifest file: {manifest_file}")
                    with open(manifest_file, 'r', encoding='utf-8') as f:
                        line_count = 0
                        for line_num, line in enumerate(f, 1):
                            line = line.strip()
                            if not line:
                                continue

                            line_count += 1
                            logger.debug(f"[INGEST] Processing manifest line {line_num}")

                            try:
                                record = json.loads(line)
                                logger.debug(f"[INGEST] Parsed JSON record: source={record.get('source', 'N/A')}, outputs={len(record.get('outputs', []))}")

                                # Extract source and outputs
                                source = record.get('source', '')
                                outputs = record.get('outputs', [])

                                if not outputs:
                                    logger.debug(f"[INGEST] No outputs in manifest record line {line_num}")
                                    continue

                                logger.debug(f"[INGEST] Processing {len(outputs)} output files from line {line_num}")

                                # Process each output file
                                for output_idx, output_file in enumerate(outputs, 1):
                                    # Resolve output file path relative to manifest location
                                    # Output files are specified relative to the manifest's directory
                                    output_file_path = manifest_file.parent / output_file
                                    logger.debug(f"[INGEST] Output {output_idx}/{len(outputs)}: {output_file}")
                                    logger.debug(f"[INGEST] Checking path: {output_file_path}")

                                    # WORKAROUND: If file doesn't exist at specified path, check common subdirectories
                                    # This handles cases where the manifest doesn't include the subdirectory
                                    if not output_file_path.exists():
                                        logger.debug(f"[INGEST] Output file not found at manifest path, checking subdirectories...")

                                        # Try common subdirectories
                                        for subdir in ['documents', 'images', 'files']:
                                            alt_path = manifest_file.parent / subdir / output_file
                                            if alt_path.exists():
                                                logger.debug(f"[INGEST] Found file in subdirectory: {subdir}/")
                                                output_file_path = alt_path
                                                break

                                        # If still not found, skip
                                        if not output_file_path.exists():
                                            logger.warning(f"[INGEST] Output file not found: {output_file}")
                                            continue

                                    # Determine output type based on folder, extension, step, and plan context
                                    output_type = self._determine_output_type(output_file_path, step_name, plan_name)
                                    file_format = output_file_path.suffix.lstrip('.')
                                    logger.debug(f"[INGEST] Determined output_type={output_type}, file_format={file_format}")

                                    # Get file metadata
                                    file_size = output_file_path.stat().st_size
                                    file_modified = datetime.fromtimestamp(output_file_path.stat().st_mtime)
                                    logger.debug(f"[INGEST] File metadata: size={file_size} bytes, modified={file_modified}")

                                    # Make path relative to collection folder
                                    try:
                                        # output_path is typically: collection_id/outputs/date/workflow/item
                                        # We want to store path relative to collection folder
                                        rel_path = output_file_path.relative_to(output_path.parent.parent.parent)
                                        output_path_str = str(rel_path)
                                        logger.debug(f"[INGEST] Relative path: {output_path_str}")
                                    except ValueError as e:
                                        # Fallback: use path relative to output_path
                                        logger.warning(f"[INGEST] Could not make path relative to collection folder: {e}")
                                        output_path_str = str(output_file_path.relative_to(output_path))
                                        logger.debug(f"[INGEST] Relative path (fallback): {output_path_str}")

                                    # Determine the correct target item_id for this output
                                    target_item_id = self._resolve_target_item_id(
                                        source=source,
                                        step_name=step_name,
                                        output_type=output_type,
                                        default_item_id=item_id,
                                        item_map=item_map
                                    )
                                    logger.debug(f"[INGEST] Resolved target_item_id: {target_item_id} (source: {source}, output_type: {output_type})")

                                    # Create ProcessingOutput record
                                    processing_output = ProcessingOutput(
                                        processing_result_id=processing_result_id,
                                        collection_id=collection_id,
                                        item_id=target_item_id,
                                        step_name=step_name,
                                        source_file=source if source else None,
                                        output_type=output_type,
                                        output_path=output_path_str,
                                        file_format=file_format,
                                        file_size=file_size,
                                        file_modified=file_modified,
                                        metadata_extracted=False,
                                        is_valid=True
                                    )

                                    # Save to database with validation
                                    try:
                                        success = self.library_manager.storage.add_processing_output(processing_output)
                                        if success:
                                            outputs_created += 1
                                            logger.info(f"[INGEST] Created ProcessingOutput: {output_type} - {output_file}")
                                        else:
                                            logger.error(f"[INGEST] Failed to save ProcessingOutput to database: {output_file}")
                                    except Exception as db_e:
                                        logger.error(f"[INGEST] Database error saving ProcessingOutput {output_file}: {db_e}")
                                        continue

                            except json.JSONDecodeError as e:
                                logger.error(f"[INGEST] Failed to parse JSON in manifest line {line_num}: {e}")
                                logger.error(f"[INGEST] Problematic line content: {line[:100] if len(line) <= 100 else line[:100] + '...'}")
                                continue
                            except Exception as line_e:
                                logger.error(f"[INGEST] Unexpected error processing manifest line {line_num}: {line_e}")
                                import traceback
                                logger.error(traceback.format_exc())
                                continue

                        logger.debug(f"[INGEST] Finished processing manifest file {manifest_file.name}: processed {line_count} lines")

                except FileNotFoundError:
                    logger.error(f"[INGEST] Manifest file not found: {manifest_file}")
                    continue
                except PermissionError:
                    logger.error(f"[INGEST] Permission denied reading manifest file: {manifest_file}")
                    continue
                except Exception as e:
                    logger.error(f"[INGEST] Error reading tool manifest {manifest_file.name}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue

            # Comprehensive validation and summary with intelligent analysis
            logger.info(f"[INGEST] Output ingestion complete: created {outputs_created} ProcessingOutput records from {len(steps)} steps")

            # Validate that ProcessingOutput records were actually created in the database
            try:
                db_outputs = self.library_manager.storage.get_processing_outputs(processing_result_id)
                db_count = len(db_outputs) if db_outputs else 0
                logger.info(f"[INGEST] Database validation: {db_count} ProcessingOutput records found in database")

                if db_count != outputs_created:
                    logger.warning(f"[INGEST] Validation mismatch: created {outputs_created} but database contains {db_count}")

                # Log summary of output types created
                if db_outputs:
                    output_types = {}
                    for output in db_outputs:
                        output_type = output.output_type
                        output_types[output_type] = output_types.get(output_type, 0) + 1

                    logger.info(f"[INGEST] Output types summary: {dict(output_types)}")

                    # INTELLIGENT VALIDATION: Apply plan-aware validation
                    logger.info(f"[INGEST] Applying intelligent output validation...")
                    validation_result = self._validate_outputs_for_processing_type(
                        processing_type=processing_type,
                        outputs=db_outputs,
                        plan_name=plan_name,
                        workflow_name=workflow_name,
                        task_info=task_info
                    )

                    # Log validation results
                    logger.info(f"[INGEST] Validation Results:")
                    logger.info(f"[INGEST] ├── Processing Type: {validation_result['processing_type']}")
                    logger.info(f"[INGEST] ├── Completeness Score: {validation_result['completeness_score']:.1%}")
                    logger.info(f"[INGEST] ├── Missing Outputs: {len(validation_result['missing_outputs'])}")
                    logger.info(f"[INGEST] ├── Unexpected Outputs: {len(validation_result['unexpected_outputs'])}")
                    logger.info(f"[INGEST] └── Issues Found: {len(validation_result['issues'])}")

                    # Log specific issues and recommendations
                    for issue in validation_result['issues']:
                        logger.warning(f"[INGEST] Issue: {issue}")
                    for recommendation in validation_result['recommendations']:
                        logger.info(f"[INGEST] Recommendation: {recommendation}")

                    # Store validation results in processing result metadata for UI access
                    try:
                        processing_result = self.library_manager.storage.get_processing_result(processing_result_id)
                        if processing_result and hasattr(processing_result, 'metadata'):
                            if not processing_result.metadata:
                                processing_result.metadata = {}
                            processing_result.metadata['output_validation'] = validation_result
                            self.library_manager.storage.update_processing_result(processing_result)
                            logger.debug(f"[INGEST] Stored validation results in processing result metadata")
                    except Exception as metadata_e:
                        logger.warning(f"[INGEST] Could not store validation results in metadata: {metadata_e}")

                    # RECOVERY MECHANISM: Handle incomplete or missing outputs
                    if validation_result['completeness_score'] < 1.0:
                        logger.info(f"[RECOVERY] Incomplete processing detected, applying recovery mechanisms...")
                        recovery_result = self._apply_output_recovery(
                            processing_result_id=processing_result_id,
                            collection_id=collection_id,
                            item_id=item_id,
                            output_path=output_path,
                            validation_result=validation_result,
                            plan_name=plan_name,
                            workflow_name=workflow_name
                        )

                        if recovery_result['recovered_outputs'] > 0:
                            logger.info(f"[RECOVERY] Successfully recovered {recovery_result['recovered_outputs']} outputs")

                        if recovery_result['issues']:
                            for issue in recovery_result['issues']:
                                logger.warning(f"[RECOVERY] {issue}")

                else:
                    logger.warning(f"[INGEST] No ProcessingOutput records found in database after ingestion")

                    # FALLBACK MECHANISM: Try to recover from empty ingestion
                    logger.info(f"[FALLBACK] Attempting fallback output discovery...")
                    fallback_result = self._apply_fallback_output_discovery(
                        processing_result_id=processing_result_id,
                        collection_id=collection_id,
                        item_id=item_id,
                        output_path=output_path,
                        plan_name=plan_name,
                        workflow_name=workflow_name
                    )

                    if fallback_result['discovered_outputs'] > 0:
                        logger.info(f"[FALLBACK] Discovered {fallback_result['discovered_outputs']} outputs through fallback method")
                    else:
                        logger.error(f"[FALLBACK] No outputs could be recovered through fallback method")

            except Exception as validation_e:
                logger.error(f"[INGEST] Failed to validate ProcessingOutput records in database: {validation_e}")

        except Exception as e:
            logger.error(f"[INGEST] FATAL: Failed to ingest outputs from {output_path}: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Even on failure, try to provide some diagnostics
            try:
                logger.debug(f"[INGEST] Diagnostic: Checking if output_path exists: {output_path.exists()}")
                if output_path.exists():
                    logger.debug(f"[INGEST] Diagnostic: Directory contents: {list(output_path.iterdir())}")
            except Exception as diag_e:
                logger.debug(f"[INGEST] Diagnostic check failed: {diag_e}")

    def _get_task_info_from_processing_result(self, processing_result_id: str) -> Dict:
        """
        Retrieve task info from processing result metadata for processing type detection

        Args:
            processing_result_id: ID of the ProcessingResult

        Returns:
            Task info dictionary with available metadata
        """
        try:
            processing_result = self.library_manager.storage.get_processing_result(processing_result_id)
            if processing_result and hasattr(processing_result, 'metadata') and processing_result.metadata:
                # Extract task-related metadata
                metadata = processing_result.metadata
                task_info = {
                    'type': metadata.get('task_type', 'unknown'),
                    'staging_dir': metadata.get('staging_dir'),
                    'input_path': metadata.get('input_path'),
                    'item_ids': metadata.get('item_ids'),
                    'batch_task': metadata.get('batch_task', False)
                }

                # Also check for task_id in metadata for cross-reference
                task_id = metadata.get('task_id')
                if task_id and task_id in self.active_tasks:
                    # Merge with active task info if available
                    active_info = self.active_tasks[task_id]
                    task_info.update(active_info)

                logger.debug(f"[TASK_INFO] Retrieved task info from processing result: {task_info}")
                return task_info
            else:
                logger.debug(f"[TASK_INFO] No metadata found in processing result {processing_result_id}")
                return {'type': 'unknown'}
        except Exception as e:
            logger.warning(f"[TASK_INFO] Failed to retrieve task info from processing result: {e}")
            return {'type': 'unknown'}

    def _apply_output_recovery(self, processing_result_id: str, collection_id: str,
                              item_id: Optional[str], output_path: Path,
                              validation_result: Dict, plan_name: str, workflow_name: str) -> Dict[str, Any]:
        """
        Apply recovery mechanisms for incomplete outputs

        Args:
            processing_result_id: ID of the ProcessingResult
            collection_id: Collection ID
            item_id: Item ID (None for batch-level outputs)
            output_path: Path to output directory
            validation_result: Validation results from previous check
            plan_name: Name of the plan used
            workflow_name: Name of the workflow used

        Returns:
            Dict with recovery results
        """
        recovery_result = {
            'recovered_outputs': 0,
            'issues': [],
            'methods_used': []
        }

        try:
            logger.info(f"[RECOVERY] Starting output recovery for {len(validation_result['missing_outputs'])} missing outputs")

            # Method 1: Search for common output patterns in subdirectories
            if validation_result['missing_outputs']:
                found_files = self._search_for_missing_outputs(output_path, validation_result['missing_outputs'])

                for missing_output, found_file in found_files.items():
                    try:
                        # Extract step name and expected type
                        step_name, expected_type = missing_output.split(': ')

                        # Create ProcessingOutput record for recovered file
                        file_size = found_file.stat().st_size
                        file_modified = datetime.fromtimestamp(found_file.stat().st_mtime)
                        file_format = found_file.suffix.lstrip('.')

                        # Make path relative to collection folder
                        try:
                            rel_path = found_file.relative_to(output_path.parent.parent.parent)
                            output_path_str = str(rel_path)
                        except ValueError:
                            output_path_str = str(found_file.relative_to(output_path))

                        processing_output = ProcessingOutput(
                            processing_result_id=processing_result_id,
                            collection_id=collection_id,
                            item_id=item_id,
                            step_name=step_name,
                            source_file=None,
                            output_type=expected_type,
                            output_path=output_path_str,
                            file_format=file_format,
                            file_size=file_size,
                            file_modified=file_modified,
                            metadata_extracted=False,
                            is_valid=True
                        )

                        # Save to database
                        success = self.library_manager.storage.add_processing_output(processing_output)
                        if success:
                            recovery_result['recovered_outputs'] += 1
                            logger.info(f"[RECOVERY] Recovered: {step_name} -> {expected_type} from {found_file.name}")
                        else:
                            recovery_result['issues'].append(f"Failed to save recovered output: {missing_output}")

                    except Exception as e:
                        recovery_result['issues'].append(f"Error recovering {missing_output}: {str(e)}")

                if found_files:
                    recovery_result['methods_used'].append('file_system_search')

            # Method 2: Check for partial manifests that might have been missed
            partial_manifests = self._find_partial_manifests(output_path)
            if partial_manifests:
                recovery_result['methods_used'].append('partial_manifest_recovery')
                # Process partial manifests similar to normal ingestion
                for manifest_file, step_name in partial_manifests:
                    logger.info(f"[RECOVERY] Processing partial manifest: {manifest_file} for step {step_name}")
                    # This would be implemented similar to the main ingestion logic

            # Method 3: Generate placeholder outputs for critical missing files
            critical_steps = ['build_documents_manifest', 'prepare_images']
            missing_critical = [mo for mo in validation_result['missing_outputs']
                              if any(cs in mo for cs in critical_steps)]

            if missing_critical:
                logger.warning(f"[RECOVERY] Missing critical outputs: {missing_critical}")
                recovery_result['issues'].append(f"Critical outputs missing: {missing_critical}")
                # Could implement placeholder generation here

        except Exception as e:
            logger.error(f"[RECOVERY] Recovery process failed: {e}")
            recovery_result['issues'].append(f"Recovery process error: {str(e)}")

        return recovery_result

    def _apply_fallback_output_discovery(self, processing_result_id: str, collection_id: str,
                                        item_id: Optional[str], output_path: Path,
                                        plan_name: str, workflow_name: str) -> Dict[str, Any]:
        """
        Apply fallback mechanisms when no outputs were ingested

        Args:
            processing_result_id: ID of the ProcessingResult
            collection_id: Collection ID
            item_id: Item ID
            output_path: Path to output directory
            plan_name: Name of the plan used
            workflow_name: Name of the workflow used

        Returns:
            Dict with fallback results
        """
        fallback_result = {
            'discovered_outputs': 0,
            'issues': [],
            'methods_used': []
        }

        try:
            logger.info(f"[FALLBACK] Starting fallback output discovery in {output_path}")

            # Method 1: Direct file system scan (no manifests)
            discovered_files = []

            # Common output patterns to look for
            output_patterns = {
                '**/*.txt': 'transcription',
                '**/*.docx': 'word_doc',
                '**/*.json': 'json_data',
                '**/*.jsonl': 'json_data',
                '**/prepared/**/*.jpg': 'prepared_image',
                '**/prepared/**/*.png': 'prepared_image',
                '**/transcriptions/**/*.txt': 'transcription',
                '**/word/**/*.docx': 'word_doc',
                '**/llm_catalogue/**/*.json': 'catalogue'
            }

            for pattern, output_type in output_patterns.items():
                for file_path in output_path.glob(pattern):
                    if file_path.is_file():
                        discovered_files.append((file_path, output_type))

            logger.info(f"[FALLBACK] Discovered {len(discovered_files)} files through direct scan")

            # Create ProcessingOutput records for discovered files
            for file_path, output_type in discovered_files:
                try:
                    # Infer step name from path
                    step_name = self._infer_step_name_from_path(file_path, output_path)

                    file_size = file_path.stat().st_size
                    file_modified = datetime.fromtimestamp(file_path.stat().st_mtime)
                    file_format = file_path.suffix.lstrip('.')

                    # Make path relative
                    try:
                        rel_path = file_path.relative_to(output_path.parent.parent.parent)
                        output_path_str = str(rel_path)
                    except ValueError:
                        output_path_str = str(file_path.relative_to(output_path))

                    processing_output = ProcessingOutput(
                        processing_result_id=processing_result_id,
                        collection_id=collection_id,
                        item_id=item_id,
                        step_name=step_name,
                        source_file=None,
                        output_type=output_type,
                        output_path=output_path_str,
                        file_format=file_format,
                        file_size=file_size,
                        file_modified=file_modified,
                        metadata_extracted=False,
                        is_valid=True
                    )

                    success = self.library_manager.storage.add_processing_output(processing_output)
                    if success:
                        fallback_result['discovered_outputs'] += 1
                        logger.info(f"[FALLBACK] Discovered: {step_name} -> {output_type} from {file_path.name}")

                except Exception as e:
                    fallback_result['issues'].append(f"Error processing discovered file {file_path.name}: {str(e)}")

            if discovered_files:
                fallback_result['methods_used'].append('direct_file_scan')

        except Exception as e:
            logger.error(f"[FALLBACK] Fallback discovery failed: {e}")
            fallback_result['issues'].append(f"Fallback discovery error: {str(e)}")

        return fallback_result

    def _search_for_missing_outputs(self, output_path: Path, missing_outputs: List[str]) -> Dict[str, Path]:
        """Search for missing outputs in common locations"""
        found_files = {}

        for missing_output in missing_outputs:
            try:
                step_name, expected_type = missing_output.split(': ')

                # Search patterns based on output type
                search_patterns = {
                    'transcription': ['**/*transcript*.txt', '**/*transcription*.txt', '**/transcriptions/**/*.txt'],
                    'prepared_image': ['**/prepared/**/*.jpg', '**/prepared/**/*.png', '**/*prepared*.jpg'],
                    'word_doc': ['**/*.docx', '**/word/**/*.docx', '**/*word*.docx'],
                    'catalogue': ['**/catalogue*.json', '**/catalog*.json', '**/llm_catalogue/**/*.json'],
                    'json_data': ['**/*.json', '**/*.jsonl', '**/manifests/**/*.jsonl']
                }

                patterns = search_patterns.get(expected_type, [])
                for pattern in patterns:
                    for file_path in output_path.glob(pattern):
                        if file_path.is_file():
                            # Check if this file contains the step name in its path or content
                            if step_name.lower() in str(file_path).lower():
                                found_files[missing_output] = file_path
                                break
                    if missing_output in found_files:
                        break

            except ValueError:
                continue  # Skip malformed missing_output strings

        return found_files

    def _find_partial_manifests(self, output_path: Path) -> List[tuple]:
        """Find manifest files that might have been missed"""
        partial_manifests = []

        # Look for any .jsonl files that could be manifests
        for jsonl_file in output_path.rglob("*.jsonl"):
            if jsonl_file.is_file():
                # Try to determine step name from filename
                file_name = jsonl_file.stem
                possible_step = file_name.replace('_manifest', '')
                partial_manifests.append((jsonl_file, possible_step))

        return partial_manifests

    def _infer_step_name_from_path(self, file_path: Path, output_path: Path) -> str:
        """Infer step name from file path structure"""
        rel_path = file_path.relative_to(output_path)
        path_parts = rel_path.parts

        # Common step name patterns in paths
        step_patterns = {
            'transcriptions': 'transcribe',
            'prepared': 'prepare_images',
            'word': 'convert_to_word',
            'llm_catalogue': 'catalogue_folder',
            'manifests': 'build_documents_manifest'
        }

        for part in path_parts:
            for pattern, step_name in step_patterns.items():
                if pattern in part.lower():
                    return step_name

        # Fallback: use first directory name
        if len(path_parts) > 1:
            return path_parts[0].replace('_', '').lower()

        return 'unknown'

    def _determine_output_type(self, file_path: Path, step_name: str, plan_name: str = None) -> str:
        """
        Determine output type based on file path, extension, step name, and plan context with confidence scoring

        Args:
            file_path: Path to output file
            step_name: Name of processing step
            plan_name: Name of processing plan for context

        Returns:
            Output type string (e.g., "transcription", "word_doc", "prepared_image")
        """
        # Track confidence scores for different detection methods
        type_scores = {}

        # Method 1: Folder structure analysis (highest confidence)
        parts = [p.lower() for p in file_path.parts]

        folder_patterns = {
            'transcription': ['transcriptions', 'txt', 'text'],
            'prepared_image': ['prepared', 'prepared_images', 'processed_images', 'enhanced'],
            'word_doc': ['word_output', 'docx', 'documents', 'word'],
            'catalogue': ['llm_catalogue', 'catalogue', 'catalog', 'llm_catalog'],
            'json_data': ['json_output', 'data', 'manifests'],  # More specific patterns
            'markdown': ['markdown', 'md']
        }

        for output_type, patterns in folder_patterns.items():
            for pattern in patterns:
                if any(pattern in part for part in parts):
                    type_scores[output_type] = type_scores.get(output_type, 0) + 3
                    logger.debug(f"[OUTPUT_TYPE] Folder match: '{pattern}' -> {output_type} (+3)")

        # Method 2: File extension analysis (medium confidence)
        suffix = file_path.suffix.lower()
        extension_mapping = {
            '.txt': 'transcription',
            '.text': 'transcription',
            '.docx': 'word_doc',
            '.doc': 'word_doc',
            '.json': 'json_data',
            '.jsonl': 'json_data',
            '.jpg': 'prepared_image',
            '.jpeg': 'prepared_image',
            '.png': 'prepared_image',
            '.tif': 'prepared_image',
            '.tiff': 'prepared_image',
            '.md': 'markdown',
            '.markdown': 'markdown'
        }

        if suffix in extension_mapping:
            output_type = extension_mapping[suffix]
            type_scores[output_type] = type_scores.get(output_type, 0) + 2
            logger.debug(f"[OUTPUT_TYPE] Extension match: '{suffix}' -> {output_type} (+2)")

        # Method 3: Step name analysis (medium confidence)
        step_lower = step_name.lower()
        step_patterns = {
            'transcription': ['transcribe', 'transcript'],
            'catalogue': ['catalogue', 'catalog'],
            'prepared_image': ['prepare', 'crop', 'enhance', 'process_image'],
            'word_doc': ['word', 'docx', 'document'],
            'json_data': ['manifest', 'documents_manifest', 'build_documents']
        }

        for output_type, patterns in step_patterns.items():
            for pattern in patterns:
                if pattern in step_lower:
                    type_scores[output_type] = type_scores.get(output_type, 0) + 2
                    logger.debug(f"[OUTPUT_TYPE] Step name match: '{pattern}' -> {output_type} (+2)")

        # Method 4: Plan context analysis (medium-high confidence)
        if plan_name:
            plan_lower = plan_name.lower()

            # Plan-specific output preferences
            if 'transcrib' in plan_lower and suffix in ['.txt', '.text']:
                type_scores['transcription'] = type_scores.get('transcription', 0) + 3
                logger.debug(f"[OUTPUT_TYPE] Plan context: transcription plan with text file (+3)")

            if 'catalogue' in plan_lower or 'catalog' in plan_lower:
                if 'catalogue' in str(file_path).lower():
                    type_scores['catalogue'] = type_scores.get('catalogue', 0) + 3
                    logger.debug(f"[OUTPUT_TYPE] Plan context: catalogue plan with catalogue output (+3)")

            if 'prepare' in plan_lower and suffix in ['.jpg', '.jpeg', '.png', '.tiff']:
                type_scores['prepared_image'] = type_scores.get('prepared_image', 0) + 3
                logger.debug(f"[OUTPUT_TYPE] Plan context: prepare plan with image output (+3)")

        # Method 5: Specific step-output mapping (highest confidence for known mappings)
        step_output_map = {
            'build_documents_manifest': 'json_data',
            'prepare_images': 'prepared_image',
            'transcribe_qwen_max_direct': 'transcription',
            'transcribe_qwen_max': 'transcription',
            'transcribe': 'transcription',
            'catalogue_folder': 'catalogue',
            'convert_to_word': 'word_doc',
            'catalogue_to_word': 'word_doc',
            'json_to_word': 'word_doc',
            'llm_process': 'catalogue'
        }

        if step_name in step_output_map:
            expected_type = step_output_map[step_name]
            type_scores[expected_type] = type_scores.get(expected_type, 0) + 5
            logger.debug(f"[OUTPUT_TYPE] Step mapping: {step_name} -> {expected_type} (+5)")

        # Method 6: Filename pattern analysis (high confidence for specific patterns)
        filename_lower = file_path.name.lower()
        if '_catalogue.json' in filename_lower or '_catalog.json' in filename_lower:
            type_scores['catalogue'] = type_scores.get('catalogue', 0) + 4
            logger.debug(f"[OUTPUT_TYPE] Catalogue filename pattern detected (+4)")
        elif 'catalogue' in filename_lower and suffix == '.json':
            type_scores['catalogue'] = type_scores.get('catalogue', 0) + 3
            logger.debug(f"[OUTPUT_TYPE] Catalogue filename detected (+3)")

        # Method 7: Content-based detection for text files (when available)
        if suffix in ['.txt', '.text', '.md', '.json']:
            try:
                # Quick content peek for additional confidence
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content_sample = f.read(1000).lower()  # First 1KB

                # JSON structure detection
                if content_sample.strip().startswith('{') and 'metadata' in content_sample:
                    type_scores['json_data'] = type_scores.get('json_data', 0) + 1
                    logger.debug(f"[OUTPUT_TYPE] JSON content detected (+1)")

                # Catalogue patterns
                if any(keyword in content_sample for keyword in ['título:', 'title:', 'author:', 'date:', 'summary:']):
                    type_scores['catalogue'] = type_scores.get('catalogue', 0) + 2
                    logger.debug(f"[OUTPUT_TYPE] Catalogue content detected (+2)")

                # Transcription patterns
                if len(content_sample) > 100 and content_sample.count(' ') > 20:  # Likely transcribed text
                    type_scores['transcription'] = type_scores.get('transcription', 0) + 1
                    logger.debug(f"[OUTPUT_TYPE] Transcription content detected (+1)")

            except Exception as e:
                logger.debug(f"[OUTPUT_TYPE] Content analysis failed for {file_path}: {e}")

        # Determine best match
        if type_scores:
            best_type = max(type_scores.items(), key=lambda x: x[1])
            best_score = best_type[1]
            result_type = best_type[0]

            # Log confidence level
            confidence = "high" if best_score >= 3 else "medium" if best_score >= 2 else "low"
            logger.debug(f"[OUTPUT_TYPE] Decision: {result_type} (confidence: {confidence}, score: {best_score})")
            logger.debug(f"[OUTPUT_TYPE] All scores: {type_scores}")

            return result_type

        # Fallback to unknown with diagnostic info
        logger.warning(f"[OUTPUT_TYPE] Unable to determine type for {file_path} (step: {step_name})")
        logger.debug(f"[OUTPUT_TYPE] Parts: {parts}")
        logger.debug(f"[OUTPUT_TYPE] Extension: {suffix}")

        return 'unknown'

    def _extract_metadata_from_outputs(self, processing_result_id: str, collection_id: str,
                                       output_path: Path):
        """
        Extract searchable metadata from processing outputs using universal extractors

        Uses the UniversalExtractor to automatically extract and index metadata from
        all output types (transcriptions, catalogues, images, etc.) with proper
        source labels and versioning.

        Args:
            processing_result_id: ID of the ProcessingResult
            collection_id: Collection ID
            output_path: Path to output directory
        """
        try:
            logger.info(f"[METADATA] Starting metadata extraction for processing result {processing_result_id}")
            logger.debug(f"[METADATA] Parameters: collection_id={collection_id}, output_path={output_path}")

            # Read workflow manifest for scope information
            workflow_manifest = self._read_workflow_manifest(output_path)
            if workflow_manifest:
                logger.debug(f"[METADATA] Loaded workflow manifest with {len(workflow_manifest.get('steps', []))} steps")
            else:
                logger.debug(f"[METADATA] No workflow manifest found, using heuristic scope detection")

            # Get all ProcessingOutputs for this result
            outputs = self.library_manager.storage.get_processing_outputs(processing_result_id)
            logger.info(f"[METADATA] Found {len(outputs)} ProcessingOutput records to extract metadata from")

            if not outputs:
                logger.warning(f"[METADATA] No ProcessingOutput records found for result {processing_result_id}")
                return

            # Track detailed statistics
            metadata_created = 0
            outputs_processed = 0
            outputs_skipped = 0
            outputs_failed = 0
            outputs_already_processed = 0

            for output_idx, output in enumerate(outputs, 1):
                try:
                    logger.debug(f"[METADATA] Processing output {output_idx}/{len(outputs)}: {output.output_type} - {output.output_path}")

                    # Skip if metadata already extracted
                    if output.metadata_extracted:
                        logger.debug(f"[METADATA] Metadata already extracted for output {output.id}, skipping")
                        outputs_already_processed += 1
                        continue

                    # Reconstruct full path (output_path is relative to collection folder)
                    full_output_path = output_path.parent.parent.parent / output.output_path
                    logger.debug(f"[METADATA] Resolving full path: {full_output_path}")

                    if not full_output_path.exists():
                        logger.warning(f"[METADATA] Output file not found, skipping: {full_output_path}")
                        outputs_skipped += 1
                        continue

                    # Validate file accessibility
                    try:
                        file_stats = full_output_path.stat()
                        logger.debug(f"[METADATA] File validation passed: size={file_stats.st_size} bytes")
                    except Exception as file_e:
                        logger.warning(f"[METADATA] File not accessible, skipping: {full_output_path} - {file_e}")
                        outputs_skipped += 1
                        continue

                    # Use universal extractor to extract metadata
                    logger.debug(f"[METADATA] Calling metadata extractor for {output.output_type}")
                    extracted_metadata = self.metadata_extractor.extract_from_output(
                        output_path=full_output_path,
                        output_type=output.output_type,
                        collection_id=collection_id,
                        item_id=output.item_id,  # Pass actual item_id, could be None for collection-level
                        processing_output_id=output.id,
                        step_name=output.step_name,
                        workflow_manifest=workflow_manifest
                    )

                    if extracted_metadata and len(extracted_metadata) > 0:
                        metadata_created += len(extracted_metadata)
                        logger.info(f"[METADATA] Extracted {len(extracted_metadata)} metadata records from {output.output_type}: {output.source_file or output.output_path}")

                        # Update output record to mark metadata as extracted
                        output.metadata_extracted = True
                        update_success = self.library_manager.storage.update_processing_output(output)
                        if not update_success:
                            logger.warning(f"[METADATA] Failed to update metadata_extracted flag for output {output.id}")

                        outputs_processed += 1
                    else:
                        logger.warning(f"[METADATA] No metadata extracted from {output.output_type}: {output.output_path}")
                        # Still mark as processed to avoid repeated attempts
                        output.metadata_extracted = True
                        self.library_manager.storage.update_processing_output(output)
                        outputs_processed += 1

                except Exception as e:
                    logger.error(f"[METADATA] Failed to extract metadata from output {output.output_path}: {e}")
                    import traceback
                    logger.error(f"[METADATA] Traceback: {traceback.format_exc()}")
                    outputs_failed += 1
                    continue

            # Log comprehensive summary
            logger.info(f"[METADATA] Metadata extraction completed for result {processing_result_id}")
            logger.info(f"[METADATA] Summary: processed={outputs_processed}, failed={outputs_failed}, skipped={outputs_skipped}, already_processed={outputs_already_processed}")
            logger.info(f"[METADATA] Total metadata records created: {metadata_created}")

            # Validate that we processed the expected number of outputs
            total_handled = outputs_processed + outputs_failed + outputs_skipped + outputs_already_processed
            if total_handled != len(outputs):
                logger.error(f"[METADATA] Validation error: handled {total_handled} outputs but expected {len(outputs)}")

            # Log warning if no metadata was created
            if metadata_created == 0 and outputs_processed > 0:
                logger.warning(f"[METADATA] No metadata records created despite processing {outputs_processed} outputs")

        except Exception as e:
            logger.error(f"[METADATA] FATAL: Failed to extract metadata for result {processing_result_id}: {e}")
            import traceback
            logger.error(f"[METADATA] Fatal traceback: {traceback.format_exc()}")

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
                        item.status = 'error'  # Cancelled tasks are marked as error
                        await self.library_manager.update_item(item)

                    # Remove from active tasks
                    self.active_tasks.pop(task_id, None)

                return success

        return False
