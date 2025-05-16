from scripts.utils.jsonl_manager import JSONLManager
from pathlib import Path
import time
import random
import os
import fcntl
import json
from typing import Optional, Dict, Any, List
from rich.console import Console
from scripts.utils.logging_utils import rich_log, should_show_progress

console = Console()

class StepManifest:
    """Manages step-specific manifest files with progress tracking."""
    
    def __init__(self, step_name: str, base_dir: str = "data"):
        """
        Initialize StepManifest.
        
        Args:
            step_name: Name of the processing step
            base_dir: Base directory for manifest files
        """
        self.step_name = step_name
        self.base_dir = Path(base_dir)
        self.manifest_dir = self.base_dir / "manifests"
        self.manifest_file = self.manifest_dir / f"{step_name}_manifest.jsonl"
        self.jsonl_manager = JSONLManager(str(self.manifest_file))
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure required directories exist."""
        try:
            self.manifest_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            rich_log("error", f"Error creating manifest directory {self.manifest_dir}: {str(e)}")
            raise

    def add_entry(self, file_path: str, status: str = "pending", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add a new entry to the manifest.
        
        Args:
            file_path: Path to the file being processed
            status: Current status of the file
            metadata: Additional metadata about the file
            
        Returns:
            bool: True if entry was added successfully
        """
        try:
            entry = {
                "file_path": str(file_path),
                "status": status,
                "metadata": metadata or {}
            }
            return self.jsonl_manager.append_entry(entry)
        except Exception as e:
            rich_log("error", f"Error adding entry to manifest: {str(e)}")
            return False

    def update_status(self, file_path: str, status: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update the status of a file in the manifest.
        
        Args:
            file_path: Path to the file
            status: New status
            metadata: Additional metadata to update
            
        Returns:
            bool: True if update was successful
        """
        try:
            entry = self.jsonl_manager.read_entry("file_path", str(file_path))
            if not entry:
                rich_log("warning", f"No entry found for {file_path}")
                return False
                
            if metadata:
                entry["metadata"].update(metadata)
            entry["status"] = status
            
            return self.jsonl_manager.update_entry("file_path", str(file_path), entry)
        except Exception as e:
            rich_log("error", f"Error updating status in manifest: {str(e)}")
            return False

    def get_status(self, file_path: str) -> Optional[str]:
        """
        Get the current status of a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Optional[str]: Current status or None if not found
        """
        try:
            entry = self.jsonl_manager.read_entry("file_path", str(file_path))
            return entry["status"] if entry else None
        except Exception as e:
            rich_log("error", f"Error getting status from manifest: {str(e)}")
            return None

    def get_pending_files(self) -> List[str]:
        """
        Get list of files with pending status.
        
        Returns:
            List[str]: List of file paths with pending status
        """
        try:
            entries = self.jsonl_manager.read_all()
            return [entry["file_path"] for entry in entries if entry["status"] == "pending"]
        except Exception as e:
            rich_log("error", f"Error getting pending files from manifest: {str(e)}")
            return []

    def get_completed_files(self) -> List[str]:
        """
        Get list of files with completed status.
        
        Returns:
            List[str]: List of file paths with completed status
        """
        try:
            entries = self.jsonl_manager.read_all()
            return [entry["file_path"] for entry in entries if entry["status"] == "completed"]
        except Exception as e:
            rich_log("error", f"Error getting completed files from manifest: {str(e)}")
            return []

    def get_failed_files(self) -> List[str]:
        """
        Get list of files with failed status.
        
        Returns:
            List[str]: List of file paths with failed status
        """
        try:
            entries = self.jsonl_manager.read_all()
            return [entry["file_path"] for entry in entries if entry["status"] == "failed"]
        except Exception as e:
            rich_log("error", f"Error getting failed files from manifest: {str(e)}")
            return []

    def get_all_files(self) -> List[Dict[str, Any]]:
        """
        Get all entries from the manifest.
        
        Returns:
            List[Dict[str, Any]]: List of all entries
        """
        try:
            return self.jsonl_manager.read_all()
        except Exception as e:
            rich_log("error", f"Error getting all files from manifest: {str(e)}")
            return []

    def clear_manifest(self) -> bool:
        """
        Clear all entries from the manifest.
        
        Returns:
            bool: True if clear was successful
        """
        try:
            return self.jsonl_manager.batch_update([])
        except Exception as e:
            rich_log("error", f"Error clearing manifest: {str(e)}")
            return False

    def get_progress(self) -> Dict[str, int]:
        """
        Get progress statistics for the step.
        
        Returns:
            Dict[str, int]: Dictionary with counts for each status
        """
        try:
            entries = self.jsonl_manager.read_all()
            status_counts = {"total": len(entries)}
            for entry in entries:
                status = entry["status"]
                status_counts[status] = status_counts.get(status, 0) + 1
            return status_counts
        except Exception as e:
            rich_log("error", f"Error getting progress from manifest: {str(e)}")
            return {"total": 0}

class StepManifestManager:
    def __init__(self, manifest_path: str, step: str):
        rich_log("debug", f"Initializing StepManifestManager for {step} with manifest {manifest_path}")
        self.manifest = JSONLManager(manifest_path)
        self.step = step
        self.max_retries = 3
        self.base_delay = 0.1  # Base delay in seconds
        self.worker_id = os.environ.get('WORKER_ID', '0')
        self.claim_timeout = 30  # Maximum time to wait for a claim
        self.processing_timeout = 300  # Maximum time a file can be in processing state
        self.lock_file = f"{manifest_path}.lock"

    def cleanup_stale_tasks(self) -> int:
        """Clean up stale processing tasks.
        Returns number of tasks cleaned up."""
        cleaned = 0
        lock_fd = self._acquire_lock()
        try:
            entries = self.manifest.all_entries()
            current_time = time.time()
            
            for entry in entries:
                if (entry.get("type") == "file" and 
                    entry.get(f"{self.step}_status") == "processing"):
                    start_time = entry.get(f"{self.step}_start_time", 0)
                    if current_time - start_time > self.processing_timeout:
                        rich_log("warning", f"Cleaning up stale task: {entry['input_path']}")
                        self.manifest.update_entry(
                            entry["input_path"],
                            **{
                                f"{self.step}_status": "pending",
                                f"{self.step}_worker": None,
                                f"{self.step}_start_time": None,
                                f"{self.step}_error": "Task timed out"
                            }
                        )
                        cleaned += 1
            return cleaned
        finally:
            self._release_lock(lock_fd)

    def get_next_pending(self) -> Optional[str]:
        """Get next pending file with improved stale task handling."""
        rich_log("debug", f"Worker {self.worker_id} looking for next pending file")
        retries = 0
        start_time = time.time()
        
        # Clean up stale tasks periodically (every 5 minutes)
        if time.time() % 300 < 1:  # Check roughly every 5 minutes
            cleaned = self.cleanup_stale_tasks()
            if cleaned > 0:
                rich_log("info", f"Cleaned up {cleaned} stale tasks")
        
        while retries < self.max_retries and (time.time() - start_time) < self.claim_timeout:
            rich_log("debug", f"Worker {self.worker_id} attempt {retries + 1}/{self.max_retries}")
            lock_fd = self._acquire_lock()
            try:
                # Get all entries and find pending ones
                entries = self.manifest.all_entries()
                
                # Find first pending file not claimed by another worker
                for entry in entries:
                    if (entry.get("type") == "file" and 
                        isinstance(entry.get("input_path"), str) and  # Ensure input_path is a string
                        entry.get(f"{self.step}_status") in [None, "pending"] and
                        not entry.get(f"{self.step}_worker")):
                        
                        # Claim this file
                        success = self.manifest.update_entry(
                            entry["input_path"],
                            **{
                                f"{self.step}_status": "processing",
                                f"{self.step}_worker": self.worker_id,
                                f"{self.step}_start_time": time.time()
                            }
                        )
                        if success:
                            return entry["input_path"]
                        else:
                            rich_log("warning", f"Failed to claim file: {entry['input_path']}")
                
                # No pending files found
                return None
                
            except Exception as e:
                rich_log("error", f"Error getting next pending file: {str(e)}")
                retries += 1
            finally:
                self._release_lock(lock_fd)
                
            # Add small delay between retries
            if retries < self.max_retries:
                delay = self.base_delay * (2 ** retries) + random.uniform(0, 0.1)
                time.sleep(delay)
                
        rich_log("warning", f"Worker {self.worker_id} failed to get next file after {retries} retries")
        return None

    def _acquire_lock(self):
        """Acquire a file lock for manifest updates"""
        rich_log("debug", f"Worker {self.worker_id} attempting to acquire lock")
        start_time = time.time()
        lock_fd = open(self.lock_file, 'w')
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            rich_log("debug", f"Worker {self.worker_id} acquired lock in {time.time() - start_time:.2f}s")
            return lock_fd
        except Exception as e:
            rich_log("error", f"Worker {self.worker_id} failed to acquire lock: {e}")
            lock_fd.close()
            raise e

    def _release_lock(self, lock_fd):
        """Release the file lock"""
        rich_log("debug", f"Worker {self.worker_id} releasing lock")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            lock_fd.close()

    def claim(self, input_path: str, lock_fd=None) -> bool:
        """Try to claim a file with exponential backoff retry."""
        retries = 0
        should_release = False
        
        if lock_fd is None:
            lock_fd = self._acquire_lock()
            should_release = True
            
        try:
            while retries < self.max_retries:
                try:
                    entry = self.manifest.get_entry(input_path)
                    if entry and entry.get("type") == "file" and entry.get(f"{self.step}_status") == "pending":
                        # Try to update status to processing
                        self.manifest.update_entry(
                            input_path,
                            **{
                                f"{self.step}_status": "processing",
                                f"{self.step}_worker": self.worker_id,
                                f"{self.step}_start_time": time.time()
                            }
                        )
                        return True
                except Exception as e:
                    rich_log("debug", f"Worker {self.worker_id} claim attempt failed: {str(e)}")
                    delay = self.base_delay * (2 ** retries) + random.uniform(0, 0.1)
                    time.sleep(delay)
                    retries += 1
                    continue
                return False
        finally:
            if should_release:
                self._release_lock(lock_fd)
        return False

    def mark_done(self, input_path: str, **fields) -> bool:
        """Mark a file as done with all its details."""
        retries = 0
        while retries < self.max_retries:
            lock_fd = self._acquire_lock()
            try:
                update_fields = {
                    f"{self.step}_status": "done",
                    f"{self.step}_end_time": time.time()
                }
                update_fields.update(fields)
                success = self.manifest.update_entry(input_path, **update_fields)
                if success:
                    rich_log("info", f"Worker {self.worker_id} completed file: {input_path}")
                    return True
                else:
                    rich_log("warning", f"Failed to mark file as done: {input_path}, retrying...")
                    retries += 1
            except Exception as e:
                rich_log("error", f"Error marking file as done {input_path}: {str(e)}")
                retries += 1
            finally:
                self._release_lock(lock_fd)
            
            if retries < self.max_retries:
                delay = self.base_delay * (2 ** retries) + random.uniform(0, 0.1)
                time.sleep(delay)
        
        rich_log("error", f"Failed to mark file as done after {retries} retries: {input_path}")
        return False

    def mark_error(self, input_path: str, error: str) -> bool:
        """Mark a file as error with error message."""
        retries = 0
        while retries < self.max_retries:
            lock_fd = self._acquire_lock()
            try:
                success = self.manifest.update_entry(
                    input_path,
                    **{
                        f"{self.step}_status": "error",
                        f"{self.step}_error": error,
                        f"{self.step}_end_time": time.time()
                    }
                )
                if success:
                    rich_log("error", f"Worker {self.worker_id} failed file {input_path}: {error}")
                    return True
                else:
                    rich_log("warning", f"Failed to mark file as error: {input_path}, retrying...")
                    retries += 1
            except Exception as e:
                rich_log("error", f"Error marking file as error {input_path}: {str(e)}")
                retries += 1
            finally:
                self._release_lock(lock_fd)
            
            if retries < self.max_retries:
                delay = self.base_delay * (2 ** retries) + random.uniform(0, 0.1)
                time.sleep(delay)
        
        rich_log("error", f"Failed to mark file as error after {retries} retries: {input_path}")
        return False 