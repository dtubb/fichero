"""
Progress Tracking Utility

Provides progress tracking and statistics without Rich progress bars.
Uses tool_logger for consistent output across workflow and CLI contexts.
"""

from pathlib import Path
from datetime import datetime
import srsly
import os
from fichero.tool_logger import get_tool_logger

tool_logger = get_tool_logger('progress')

class ProcessingProgress:
    """Handle progress file tracking and stats"""
    def __init__(self, progress_file: Path):
        self.progress_file = progress_file
        self.stats = self.load_progress()

    def load_progress(self) -> dict:
        """Load last progress stats"""
        if not self.progress_file.exists():
            return {"processed": 0, "skipped": 0, "failed": 0, "total": 0}
            
        try:
            with open(self.progress_file, 'rb') as f:
                f.seek(-min(os.path.getsize(self.progress_file), 4096), os.SEEK_END)
                last_line = f.read().decode().strip().split('\n')[-1]
                entry = srsly.json_loads(last_line)
                return entry.get("stats", {})
        except Exception:
            return {"processed": 0, "skipped": 0, "failed": 0, "total": 0}

    def save_progress(self, stats: dict, current_idx: int):
        """Save current progress"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "stats": stats,
            "processed_count": current_idx
        }
        with open(self.progress_file, "a") as f:
            f.write(srsly.json_dumps(entry) + "\n")

    @property
    def processed_count(self) -> int:
        """Get number of processed files"""
        return self.stats.get("processed", 0)

class ProgressTracker:
    """
    Simple progress tracker that uses tool_logger instead of Rich progress bars.
    
    Provides progress updates via logging rather than visual progress bars.
    This eliminates Rich dependencies and works consistently in both workflow and CLI contexts.
    """
    def __init__(self, total: int, task_name: str, progress_fields: dict):
        # Remove total from progress_fields since it's passed separately
        fields = progress_fields.copy()
        if 'total' in fields:
            del fields['total']
            
        self.total = total
        self.task_name = task_name
        self.stats = fields
        self.processed = 0
        
        # Log initial progress
        tool_logger.info(f"Starting {task_name}: {total} items to process")
        tool_logger.progress(f"Progress: 0/{total} (0%)")

    def update(self, advance: int = 1, **fields):
        """Update progress and stats"""
        self.stats.update(fields)
        self.processed += advance
        
        # Calculate percentage
        percentage = (self.processed / self.total) * 100 if self.total > 0 else 0
        
        # Log progress update
        tool_logger.progress(f"Progress: {self.processed}/{self.total} ({percentage:.1f}%)")
        
        # Log stats if they changed significantly
        if self.processed % 10 == 0 or self.processed == self.total:  # Log every 10 items or on completion
            stats_str = ", ".join(f"{k}: {v}" for k, v in self.stats.items() if v > 0)
            if stats_str:
                tool_logger.info(f"Stats: {stats_str}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Log completion
        if exc_type is None:
            tool_logger.success(f"Completed {self.task_name}: {self.processed}/{self.total} items")
        else:
            tool_logger.error(f"Failed {self.task_name}: {exc_val}")
        return False  # Don't suppress exceptions
