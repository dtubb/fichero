"""
CLI Task Display

Simple CLI displays for task monitoring.
Handles both inline progress and activity monitoring.
"""

import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import platform

try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.columns import Columns
    from rich.layout import Layout
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from ..task_monitor import TaskMonitor, TaskInfo

logger = logging.getLogger(__name__)


class CLITaskDisplay:
    """
    Simple CLI display for tasks.
    
    Two main modes:
    1. Inline progress - show progress for single task (used by process command)
    2. Activity monitor - show all tasks (used by activity-monitor command)
    """
    
    def __init__(self, console: Optional[Console] = None, task_monitor: Optional[TaskMonitor] = None):
        if not RICH_AVAILABLE:
            raise ImportError("Rich is required for CLI displays")
        
        self.console = console or Console()
        self.task_monitor = task_monitor
        self.is_monitoring = False
        
        logger.info("CLITaskDisplay initialized")
    
    # Inline Progress (for process command)
    
    def show_task_progress(self, task_id: str, live_updates: bool = True):
        """Show progress for a single task with live updates"""
        if not self.task_monitor:
            self.console.print("❌ No task monitor available", style="red")
            return
        
        if live_updates:
            self._show_live_task_progress(task_id)
        else:
            self._show_static_task_progress(task_id)
    
    def _show_live_task_progress(self, task_id: str):
        """Show live updating progress for a task"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console
        ) as progress:
            
            # Add task to progress display
            progress_task = progress.add_task("Starting...", total=100)
            
            # Monitor until task completes
            while True:
                task_info = self.task_monitor.get_task(task_id)
                if not task_info:
                    progress.update(progress_task, description="Task not found", completed=100)
                    break
                
                # Update progress display
                description = f"{task_info.folder_name}"
                if task_info.current_step:
                    description += f" - {task_info.current_step}"
                
                progress.update(
                    progress_task,
                    description=description,
                    completed=task_info.overall_progress
                )
                
                # Check if finished
                if task_info.is_finished:
                    if task_info.status == "completed":
                        self.console.print(f"✅ Completed: {task_info.folder_name}", style="bold green")
                    elif task_info.status == "failed":
                        self.console.print(f"❌ Failed: {task_info.folder_name}", style="bold red")
                        if task_info.error_message:
                            self.console.print(f"Error: {task_info.error_message}", style="red")
                    else:
                        self.console.print(f"⏹️ Cancelled: {task_info.folder_name}", style="yellow")
                    break
                
                time.sleep(0.5)  # Update every 500ms
    
    def _show_static_task_progress(self, task_id: str):
        """Show current progress for a task (one-time)"""
        task_info = self.task_monitor.get_task(task_id)
        if not task_info:
            self.console.print("❌ Task not found", style="red")
            return
        
        # Create progress display
        progress_bar = self._create_progress_bar(task_info.overall_progress)
        
        self.console.print(f"📁 {task_info.folder_name}")
        self.console.print(f"Status: {task_info.status_icon} {task_info.status.title()}")
        if task_info.current_step:
            self.console.print(f"Step: {task_info.current_step}")
        self.console.print(f"Progress: {progress_bar} {task_info.overall_progress:.1f}%")
        if task_info.duration:
            self.console.print(f"Duration: {task_info.duration}")
    
    # Activity Monitor (for activity-monitor command)
    
    def show_all_tasks(self, live_updates: bool = False):
        """Show all tasks"""
        if not self.task_monitor:
            self.console.print("❌ No task monitor available", style="red")
            return
        
        if live_updates:
            self._show_live_activity_monitor()
        else:
            self._show_static_activity_monitor()
    
    def _show_static_activity_monitor(self):
        """Show current state of all tasks (one-time)"""
        # Backend info
        backend_info = self.task_monitor.get_backend_info()
        backend_panel = Panel(
            f"Backend: {backend_info.get('backend_name', 'Unknown')}\n"
            f"Status: {backend_info.get('status', 'Unknown')}",
            title="🔧 Backend Status",
            border_style="blue"
        )
        
        # Statistics
        stats = self.task_monitor.get_session_stats()
        stats_panel = Panel(
            f"Active: {stats['active_tasks']}\n"
            f"Session: {stats['session_tasks']}\n"
            f"Completed: {stats['completed_tasks']}\n"
            f"Failed: {stats['failed_tasks']}",
            title="📊 Statistics",
            border_style="green"
        )
        
        # Show top panels
        top_panels = Columns([backend_panel, stats_panel])
        self.console.print(top_panels)
        self.console.print()
        
        # Active tasks table
        active_tasks = self.task_monitor.get_active_tasks()
        self._show_tasks_table(active_tasks, "⚡ Active Tasks")
        
        # Recent failed tasks
        failed_tasks = self.task_monitor.get_failed_tasks()
        if failed_tasks:
            self.console.print()
            failed_dict = {t.task_id: t for t in failed_tasks[-5:]}  # Last 5 failures
            self._show_tasks_table(failed_dict, "❌ Recent Failures")
    
    def _show_live_activity_monitor(self):
        """Show live updating activity monitor"""
        self.console.print("🔄 Live Activity Monitor - Press Ctrl+C to exit")
        self.console.print()
        
        try:
            with Live(self._create_activity_layout(), console=self.console, refresh_per_second=1) as live:
                self.is_monitoring = True
                last_cleanup = time.time()
                
                while self.is_monitoring:
                    live.update(self._create_activity_layout())
                    
                    # Check if all tasks are finished
                    active_tasks = self.task_monitor.get_active_tasks()
                    running_tasks = {tid: task for tid, task in active_tasks.items() if task.status in ["pending", "running"]}
                    if not running_tasks:
                        # All tasks are done, show final status and exit
                        failed_tasks = {tid: task for tid, task in active_tasks.items() if task.status == "failed"}
                        if failed_tasks:
                            self.console.print(f"\n❌ Processing completed with {len(failed_tasks)} failed tasks", style="bold red")
                        else:
                            self.console.print("\n✅ All tasks completed successfully!", style="bold green")
                        break
                    
                    # Periodic cleanup of old failed tasks (every 30 seconds)
                    current_time = time.time()
                    if current_time - last_cleanup > 30:
                        self.task_monitor.cleanup_old_failed_tasks()
                        last_cleanup = current_time
                    
                    time.sleep(1.0)
        except KeyboardInterrupt:
            self.console.print("\n👋 Activity Monitor stopped", style="yellow")
        finally:
            self.is_monitoring = False
    
    def _create_activity_layout(self):
        """Create the live activity monitor layout"""
        # Backend info
        backend_info = self.task_monitor.get_backend_info()
        backend_panel = Panel(
            f"Backend: {backend_info.get('backend_name', 'Unknown')}\n"
            f"Status: {backend_info.get('status', 'Unknown')}\n"
            f"Updated: {datetime.now().strftime('%H:%M:%S')}",
            title="🔧 Backend",
            border_style="blue"
        )
        
        # Statistics
        stats = self.task_monitor.get_session_stats()
        stats_panel = Panel(
            f"Active: {stats['active_tasks']}\n"
            f"Session: {stats['session_tasks']}\n"
            f"Completed: {stats['completed_tasks']}\n"
            f"Failed: {stats['failed_tasks']}",
            title="📊 Stats",
            border_style="green"
        )
        
        # Tasks table
        active_tasks = self.task_monitor.get_active_tasks()
        tasks_table = self._create_tasks_table(active_tasks, "⚡ Active Tasks")
        
        # Create layout
        layout = Layout()
        layout.split_column(
            Layout(Columns([backend_panel, stats_panel]), size=8),
            Layout(tasks_table)
        )
        
        return layout
    
    def _show_tasks_table(self, tasks_dict: Dict[str, TaskInfo], title: str):
        """Show tasks in a table"""
        table = self._create_tasks_table(tasks_dict, title)
        self.console.print(table)
    
    def _create_tasks_table(self, tasks_dict: Dict[str, TaskInfo], title: str):
        """Create a Rich table for tasks"""
        table = Table(title=title)
        table.add_column("Folder", width=20)
        table.add_column("Status", width=8)
        table.add_column("Step", width=20)
        table.add_column("Progress", width=8)
        table.add_column("Worker", width=14)
        table.add_column("Backend", width=10)
        table.add_column("Duration", width=8)
        table.add_column("Error", width=20)
        platform_name = "cli"
        for task in tasks_dict.values():
            row = format_task_row(task, platform_name)
            table.add_row(
                row["folder"], str(row["status"]), row["step"], str(row["progress"]),
                row["worker"], row["backend"], row["duration"], row["error"]
            )
        return table
    
    def _create_progress_bar(self, progress: float) -> str:
        """Create a simple text progress bar"""
        width = 20
        filled = int(progress / 100 * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}]"
    
    # Task Management Commands
    
    def cancel_all_tasks(self):
        """Cancel all active tasks"""
        if not self.task_monitor:
            self.console.print("❌ No task monitor available", style="red")
            return
        
        cancelled_count = self.task_monitor.cancel_all_tasks()
        if cancelled_count > 0:
            self.console.print(f"✅ Cancelled {cancelled_count} tasks", style="green")
        else:
            self.console.print("ℹ️ No tasks to cancel", style="blue")
    
    def flush_backend(self):
        """Flush backend"""
        if not self.task_monitor:
            self.console.print("❌ No task monitor available", style="red")
            return
        
        success = self.task_monitor.flush_backend()
        if success:
            self.console.print("✅ Backend flushed successfully", style="green")
        else:
            self.console.print("❌ Failed to flush backend", style="red")
    
    def restart_backend(self):
        """Restart backend"""
        if not self.task_monitor:
            self.console.print("❌ No task monitor available", style="red")
            return
        
        self.console.print("🔄 Restarting backend...", style="yellow")
        success = self.task_monitor.restart_backend()
        if success:
            self.console.print("✅ Backend restarted successfully", style="green")
        else:
            self.console.print("❌ Failed to restart backend", style="red")
    
    def reset_monitor(self):
        """Reset task monitor and clear history"""
        if not self.task_monitor:
            self.console.print("❌ No task monitor available", style="red")
            return
        
        self.console.print("🧹 Resetting task monitor...", style="yellow")
        self.task_monitor.reset()
        self.console.print("✅ Task monitor reset successfully", style="green")
    
    def clear_history(self):
        """Clear old task history"""
        if not self.task_monitor:
            self.console.print("❌ No task monitor available", style="red")
            return
        
        self.console.print("🧹 Clearing old task history...", style="yellow")
        self.task_monitor.clear_all_history()
        self.console.print("✅ Task history cleared successfully", style="green")
    
    def show_backend_info(self):
        """Show detailed backend information"""
        if not self.task_monitor:
            self.console.print("❌ No task monitor available", style="red")
            return
        
        backend_info = self.task_monitor.get_backend_info()
        
        info_text = f"""
Backend: {backend_info.get('backend_name', 'Unknown')}
Status: {backend_info.get('status', 'Unknown')}
Initialized: {'✅' if backend_info.get('is_initialized') else '❌'}
Timestamp: {backend_info.get('timestamp', 'Unknown')}
        """
        
        if 'error' in backend_info:
            info_text += f"Error: {backend_info['error']}\n"
        
        panel = Panel(info_text.strip(), title="Backend Information", border_style="blue")
        self.console.print(panel)


# Convenience functions for CLI integration

def show_task_progress(task_id: str, task_monitor: TaskMonitor, console: Console = None):
    """Show progress for a single task"""
    display = CLITaskDisplay(console, task_monitor)
    display.show_task_progress(task_id)

def show_activity_monitor(task_monitor: TaskMonitor, console: Console = None, live: bool = False):
    """Show activity monitor"""
    display = CLITaskDisplay(console, task_monitor)
    display.show_all_tasks(live_updates=live)

def cancel_all_tasks(task_monitor: TaskMonitor, console: Console = None):
    """Cancel all tasks"""
    display = CLITaskDisplay(console, task_monitor)
    display.cancel_all_tasks()

def flush_backend(task_monitor: TaskMonitor, console: Console = None):
    """Flush backend"""
    display = CLITaskDisplay(console, task_monitor)
    display.flush_backend()

def restart_backend(task_monitor: TaskMonitor, console: Console = None):
    """Restart backend"""
    display = CLITaskDisplay(console, task_monitor)
    display.restart_backend()

def reset_monitor(task_monitor: TaskMonitor, console: Console = None):
    """Reset task monitor"""
    display = CLITaskDisplay(console, task_monitor)
    display.reset_monitor()

def clear_history(task_monitor: TaskMonitor, console: Console = None):
    """Clear task history"""
    display = CLITaskDisplay(console, task_monitor)
    display.clear_history()

def format_task_row(task, platform_name=None):
    if platform_name is None:
        platform_name = platform.system().lower()
    is_macos = platform_name == "darwin"

    # Spinner/Status
    if task.status == "running":
        status_widget = "⏳"
    elif task.status == "pending":
        status_widget = "○"
    elif task.status == "completed":
        status_widget = "●"
    elif task.status == "failed":
        status_widget = "✗"
    elif task.status == "cancelled":
        status_widget = "⏹"
    else:
        status_widget = "?"

    # Step progress
    step_info = f"{task.current_step or 'Waiting'} ({task.completed_steps}/{task.total_steps})"
    # Progress
    progress_widget = f"{task.overall_progress:.0f}%"
    # Worker
    worker_display = f"{task.executor_type.upper()} {task.worker}"
    # Backend
    backend = task.executor_type.capitalize()
    # Duration
    duration = f"{task.duration.total_seconds()/60:.1f}m"
    # Error
    error = task.error_message if task.status == "failed" else ""

    return {
        "folder": task.folder_name,
        "status": status_widget,
        "step": step_info,
        "progress": progress_widget,
        "worker": worker_display,
        "backend": backend,
        "duration": duration,
        "error": error,
        "task_id": task.task_id,  # for selection/cancellation
    } 