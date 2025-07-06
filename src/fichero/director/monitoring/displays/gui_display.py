"""
GUI Task Display System

Single GUITaskDisplay class for both document progress and activity monitoring.
Works like CLITaskDisplay but with Toga widgets instead of Rich formatting.

Supports two modes:
- Document Window Mode: Shows tasks for specific document
- Activity Monitor Mode: Shows all tasks across all documents

Refactored July 6, 2025 to combine Activity Monitor and Document Window display, to share code with CLI via task_monitor.py, and to remove redundant code.
"""

import asyncio
import logging
from typing import Optional, List, Dict

try:
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN, ROW
    from toga.sources import ListSource
    TOGA_AVAILABLE = True
except ImportError:
    TOGA_AVAILABLE = False

from ..task_monitor import TaskMonitor

logger = logging.getLogger(__name__)


class GUITaskDisplay:
    """
    GUI task display using Toga widgets.
    
    Thin presentation layer that reads from TaskMonitor and formats
    the data for GUI display with document filtering capability.
    """
    
    def __init__(self, task_monitor: TaskMonitor, filter_document_id: Optional[str] = None):
        """
        Initialize GUI display.
        
        Args:
            task_monitor: TaskMonitor instance to read data from
            filter_document_id: Optional document ID to filter tasks
        """
        if not TOGA_AVAILABLE:
            raise ImportError("Toga is required for GUI displays")
        
        self.task_monitor = task_monitor
        self.filter_document_id = filter_document_id
        self.is_monitoring = False
        self.refresh_task = None
        
        # Track current table data for efficient updates
        self._current_data = []
        
        self._create_ui()
    
    def _create_ui(self):
        """Create UI components: status bar, task table, and stop button."""
        
        # Status bar
        self.status_label = toga.Label(
            text="Ready",
            style=Pack(padding=(5, 10), text_align="center")
        )
        
        # Task table
        self.list_source = ListSource(accessors=['folder', 'status'], data=[])
        self.table = toga.Table(
            headings=['Folder', 'Status'],
            data=self.list_source,
            style=Pack(flex=1)
        )
        
        # Context-aware stop button
        if self.filter_document_id:
            button_text = "Stop Document Tasks"
        else:
            button_text = "Stop All Tasks"
        
        self.stop_button = toga.Button(
            text=button_text,
            on_press=self._stop_tasks,
            style=Pack(padding=5)
        )
        
        # Layout containers
        bottom_box = toga.Box(
            children=[self.stop_button, self.status_label],
            style=Pack(direction=ROW, padding=5)
        )
        
        self.container = toga.Box(
            children=[
                self.table,
                bottom_box
            ],
            style=Pack(direction=COLUMN, flex=1)
        )
    
    def start_monitoring(self):
        """Start auto-refresh monitoring for real-time updates."""
        if not self.is_monitoring:
            self.is_monitoring = True
            self.refresh_task = asyncio.create_task(self._auto_refresh_loop())
    
    def stop_monitoring(self):
        """Stop auto-refresh monitoring and clean up resources."""
        if self.is_monitoring:
            self.is_monitoring = False
            if self.refresh_task:
                self.refresh_task.cancel()
                self.refresh_task = None
    
    async def _auto_refresh_loop(self):
        """Background auto-refresh loop that updates display every 0.5 seconds."""
        try:
            while self.is_monitoring:
                self._update_display()
                await asyncio.sleep(0.5)  # 0.5s refresh for smooth spinner animations
        except asyncio.CancelledError:
            # Normal cancellation when monitoring stops
            pass
        except Exception as e:
            logger.error(f"Error in GUI auto-refresh loop: {e}")
            self.is_monitoring = False
    
    def _update_display(self):
        """Update display with current task data from TaskMonitor."""
        try:
            # Get fresh data from TaskMonitor
            display_data = self.task_monitor.create_display_data(self.filter_document_id)
            
            # WORKAROUND: If document filtering returns no tasks, also try getting all tasks
            # This handles the case where document_id isn't properly propagated to tasks
            if self.filter_document_id and len(display_data) == 0:
                display_data = self.task_monitor.create_display_data(None)
            
            # Update table only if data has changed (efficiency check)
            if display_data != self._current_data:
                self._update_table_data(display_data)
                self._current_data = display_data.copy()
            
            # Update status summary
            status_text = self.task_monitor.get_status_summary(self.filter_document_id)
            if self.filter_document_id and "No active tasks" in status_text:
                status_text = self.task_monitor.get_status_summary(None)
            self.status_label.text = status_text
            
        except Exception as e:
            logger.error(f"Error updating GUI display: {e}")
            self.status_label.text = "Display error"
    
    def _update_table_data(self, new_data: List[Dict[str, str]]):
        """Update table data using proper ListSource clear() + append() pattern."""
        try:
            # Clear existing data
            self.list_source.clear()
            
            # Add new data
            if not new_data:
                self.list_source.append({
                    'folder': 'No tasks to display',
                    'status': ''
                })
            else:
                for row_data in new_data:
                    self.list_source.append({
                        'folder': row_data.get('folder', ''),
                        'status': row_data.get('status', '')
                    })
            
        except Exception as e:
            logger.error(f"Error updating table data: {e}")
    
    def _stop_tasks(self, widget):
        """Context-aware stop tasks button handler."""
        try:
            if self.filter_document_id:
                # Stop only tasks from this document
                tasks = self.task_monitor.get_tasks_by_document(self.filter_document_id)
                for task_id in tasks.keys():
                    self.task_monitor.cancel_task(task_id)
            else:
                # Stop all tasks
                self.task_monitor.cancel_all_tasks()
            
            # Update display immediately
            self._update_display()
            
        except Exception as e:
            logger.error(f"Error stopping tasks: {e}")