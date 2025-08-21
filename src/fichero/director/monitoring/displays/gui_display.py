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

from fichero.director.monitoring.task_monitor import TaskMonitor
import gettext

logger = logging.getLogger(__name__)


class GUITaskDisplay:
    """
    GUI task display using Toga widgets.
    
    Thin presentation layer that reads from TaskMonitor and formats
    the data for GUI display with document filtering capability.
    
    Platform-aware: Uses DetailedList on iOS, Table on other platforms.
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
        self._current_rows = {}  # Track rows by task ID for efficient updates
        
        # Platform detection for widget choice
        self._detect_platform()
        
        self._create_ui()
    
    def _detect_platform(self):
        """Detect platform to choose appropriate widget type"""
        try:
            # First check debug constants for manual override
            try:
                from fichero.config.debug_constants import get_debug_platform_override
                debug_platform = get_debug_platform_override()
                if debug_platform:
                    self.is_ios = debug_platform == 'ios'
                    logger.debug(f"Using debug platform override: {debug_platform}, using {'DetailedList' if self.is_ios else 'Table'}")
                    return
            except ImportError:
                pass  # Debug constants not available, fall back to platform detection
            
            # Use actual platform detection
            import toga.platform
            current_platform = toga.platform.current_platform
            self.is_ios = current_platform == 'iOS'
            logger.debug(f"Detected platform: {current_platform}, using {'DetailedList' if self.is_ios else 'Table'}")
        except Exception:
            # Fallback to non-iOS if platform detection fails
            self.is_ios = False
            logger.warning("Platform detection failed, defaulting to Table widget")
    
    def _create_ui(self):
        """Create UI components: status bar, task table, and stop button."""
        # Status label
        self.status_label = toga.Label(
            _("task_table_loading"),
            style=Pack(margin=5, font_size=10)
        )
        
        # Task display - platform-aware widget choice
        if self.is_ios:
            # iOS: Use DetailedList with structured data
            self.list_source = ListSource(
                accessors=['icon', 'title', 'subtitle'],
                data=[]
            )
            self.task_display = toga.DetailedList(
                data=self.list_source,
                style=Pack(flex=1),
                on_select=self._on_task_select
            )
        else:
            # Desktop: Use Table with columns
            self.list_source = ListSource(
                accessors=['folder', 'status'],
                data=[]
            )
            self.task_display = toga.Table(
                headings=['Folder', 'Status'],
                data=self.list_source,
                style=Pack(flex=1)
            )
        
        # Context-aware stop button
        button_text = _("task_button_stop_document") if self.filter_document_id else _("task_button_stop_all")
        
        self.stop_button = toga.Button(
            text=button_text,
            on_press=self._stop_tasks,
            style=Pack(margin=5)
        )
        
        # Layout containers
        bottom_box = toga.Box(
            children=[self.stop_button, self.status_label],
            style=Pack(direction=ROW, margin=5)
        )
        
        self.container = toga.Box(
            children=[
                self.task_display,
                bottom_box
            ],
            style=Pack(direction=COLUMN, flex=1)
        )
    
    def _on_task_select(self, widget, **kwargs):
        """Handle task selection in DetailedList (iOS)"""
        if self.is_ios and hasattr(widget, 'selection') and widget.selection:
            selected_task = widget.selection
            logger.debug(f"Task selected on iOS: {selected_task.title}")
            # Could add task details popup or other iOS-specific behavior here
    
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
                self._update_display_data(display_data)
                self._current_data = display_data.copy()
            
            # Update status summary
            status_text = self.task_monitor.get_status_summary(self.filter_document_id)
            if self.filter_document_id and _("task_table_no_active") in status_text:
                status_text = self.task_monitor.get_status_summary(None)
            self.status_label.text = status_text
            
        except Exception as e:
            logger.error(f"Error updating GUI display: {e}")
            self.status_label.text = _("task_table_error")
    
    def _update_display_data(self, new_data: List[Dict[str, str]]):
        """Update display data efficiently by adding/removing/updating individual rows."""
        try:
            # Create a mapping of new data by task ID (using folder name as proxy for task ID)
            new_data_map = {}
            for row_data in new_data:
                folder = row_data.get('folder', '')
                new_data_map[folder] = row_data
            
            # Find tasks to add (new tasks)
            tasks_to_add = []
            for folder, row_data in new_data_map.items():
                if folder not in self._current_rows:
                    tasks_to_add.append(row_data)
            
            # Find tasks to remove (completed/removed tasks)
            tasks_to_remove = []
            for folder in list(self._current_rows.keys()):
                if folder not in new_data_map:
                    tasks_to_remove.append(folder)
            
            # Find tasks to update (status changes)
            tasks_to_update = []
            for folder, row_data in new_data_map.items():
                if folder in self._current_rows:
                    current_row = self._current_rows[folder]
                    if self.is_ios:
                        # iOS: Check DetailedList data structure
                        if (current_row.title != row_data.get('folder', '') or 
                            current_row.subtitle != row_data.get('status', '')):
                            tasks_to_update.append((folder, row_data))
                    else:
                        # Desktop: Check Table data structure
                        if (current_row.folder != row_data.get('folder', '') or 
                            current_row.status != row_data.get('status', '')):
                            tasks_to_update.append((folder, row_data))
            
            # Handle empty state
            if not new_data:
                if self._current_rows:  # Only clear if we have data
                    self.list_source.clear()
                    self._current_rows.clear()
                if not any(self.list_source):  # Only add if display is empty
                    if self.is_ios:
                        self.list_source.append({
                            'icon': '○',
                            'title': _("task_table_empty"),
                            'subtitle': ''
                        })
                    else:
                        self.list_source.append({
                            'folder': _("task_table_empty"),
                            'status': ''
                        })
                return
            
            # Remove completed/removed tasks
            for folder in tasks_to_remove:
                if folder in self._current_rows:
                    row = self._current_rows[folder]
                    try:
                        self.list_source.remove(row)
                    except ValueError:
                        pass  # Row might already be removed
                    del self._current_rows[folder]
            
            # Update existing tasks (status changes)
            for folder, row_data in tasks_to_update:
                if folder in self._current_rows:
                    row = self._current_rows[folder]
                    if self.is_ios:
                        # iOS: Update DetailedList data
                        row.title = row_data.get('folder', '')
                        row.subtitle = row_data.get('status', '')
                    else:
                        # Desktop: Update Table data
                        row.folder = row_data.get('folder', '')
                        row.status = row_data.get('status', '')
            
            # Add new tasks
            for row_data in tasks_to_add:
                if self.is_ios:
                    # iOS: Create DetailedList data structure
                    new_row = self.list_source.append({
                        'icon': self._get_status_icon(row_data.get('status', '')),
                        'title': row_data.get('folder', ''),
                        'subtitle': row_data.get('status', '')
                    })
                else:
                    # Desktop: Create Table data structure
                    new_row = self.list_source.append({
                        'folder': row_data.get('folder', ''),
                        'status': row_data.get('status', '')
                    })
                
                # Track the new row
                folder = row_data.get('folder', '')
                self._current_rows[folder] = new_row
            
        except Exception as e:
            logger.error(f"Error updating display data: {e}")
            # Fallback to simple clear/rebuild if efficient update fails
            self.list_source.clear()
            self._current_rows.clear()
            if not new_data:
                if self.is_ios:
                    self.list_source.append({
                        'icon': '○',
                        'title': _("task_table_empty"),
                        'subtitle': ''
                    })
                else:
                    self.list_source.append({
                        'folder': _("task_table_empty"),
                        'status': ''
                    })
            else:
                for row_data in new_data:
                    if self.is_ios:
                        new_row = self.list_source.append({
                            'icon': self._get_status_icon(row_data.get('status', '')),
                            'title': row_data.get('folder', ''),
                            'subtitle': row_data.get('status', '')
                        })
                    else:
                        new_row = self.list_source.append({
                            'folder': row_data.get('folder', ''),
                            'status': row_data.get('status', '')
                        })
                    
                    folder = row_data.get('folder', '')
                    self._current_rows[folder] = new_row
    
    def _get_status_icon(self, status_text: str) -> str:
        """Extract status icon from status text for iOS DetailedList"""
        if status_text.startswith('✓'):
            return '✓'
        elif status_text.startswith('✗'):
            return '✗'
        elif status_text.startswith('■'):
            return '■'
        elif status_text.startswith('○'):
            return '○'
        elif '🔄' in status_text or '⏳' in status_text:
            return '🔄'
        else:
            return '○'  # Default icon
    
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