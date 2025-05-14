import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading
import fcntl
import time
import atexit
from rich.console import Console

console = Console()

def rich_log(level, message):
    """Log a message with rich formatting, respecting debug mode."""
    # Get debug mode from environment
    debug_mode = os.environ.get('FICHERO_DEBUG', '0') == '1'
    
    if level == "info":
        if debug_mode:
            console.log(f"[bold cyan][INFO][/bold cyan] {message}")
        else:
            # In non-debug mode, only show important info messages
            if "Processing complete" in message or "Processing " in message and "files" in message:
                console.log(f"[bold cyan][INFO][/bold cyan] {message}")
    elif level == "warning":
        console.log(f"[bold yellow][WARNING][/bold yellow] {message}")
    elif level == "error":
        console.log(f"[bold red][ERROR][/bold red] {message}")
    elif level == "debug" and debug_mode:
        console.log(f"[dim][DEBUG][/dim] {message}")

class JSONLManager:
    def __init__(self, file_path: str, cache_duration: int = 5):
        """Initialize JSONLManager with longer cache duration."""
        self.file_path = file_path
        self._lock = threading.Lock()
        self._cache = {}
        self._cache_timestamp = 0
        self._cache_valid_duration = cache_duration  # Cache for 5 seconds by default
        self._file_mtime = 0
        self.path = Path(file_path)
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

    def _read_entries_from_file(self) -> List[Dict[str, Any]]:
        """Read all entries from the JSONL file without caching."""
        if not self.path.exists():
            return []
        
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                if not self._acquire_file_lock(f):
                    rich_log("warning", "Could not acquire file lock for reading")
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
                            rich_log("error", f"Invalid JSON at line {i}: {e}")
                            raise
                    return entries
                finally:
                    self._release_file_lock(f)
        except Exception as e:
            rich_log("error", f"Error reading manifest: {e}")
            raise

    def all_entries(self) -> List[Dict[str, Any]]:
        """Get all entries with improved caching."""
        current_time = time.time()
        
        # Check if file has been modified
        try:
            current_mtime = os.path.getmtime(self.file_path)
        except OSError:
            current_mtime = 0
        
        # Use cache if it's valid and file hasn't changed
        if (self._cache and 
            current_time - self._cache_timestamp < self._cache_valid_duration and
            current_mtime == self._file_mtime):
            return list(self._cache.values())
        
        # Cache is invalid or file changed, read from file
        with self._lock:
            # Double check in case another thread updated cache
            if (current_time - self._cache_timestamp < self._cache_valid_duration and
                current_mtime == self._file_mtime):
                return list(self._cache.values())
            
            entries = self._read_entries_from_file()
            self._cache = {entry["input_path"]: entry for entry in entries}
            self._cache_timestamp = current_time
            self._file_mtime = current_mtime
            return list(self._cache.values())

    def get_entry(self, input_path: str) -> Optional[Dict[str, Any]]:
        """Get a single entry by input_path with caching."""
        current_time = time.time()
        
        # Check cache first
        if self._cache and current_time - self._cache_timestamp < self._cache_valid_duration:
            return self._cache.get(input_path)
        
        # Cache miss or invalid, refresh cache
        self.all_entries()
        return self._cache.get(input_path)

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
                        rich_log("warning", f"Skipping update without input_path: {update}")
                        continue
                    ip = update['input_path']
                    if ip in valid_entries:
                        valid_entries[ip].update(update)
                    else:
                        valid_entries[ip] = update
                
                # Write back all valid entries
                self._atomic_write(list(valid_entries.values()))
        except Exception as e:
            rich_log("error", f"Exception in batch_update: {e}")
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
                    rich_log("warning", "Could not acquire file lock for writing")
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
                    rich_log("warning", "Could not acquire file lock for rename")
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