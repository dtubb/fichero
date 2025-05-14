from scripts.utils.jsonl_manager import JSONLManager
from pathlib import Path
import time
import random
import os
import logging
import fcntl
import json
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class StepManifestManager:
    def __init__(self, manifest_path: str, step: str):
        self.manifest = JSONLManager(manifest_path)
        self.step = step
        self.max_retries = 3
        self.base_delay = 0.1  # Base delay in seconds
        self.worker_id = os.environ.get('WORKER_ID', '0')
        self.claim_timeout = 30  # Maximum time to wait for a claim
        self.processing_timeout = 300  # Maximum time a file can be in processing state
        self.lock_file = f"{manifest_path}.lock"

    def get_all_files(self) -> List[str]:
        """Get all files from the manifest."""
        files = []
        for entry in self.manifest.all_entries():
            if entry.get("type") == "file":
                files.append(entry["input_path"])
        return files

    def is_pending(self, input_path: str) -> bool:
        """Check if a file is pending for this step."""
        entry = self.manifest.get_entry(input_path)
        if entry and entry.get("type") == "file":
            status = entry.get(f"{self.step}_status")
            return status == "pending"
        return False

    def _acquire_lock(self):
        """Acquire a file lock for manifest updates"""
        lock_fd = open(self.lock_file, 'w')
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            return lock_fd
        except Exception as e:
            lock_fd.close()
            raise e

    def _release_lock(self, lock_fd):
        """Release the file lock"""
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            lock_fd.close()

    def get_next_pending(self) -> Optional[str]:
        """Get next pending file with exponential backoff retry."""
        retries = 0
        start_time = time.time()
        
        while retries < self.max_retries and (time.time() - start_time) < self.claim_timeout:
            lock_fd = self._acquire_lock()
            try:
                # Get all entries and filter for pending files
                pending_files = []
                for entry in self.manifest.all_entries():
                    if entry.get("type") == "file":
                        status = entry.get(f"{self.step}_status")
                        if status == "pending":
                            pending_files.append(entry["input_path"])
                        elif status == "processing":
                            # Check for stale processing entries
                            start_time = entry.get(f"{self.step}_start_time", 0)
                            if time.time() - start_time > self.processing_timeout:
                                logger.warning(f"Found stale processing entry for {entry['input_path']}, resetting to pending")
                                self.manifest.update_entry(
                                    entry["input_path"],
                                    **{
                                        f"{self.step}_status": "pending",
                                        f"{self.step}_worker": None,
                                        f"{self.step}_start_time": None
                                    }
                                )
                                pending_files.append(entry["input_path"])
                
                if pending_files:
                    # Try to claim each file until one succeeds
                    for input_path in pending_files:
                        if self.claim(input_path, lock_fd):
                            logger.info(f"Worker {self.worker_id} claimed file: {input_path}")
                            return input_path
            finally:
                self._release_lock(lock_fd)
            
            # If no files could be claimed, wait with exponential backoff
            delay = self.base_delay * (2 ** retries) + random.uniform(0, 0.1)
            logger.debug(f"Worker {self.worker_id} waiting {delay:.2f}s for next file")
            time.sleep(delay)
            retries += 1
            
        return None

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
                    logger.debug(f"Worker {self.worker_id} claim attempt failed: {str(e)}")
                    delay = self.base_delay * (2 ** retries) + random.uniform(0, 0.1)
                    time.sleep(delay)
                    retries += 1
                    continue
                return False
        finally:
            if should_release:
                self._release_lock(lock_fd)
        return False

    def mark_done(self, input_path: str, **fields):
        """Mark a file as done with all its details."""
        lock_fd = self._acquire_lock()
        try:
            update_fields = {
                f"{self.step}_status": "done",
                f"{self.step}_end_time": time.time()
            }
            update_fields.update(fields)
            self.manifest.update_entry(input_path, **update_fields)
            logger.info(f"Worker {self.worker_id} completed file: {input_path}")
        finally:
            self._release_lock(lock_fd)

    def mark_error(self, input_path: str, error: str):
        """Mark a file as error with error message."""
        lock_fd = self._acquire_lock()
        try:
            self.manifest.update_entry(
                input_path,
                **{
                    f"{self.step}_status": "error",
                    f"{self.step}_error": error,
                    f"{self.step}_end_time": time.time()
                }
            )
            logger.error(f"Worker {self.worker_id} failed file {input_path}: {error}")
        finally:
            self._release_lock(lock_fd) 