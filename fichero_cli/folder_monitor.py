import asyncio
from pathlib import Path
import json
import logging
from typing import Set, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

class AsyncFolderMonitor:
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self.folder_tasks: Dict[str, asyncio.Task] = {}
        self.manifest_lock = asyncio.Lock()
        self.active_folders: Set[str] = set()
        
    async def get_active_folders(self) -> Set[str]:
        """Get all folders that have pending or processing files."""
        async with self.manifest_lock:
            with open(self.manifest_path, 'r') as f:
                for line in f:
                    entry = json.loads(line)
                    if entry['status'] in ['pending', 'processing']:
                        self.active_folders.add(entry['folder'])
        return self.active_folders

    async def is_folder_complete(self, folder: str) -> bool:
        """Check if all files in a folder are complete."""
        async with self.manifest_lock:
            with open(self.manifest_path, 'r') as f:
                for line in f:
                    entry = json.loads(line)
                    if entry['folder'] == folder and entry['status'] not in ['completed', 'error']:
                        return False
        return True
        
    async def process_folder(self, folder: str):
        """Handle folder-level processing."""
        logger.info(f"Processing folder: {folder}")
        try:
            # TODO: Implement actual folder processing
            # This could include:
            # - Merging transcriptions
            # - Creating PDFs
            # - Archiving
            await asyncio.sleep(1)  # Simulate processing
            logger.info(f"Completed folder processing: {folder}")
        except Exception as e:
            logger.error(f"Error processing folder {folder}: {str(e)}")
            raise
        
    async def watch_folders(self):
        """Continuously monitor folders for completion."""
        while True:
            try:
                folders = await self.get_active_folders()
                for folder in folders:
                    if await self.is_folder_complete(folder):
                        if folder not in self.folder_tasks:
                            self.folder_tasks[folder] = asyncio.create_task(
                                self.process_folder(folder)
                            )
                            logger.info(f"Started processing folder: {folder}")
                
                # Clean up completed folder tasks
                completed = []
                for folder, task in self.folder_tasks.items():
                    if task.done():
                        completed.append(folder)
                        if task.exception():
                            logger.error(f"Folder task failed: {folder}")
                
                for folder in completed:
                    del self.folder_tasks[folder]
                    self.active_folders.remove(folder)
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in folder monitoring: {str(e)}")
                await asyncio.sleep(5)  # Wait before retrying 