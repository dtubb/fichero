"""
Shared folder processing utilities for CLI and GUI

Centralizes common logic for folder detection, preparation, and processing
to avoid duplication between CLI and GUI interfaces.
"""

from pathlib import Path
from typing import List, Dict, Optional, Callable, TYPE_CHECKING
import time
import logging

from fichero.utils.folder_preparation import prepare_folder

if TYPE_CHECKING:
    from fichero.director import FicheroDirector

logger = logging.getLogger(__name__)


class FolderProcessor:
    """
    Shared folder processing logic for CLI and GUI.
    
    Handles:
    - Automatic subfolder detection
    - Folder preparation with output structure
    - Task submission to director
    - Progress tracking coordination
    """
    
    def __init__(self, director: 'FicheroDirector', progress_callback: Optional[Callable] = None):
        self.director = director
        self.progress_callback = progress_callback
        self.task_info = {}  # task_id -> folder info
        
        if progress_callback:
            director.register_progress_callback(self._handle_progress_update)
    
    def detect_and_prepare_folders(self, input_folders: List[Path], output: Path) -> List[Dict[str, Path]]:
        """
        Detect top-level subfolders with images and prepare them for processing.

        Each top-level subfolder becomes a separate processing task that will
        recursively process all images in its entire folder tree.

        Returns list of dicts with 'output_folder' and 'documents_folder' for each prepared folder.
        """
        # Get processing mode from settings
        processing_mode = "in_place"  # default
        if hasattr(self.director, 'settings_manager'):
            try:
                settings = self.director.settings_manager.load_settings()
                processing_mode = settings.get('preferences', {}).get('processing_mode', 'in_place')
                logger.info(f"Using processing mode from settings: {processing_mode}")
            except Exception as e:
                logger.warning(f"Could not load processing mode from settings, using default: {e}")

        prepared_folders = []

        for input_folder in input_folders:
            logger.info(f"Analyzing input folder: {input_folder}")

            # Find top-level subfolders that contain images (recursively)
            image_folders = self._find_folders_with_images(input_folder)

            if image_folders:
                logger.info(f"Found {len(image_folders)} top-level subfolders with images - each will be processed as a separate task")

                for image_folder in image_folders:
                    logger.info(f"Preparing top-level folder: {image_folder.name} (will process entire folder tree recursively)")
                    output_folder, documents_folder = prepare_folder(image_folder, output, processing_mode)
                    prepared_folders.append({
                        'output_folder': output_folder,
                        'documents_folder': documents_folder
                    })

            else:
                # FALLBACK: No subfolders with images found, check if root folder itself has images
                if self._folder_has_images_direct(input_folder):
                    logger.info(f"No subfolders found, but root folder contains images - treating input folder as single task to process")
                    output_folder, documents_folder = prepare_folder(input_folder, output, processing_mode)
                    prepared_folders.append({
                        'output_folder': output_folder,
                        'documents_folder': documents_folder
                    })
                else:
                    # No images found anywhere
                    logger.warning(f"No supported image files found in: {input_folder}")

        logger.info(f"Prepared {len(prepared_folders)} folder(s) for parallel processing")
        return prepared_folders
    
    def _find_folders_with_images(self, root_folder: Path) -> List[Path]:
        """
        Find top-level subfolders that contain images (recursively).
        
        Only immediate children of root_folder become separate tasks,
        but each task processes its entire subfolder tree recursively.
        
        Args:
            root_folder: Root folder to search in
            
        Returns:
            List of top-level folder paths that contain images anywhere in their tree
        """
        image_extensions = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.heic', '.jxl'}
        folders_with_images = []
        
        def _folder_has_images_recursive(folder: Path) -> bool:
            """Recursively check if folder contains any images"""
            try:
                for item in folder.iterdir():
                    if item.name.startswith('.'):
                        continue  # Skip hidden files/folders
                        
                    if item.is_file():
                        # Check if it's a supported image file
                        if item.suffix.lower() in image_extensions:
                            return True
                    elif item.is_dir():
                        # Recursively check subdirectories
                        if _folder_has_images_recursive(item):
                            return True
                    
            except (PermissionError, OSError) as e:
                logger.warning(f"Cannot access folder {folder}: {e}")
        
            return False
        
        def _count_images_recursive(folder: Path) -> int:
            """Recursively count all images in folder tree"""
            count = 0
            try:
                for item in folder.iterdir():
                    if item.name.startswith('.'):
                        continue  # Skip hidden files/folders
                        
                    if item.is_file():
                        # Check if it's a supported image file
                        if item.suffix.lower() in image_extensions:
                            count += 1
                    elif item.is_dir():
                        # Recursively count in subdirectories
                        count += _count_images_recursive(item)
                    
            except (PermissionError, OSError) as e:
                logger.warning(f"Cannot access folder {folder}: {e}")
        
            return count
        
        # Only look at immediate children of root_folder
        try:
            for item in root_folder.iterdir():
                if item.name.startswith('.'):
                    continue  # Skip hidden files/folders
                    
                if item.is_dir():
                    # Check if this top-level folder has images anywhere in its tree
                    if _folder_has_images_recursive(item):
                        folders_with_images.append(item)
                        logger.debug(f"Found top-level folder with images: {item}")
                        
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot access root folder {root_folder}: {e}")
        
        # Get sorting preference from settings
        try:
            from fichero.config.core.settings import get_app_settings
            app_settings = get_app_settings(self.director.app)
            if app_settings:
                folder_order = app_settings.get_setting('preferences.folder_processing_order', 'alphabetical')
                logger.info(f"🔧 DEBUG: Loaded folder order setting: '{folder_order}' from app settings")
            else:
                folder_order = 'alphabetical'  # Default fallback
                logger.warning(f"🔧 DEBUG: No app settings found, using default: '{folder_order}'")
        except Exception as e:
            logger.warning(f"Could not load folder ordering preference: {e}")
            folder_order = 'alphabetical'  # Default fallback
            logger.warning(f"🔧 DEBUG: Exception occurred, using default: '{folder_order}'")
        
        # Log original order before sorting
        original_order = [f.name for f in folders_with_images]
        logger.info(f"🔧 DEBUG: Original folder order: {original_order}")
            
        # Sort folders according to preference
        if folder_order == 'reverse_alphabetical':
            folders_with_images.sort(key=lambda x: str(x).lower(), reverse=True)
            logger.info(f"✅ Sorting {len(folders_with_images)} folders in reverse alphabetical order (Z-A)")
        elif folder_order == 'least_images_first':
            # Count images and sort by count (ascending)
            folder_counts = [(folder, _count_images_recursive(folder)) for folder in folders_with_images]
            logger.info(f"🔧 DEBUG: Folder image counts before sorting: {[(f.name, c) for f, c in folder_counts]}")
            folder_counts.sort(key=lambda x: x[1])  # Sort by count ascending (least first)
            logger.info(f"🔧 DEBUG: Folder image counts after sorting (ascending): {[(f.name, c) for f, c in folder_counts]}")
            folders_with_images = [folder for folder, count in folder_counts]
            logger.info(f"✅ Sorted {len(folders_with_images)} folders by image count (LEAST FIRST): {[f.name for f in folders_with_images]}")
        elif folder_order == 'most_images_first':
            # Count images and sort by count (descending)
            folder_counts = [(folder, _count_images_recursive(folder)) for folder in folders_with_images]
            logger.info(f"🔧 DEBUG: Folder image counts before sorting: {[(f.name, c) for f, c in folder_counts]}")
            folder_counts.sort(key=lambda x: x[1], reverse=True)  # Sort by count descending (most first)
            logger.info(f"🔧 DEBUG: Folder image counts after sorting (descending): {[(f.name, c) for f, c in folder_counts]}")
            folders_with_images = [folder for folder, count in folder_counts]
            logger.info(f"✅ Sorted {len(folders_with_images)} folders by image count (MOST FIRST): {[f.name for f in folders_with_images]}")
        else:  # 'alphabetical' or unknown
            folders_with_images.sort(key=lambda x: str(x).lower())
            logger.info(f"✅ Sorted {len(folders_with_images)} folders in alphabetical order (A-Z)")
        
        # Log final processing order
        final_order = [f.name for f in folders_with_images]
        logger.info(f"🎯 FINAL PROCESSING ORDER: {final_order}")
        
        return folders_with_images
    
    def _folder_has_images_direct(self, folder: Path) -> bool:
        """
        Check if folder contains images directly (not recursively).
        Used for fallback when no subfolders with images are found.
        
        Args:
            folder: Folder to check
            
        Returns:
            True if folder contains image files directly
        """
        image_extensions = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.heic', '.jxl'}
        
        try:
            for item in folder.iterdir():
                if item.name.startswith('.'):
                    continue  # Skip hidden files
                    
                if item.is_file():
                    # Check if it's a supported image file
                    if item.suffix.lower() in image_extensions:
                        return True
                        
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot access folder {folder}: {e}")
            
        return False
    
    def submit_processing_tasks(self, prepared_folders: List[Dict[str, Path]], plan_name: str,
                              workflow_name: str = "default",
                              document_context: Dict = None,
                              skip_processing: bool = False) -> List[str]:
        """
        Submit processing tasks for prepared folders.
        Each folder becomes a separate task for parallel processing.

        Args:
            prepared_folders: List of dicts with 'output_folder' and 'documents_folder' keys
            plan_name: Name of the processing plan
            workflow_name: Name of workflow within the plan
            document_context: Additional document metadata
            skip_processing: If True, create empty files instead of processing (default: False)

        Returns list of task IDs.
        """
        task_ids = []

        for folder_info in prepared_folders:
            output_folder = folder_info['output_folder']
            documents_folder = folder_info['documents_folder']

            # Submit each folder as a separate task
            task_id = self.director.process_folders(
                folders=[{'output_folder': output_folder, 'documents_folder': documents_folder}],
                plan_name=plan_name,
                workflow_name=workflow_name,
                document_context=document_context or {},
                skip_processing=skip_processing
            )
            task_ids.append(task_id)

            # Track task info for progress updates
            self.task_info[task_id] = {
                'folder_name': output_folder.name,
                'folder_path': output_folder,
                'documents_path': documents_folder,
                'status': 'pending',
                'progress': 0,
                'start_time': time.time()
            }

            logger.info(f"Submitted task {task_id} for folder: {output_folder.name} (documents: {documents_folder})")

        logger.info(f"Submitted {len(task_ids)} tasks for parallel processing")
        return task_ids
    
    def _handle_progress_update(self, task_id: str, progress_data: Dict):
        """Handle progress updates from director and forward to callback"""
        if task_id in self.task_info:
            # Update our tracking
            folder_info = self.task_info[task_id]
            folder_info.update({
                'status': progress_data.get('status', 'running'),
                'progress': progress_data.get('progress', 0),
                'current_step': progress_data.get('current_step', ''),
                'last_update': time.time()
            })
            
            # Add folder context to progress data
            enhanced_progress = {
                **progress_data,
                'folder_name': folder_info['folder_name'],
                'folder_path': str(folder_info['folder_path']),
                'task_start_time': folder_info['start_time']
            }
            
            # Forward to external callback if provided
            if self.progress_callback:
                self.progress_callback(task_id, enhanced_progress)
    
    def get_task_statuses(self, task_ids: List[str]) -> Dict[str, str]:
        """Get current status of all tasks"""
        statuses = {}
        for task_id in task_ids:
            status = self.director.get_task_status(task_id)
            statuses[task_id] = status.value if status else 'unknown'
        return statuses
    
    def all_tasks_completed(self, task_ids: List[str]) -> bool:
        """Check if all tasks are completed (success, failed, or cancelled)"""
        statuses = self.get_task_statuses(task_ids)
        return all(s in ['success', 'failed', 'cancelled'] for s in statuses.values())
    
    def get_completion_summary(self, task_ids: List[str]) -> Dict:
        """Get summary of completed tasks"""
        statuses = self.get_task_statuses(task_ids)
        results = {}
        
        successful = []
        failed = []
        
        for task_id in task_ids:
            status = statuses.get(task_id, 'unknown')
            folder_name = self.task_info.get(task_id, {}).get('folder_name', 'Unknown')
            
            if status == 'success':
                successful.append(folder_name)
            elif status == 'failed':
                result = self.director.get_task_result(task_id)
                error_msg = result.error_message if result else "Unknown error"
                failed.append({'folder': folder_name, 'error': error_msg})
            
            results[task_id] = {
                'folder_name': folder_name,
                'status': status,
                'result': self.director.get_task_result(task_id)
            }
        
        return {
            'total_tasks': len(task_ids),
            'successful': successful,
            'failed': failed,
            'success_count': len(successful),
            'failure_count': len(failed),
            'results': results
        }


def create_folder_processor(backend_type: str = "python", 
                          cpu_workers: int = 4, 
                          io_workers: int = 8,
                          progress_callback: Optional[Callable] = None) -> FolderProcessor:
    """
    Create and initialize a folder processor with director service.
    
    Args:
        backend_type: 'python' or 'redis' (celery/redis)
        cpu_workers: Number of CPU workers
        io_workers: Number of I/O workers  
        progress_callback: Optional callback for progress updates
    
    Returns:
        Initialized FolderProcessor instance
    """
    # Initialize director with settings
    settings = {
        'workers': {
            'backend': backend_type,
            'cpu_workers': cpu_workers,
            'io_workers': io_workers
        }
    }
    
    director = FicheroDirector.get_instance(settings=settings)
    
    # Initialize backend if not already done
    if not director.backend or not director.backend.is_initialized:
        success = director.initialize_backend()
        if not success:
            raise RuntimeError("Failed to initialize director backend")
    
    return FolderProcessor(director, progress_callback) 