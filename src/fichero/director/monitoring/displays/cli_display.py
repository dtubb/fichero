"""
CLI Task Display

Terminal-based task monitoring using Rich library for formatted output.
Reads data from TaskMonitor and displays it in two backend-aware modes:

1. **Local Session Mode** (Python backend): 
   - Shows tasks from current processing session only
   - Exits automatically when all tasks complete
   - Used by `process` command

2. **Global Activity Monitor Mode** (Celery/Redis backend):
   - Shows all tasks across all sessions/users
   - Runs indefinitely until user interrupts (Ctrl+C)
   - Used by `activity-monitor` command

Both modes display:
- Folder names (not full paths)
- Task status with icons (● Running, ○ Waiting, ✓ Completed, ✗ Failed)
- Worker type indicators when available
- Real-time status summary

Example Usage:
    ```python
    from rich.console import Console
    from ..task_monitor import TaskMonitor
    
    console = Console()
    task_monitor = TaskMonitor.get_instance()
    display = CLITaskDisplay(console, task_monitor)
    
    # Show local session tasks (Python backend)
    display.show_tasks(filter_current_only=True)
    
    # Show global activity monitor (Celery/Redis backend)
    display.show_tasks(filter_current_only=False)
    ```

Refactored July 6, 2025, to remove redundant code, and to share code with GUI display via task_monitor.py. 
"""

import time
import logging
from typing import Optional

# Rich library for terminal displays
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich.layout import Layout
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from ..task_monitor import TaskMonitor

logger = logging.getLogger(__name__)


class CLITaskDisplay:
    """
    Terminal-based task display using Rich formatting.
    
    Thin presentation layer that reads from TaskMonitor and formats
    the data for terminal display in two backend-aware modes.
    
    Attributes:
        console (Console): Rich console for formatted output
        task_monitor (TaskMonitor): Source of task data
    """
    
    def __init__(self, console: Optional[Console] = None, task_monitor: Optional[TaskMonitor] = None):
        """
        Initialize CLI display.
        
        Args:
            console: Rich console for output. Creates default Console() if None.
            task_monitor: TaskMonitor instance to read data from. Required for display.
            
        Raises:
            ImportError: If Rich library is not available
        """
        if not RICH_AVAILABLE:
            raise ImportError("Rich is required for CLI displays. Install with: pip install rich")
        
        self.console = console or Console()
        self.task_monitor = task_monitor
        
        logger.info("CLITaskDisplay initialized")

    def show_tasks(self, filter_current_only: bool = False):
        """
        Display tasks in terminal with continuous updates.
        
        Args:
            filter_current_only: Backend-aware display mode selector
                - True: Local session mode - show current tasks, exit when complete
                - False: Global activity monitor - show all tasks, run until interrupted
        """
        if not self.task_monitor:
            self.console.print("✗ No task monitor available", style="red")
            return
        
        if filter_current_only:
            self._show_live_tasks(
                title="Local Session Tasks", 
                header="● Local Session Tasks (Python Backend)",
                exit_when_complete=True
            )
        else:
            self._show_live_tasks(
                title="All Tasks",
                header="○ Global Activity Monitor (Celery/Redis) - Press Ctrl+C to exit", 
                exit_when_complete=False
            )

    def _show_live_tasks(self, title: str, header: str, exit_when_complete: bool):
        """
        Unified live task display with Rich Live updates.
        
        Args:
            title: Title for the task table
            header: Header message to display
            exit_when_complete: If True, exit when all tasks complete; if False, run forever
        """
        self.console.print(header, style="cyan")
        self.console.print()
        
        try:
            # Brief delay to allow TaskMonitor to register tasks (for local sessions)
            if exit_when_complete:
                time.sleep(1)
            
            with Live(self._create_display_content(title), refresh_per_second=4, console=self.console) as live:
                while True:
                    live.update(self._create_display_content(title))
                    
                    # Check if we should exit when tasks complete
                    if exit_when_complete:
                        try:
                            all_completed, _ = self.task_monitor.get_all_tasks_completion_status()
                        except Exception as e:
                            logger.warning(f"Failed to check task completion: {e}")
                            all_completed = True  # Assume complete if we can't check
                        
                        if all_completed:
                            break
                    
                    time.sleep(0.25)  # Update 4 times per second for smooth animation
                
        except KeyboardInterrupt:
            mode_name = "Local session monitoring" if exit_when_complete else "Global Activity Monitor"
            self.console.print(f"\n■ {mode_name} stopped", style="yellow")
        except Exception as e:
            logger.error(f"Display loop error: {e}")
            raise

    def _create_display_content(self, title: str):
        """
        Create Rich layout with status panel and task table.
        
        Args:
            title: Title for the task table
            
        Returns:
            Layout with status panel and task table
        """
        # Create layout
        layout = Layout()
        layout.split_column(
            Layout(name="status", size=3),
            Layout(name="table")
        )
        
        # Get status summary
        try:
            status_text = self.task_monitor.get_status_summary(None)
        except Exception as e:
            logger.warning(f"Failed to get status summary: {e}")
            status_text = "Status unavailable"
        
        status_panel = Panel(
            status_text,
            title="Status",
            border_style="blue"
        )
        layout["status"].update(status_panel)
        
        # Create and populate task table
        table = Table(title=title)
        table.add_column("Folder", width=25)
        table.add_column("Status", width=60)  # Wider status column
        
        try:
            display_data = self.task_monitor.create_display_data(None)
        except Exception as e:
            logger.warning(f"Failed to get display data: {e}")
            display_data = []
        
        if not display_data:
            table.add_row("○ No tasks to display", "")
        else:
            for row_data in display_data:
                table.add_row(
                    row_data.get('folder', ''),
                    row_data.get('status', '')
                )
        
        layout["table"].update(table)
        return layout