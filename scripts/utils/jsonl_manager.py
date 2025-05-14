import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading

try:
    import portalocker  # Cross-platform file locking
except ImportError:
    portalocker = None

class JSONLManager:
    def __init__(self, path: str):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix('.lock')
        self._lock = threading.RLock()  # Use reentrant lock to prevent deadlock
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("")

    def _acquire_file_lock(self, file_obj):
        if portalocker:
            try:
                portalocker.lock(file_obj, portalocker.LOCK_EX | portalocker.LOCK_NB, timeout=1)
            except portalocker.exceptions.LockException:
                pass
        # else: no-op (not safe, but fallback)

    def _release_file_lock(self, file_obj):
        if portalocker:
            try:
                portalocker.unlock(file_obj)
            except Exception as e:
                pass

    def all_entries(self) -> List[Dict[str, Any]]:
        """Read all entries from the JSONL file."""
        with self._lock:
            if not self.path.exists():
                return []
            try:
                with self.path.open('r', encoding='utf-8') as f:
                    entries = []
                    for i, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:  # Skip empty lines
                            continue
                        try:
                            entry = json.loads(line)
                            entries.append(entry)
                        except json.JSONDecodeError as e:
                            print(f"[ERROR] Invalid JSON at line {i}: {e}")
                            raise
                    return entries
            except Exception as e:
                print(f"[ERROR] Error reading manifest: {e}")
                raise

    def get_entry(self, input_path: str) -> Optional[Dict[str, Any]]:
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
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, 'w', encoding='utf-8') as f:
                    for entry in valid_entries.values():
                        json_str = json.dumps(entry, ensure_ascii=False)
                        f.write(json_str + '\n')
        except Exception as e:
            print(f"[ERROR] Exception in batch_update: {e}")
            import traceback
            traceback.print_exc()
            raise

    def filter_entries(self, **criteria) -> List[Dict[str, Any]]:
        return [e for e in self.all_entries() if all(e.get(k) == v for k, v in criteria.items())]

    def _atomic_write(self, entries: List[Dict[str, Any]]):
        """Temporarily disabled for debugging"""
        pass 