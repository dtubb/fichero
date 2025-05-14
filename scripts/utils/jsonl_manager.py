import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading
import fcntl
import time
import atexit
import logging

logger = logging.getLogger(__name__)

class JSONLManager:
    def __init__(self, path: str):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix('.lock')
        self._lock = threading.RLock()  # Use reentrant lock to prevent deadlock
        self._file_locks = {}  # Track file locks
        self._ensure_file_exists()
        atexit.register(self._cleanup_locks)

    def _cleanup_locks(self):
        """Clean up any remaining file locks."""
        for file_obj in self._file_locks.values():
            try:
                fcntl.flock(file_obj, fcntl.LOCK_UN)
                file_obj.close()
            except Exception:
                pass

    def _ensure_file_exists(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("")

    def _acquire_file_lock(self, file_obj, timeout=5.0):
        """Acquire an exclusive lock on the file with timeout."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                fcntl.flock(file_obj, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._file_locks[id(file_obj)] = file_obj
                return True
            except IOError:
                time.sleep(0.1)  # Wait a bit before retrying
        return False

    def _release_file_lock(self, file_obj):
        """Release the file lock."""
        try:
            fcntl.flock(file_obj, fcntl.LOCK_UN)
            if id(file_obj) in self._file_locks:
                del self._file_locks[id(file_obj)]
        except Exception:
            pass

    def all_entries(self) -> List[Dict[str, Any]]:
        """Read all entries from the JSONL file."""
        with self._lock:
            if not self.path.exists():
                return []
            
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    if not self._acquire_file_lock(f):
                        logger.warning("Could not acquire file lock for reading")
                        return []
                    
                    try:
                        entries = []
                        for i, line in enumerate(f, 1):
                            line = line.strip()
                            if not line:  # Skip empty lines
                                continue
                            try:
                                entry = json.loads(line)
                                entries.append(entry)
                            except json.JSONDecodeError as e:
                                logger.error(f"Invalid JSON at line {i}: {e}")
                                raise
                        return entries
                    finally:
                        self._release_file_lock(f)
            except Exception as e:
                logger.error(f"Error reading manifest: {e}")
                raise

    def get_entry(self, input_path: str) -> Optional[Dict[str, Any]]:
        """Get a single entry by input_path."""
        for entry in self.all_entries():
            if entry.get('input_path') == input_path:
                return entry
        return None

    def update_entry(self, input_path: str, **fields) -> None:
        """Update or add an entry for input_path, atomically."""
        with self._lock:
            entries = self.all_entries()
            updated = False
            for entry in entries:
                if entry.get('input_path') == input_path:
                    entry.update(fields)
                    updated = True
                    break
            if not updated:
                entry = {'input_path': input_path, **fields}
                entries.append(entry)
            self._atomic_write(entries)

    def batch_update(self, updates: List[Dict[str, Any]]):
        """Batch update entries. Each dict must have 'input_path'."""
        try:
            with self._lock:
                # Filter out any existing entries that don't have input_path
                existing_entries = self.all_entries()
                valid_entries = {e['input_path']: e for e in existing_entries if 'input_path' in e}
                
                # Process updates
                for update in updates:
                    if 'input_path' not in update:
                        print(f"[WARNING] Skipping update without input_path: {update}")
                        continue
                    ip = update['input_path']
                    if ip in valid_entries:
                        valid_entries[ip].update(update)
                    else:
                        valid_entries[ip] = update
                
                # Write back all valid entries
                self._atomic_write(list(valid_entries.values()))
        except Exception as e:
            print(f"[ERROR] Exception in batch_update: {e}")
            import traceback
            traceback.print_exc()
            raise

    def filter_entries(self, **criteria) -> List[Dict[str, Any]]:
        return [e for e in self.all_entries() if all(e.get(k) == v for k, v in criteria.items())]

    def _atomic_write(self, entries: List[Dict[str, Any]]):
        """Write all entries atomically to the JSONL file."""
        # Create temp file in same directory as target
        tmp_path = self.path.with_suffix('.tmp')
        
        try:
            # Write to temp file first
            with open(tmp_path, 'w', encoding='utf-8') as f:
                if not self._acquire_file_lock(f):
                    logger.warning("Could not acquire file lock for writing")
                    return
                
                try:
                    for entry in entries:
                        json_str = json.dumps(entry, ensure_ascii=False)
                        f.write(json_str + '\n')
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    self._release_file_lock(f)
            
            # Now atomically rename temp file to target
            with open(self.path, 'r+', encoding='utf-8') as f:
                if not self._acquire_file_lock(f):
                    logger.warning("Could not acquire file lock for rename")
                    return
                
                try:
                    # Rename temp file to target
                    tmp_path.replace(self.path)
                finally:
                    self._release_file_lock(f)
        finally:
            # Clean up temp file if it still exists
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass 