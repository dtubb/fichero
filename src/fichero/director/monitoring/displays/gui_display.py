"""
GUI Task Displays

Toga-based displays for task monitoring.
Provides both Activity Monitor window and document progress widgets.
"""

import asyncio
import logging
import platform
from typing import Optional, Dict, List, Callable
from datetime import datetime
from pathlib import Path
import io

try:
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN, ROW, CENTER
    TOGA_AVAILABLE = True
except ImportError:
    TOGA_AVAILABLE = False

from ..task_monitor import TaskMonitor, TaskInfo
from fichero.utils.text_spinner import get_spinner_frame, get_progress_bar

logger = logging.getLogger(__name__)


def get_status_icon(status: str, worker: str = "", progress: float = 0) -> str:
    """
    Get status icon with text spinner for running tasks, using task monitor's base icons.
    
    Args:
        status: Task status (pending, running, submitted, processing, completed, failed, cancelled)
        worker: Worker type (cpu, io) for running tasks
        progress: Progress percentage (0-100)
    
    Returns:
        Status string with appropriate indicator
    """
    # Debug logging
    logger.debug(f"get_status_icon called with status='{status}', worker='{worker}', progress={progress}")
    
    if status in ("running", "active", "submitted", "processing"):
        # Use text spinner for running tasks
        spinner = get_spinner_frame('circle')
        if progress > 0:
            return f"{spinner} {progress:.0f}%"
        else:
            return f"{spinner} Running"
    else:
        # For non-running tasks, use the task monitor's status icon
        # We'll get this from the task object instead of duplicating the logic
        return "○"  # Default fallback


def get_worker_display_name(worker: str, executor_type: str = "") -> str:
    """
    Get human-readable worker display name.
    
    Args:
        worker: Worker identifier
        executor_type: Type of executor (cpu, io, celery)
    
    Returns:
        Human-readable worker name
    """
    if not worker or worker == "unknown":
        return "Unknown"
    
    # Handle different worker formats
    if worker.startswith("CPU-"):
        return f"CPU Thread {worker[4:]}"
    elif worker.startswith("IO-"):
        return f"IO Thread {worker[3:]}"
    elif worker.startswith("celery"):
        return f"Celery Worker {worker[7:]}"
    elif executor_type == "cpu":
        return f"CPU Thread {worker}"
    elif executor_type == "io":
        return f"IO Thread {worker}"
    else:
        return worker


class DocumentContentDisplay:
    """
    Central content display for document windows.
    Handles both description view (initial) and progress view (processing).
    """
    
    def __init__(self, document_window, document_id: str):
        if not TOGA_AVAILABLE:
            raise ImportError("Toga is required for GUI content display")
        
        self.document_window = document_window
        self.document_id = document_id
        
        # Content containers
        self.content_section = None
        self.description_canvas = None
        self.progress_display = None
        
        # State
        self.is_showing_progress = False
        self.link_areas = []
        
        # Initialize content
        self._create_content_section()
        self._show_description_view()
        
        logger.info(f"DocumentContentDisplay initialized for document: {document_id}")
    
    def _create_content_section(self):
        """Create the main content section"""
        self.content_section = toga.Box(
            style=Pack(direction=COLUMN, margin=(0, 0, 0, 0), flex=1)
        )
    
    def _show_description_view(self):
        """Show the description view with markdown content"""
        if self.is_showing_progress:
            return
        
        # Create description canvas
        self.description_canvas = toga.Canvas(
            style=Pack(
                margin_top=20,
                margin_right=20,
                margin_bottom=10,
                margin_left=20,
                flex=1,
            ),
            on_resize=self._draw_content_text,
            on_press=self._handle_canvas_click
        )
        
        # Clear and add description
        self.content_section.clear()
        self.content_section.add(self.description_canvas)
        self._draw_content_text()
    
    def _draw_content_text(self, canvas=None, **kwargs):
        """Draw description content on canvas"""
        if canvas is None:
            canvas = self.description_canvas
        
        # Clear and draw
        with canvas.context.Fill(color='rgb(255, 255, 255)') as clear_fill:
            clear_fill.rect(0, 0, canvas.layout.content_width, canvas.layout.content_height)
        
        self._draw_rounded_background(canvas)
        self._draw_description_content(canvas)
    
    def _draw_rounded_background(self, canvas):
        """Draw rounded white background"""
        width = canvas.layout.content_width
        height = canvas.layout.content_height
        corner_radius = 6
        
        # Light gray background to show rounded corners
        with canvas.context.Fill(color='rgb(240, 240, 240)') as full_background:
            full_background.rect(0, 0, width, height)
        
        # White rounded rectangle
        with canvas.context.Fill(color='rgb(255, 255, 255)') as background:
            background.begin_path()
            background.move_to(corner_radius, 0)
            background.line_to(width - corner_radius, 0)
            background.arc(width - corner_radius, corner_radius, corner_radius, -1.5708, 0)
            background.line_to(width, height - corner_radius)
            background.arc(width - corner_radius, height - corner_radius, corner_radius, 0, 1.5708)
            background.line_to(corner_radius, height)
            background.arc(corner_radius, height - corner_radius, corner_radius, 1.5708, 3.14159)
            background.line_to(0, corner_radius)
            background.arc(corner_radius, corner_radius, corner_radius, 3.14159, 4.71239)
            background.close_path()
    
    def _draw_description_content(self, canvas):
        """Draw description text with markdown support"""
        self.link_areas = []
        
        regular_font = toga.Font(family=toga.fonts.SYSTEM, size=10, weight="light")
        bold_font = toga.Font(family=toga.fonts.SYSTEM, size=10, weight="bold")
        
        # Import i18n for translation
        from fichero.ui.i18n import _
        text = _("description")
        
        line_height_multiplier = 1.8
        left_margin = 15
        top_margin = 15
        right_margin = 10
        max_width = canvas.layout.content_width - left_margin - right_margin
        
        paragraphs = text.split('\n\n')
        current_y = top_margin
        
        for paragraph_idx, paragraph in enumerate(paragraphs):
            if paragraph_idx > 0:
                current_y += regular_font.size * line_height_multiplier * 0.8
            
            current_y = self._render_paragraph(canvas, paragraph, left_margin, current_y, 
                                             max_width, regular_font, bold_font, line_height_multiplier)
    
    def _render_paragraph(self, canvas, text, left_margin, start_y, max_width, 
                          regular_font, bold_font, line_height_multiplier):
        """Render paragraph with markdown formatting"""
        import re
        
        elements = []
        current_pos = 0
        
        # Parse markdown
        bold_pattern = r'\*([^*]+)\*'
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        combined_pattern = f'({bold_pattern})|({link_pattern})'
        
        for match in re.finditer(combined_pattern, text):
            if match.start() > current_pos:
                elements.append({
                    'type': 'text',
                    'content': text[current_pos:match.start()],
                    'font': regular_font,
                    'color': 'black'
                })
            
            if match.group(2):  # Bold
                elements.append({
                    'type': 'text',
                    'content': match.group(2),
                    'font': bold_font,
                    'color': 'black'
                })
            elif match.group(4) and match.group(5):  # Link
                elements.append({
                    'type': 'link',
                    'content': match.group(4),
                    'url': match.group(5),
                    'font': regular_font,
                    'color': 'blue'
                })
            
            current_pos = match.end()
        
        if current_pos < len(text):
            elements.append({
                'type': 'text',
                'content': text[current_pos:],
                'font': regular_font,
                'color': 'black'
            })
        
        # Render with word wrapping
        current_y = start_y
        current_line_elements = []
        current_line_width = 0
        
        for element in elements:
            words = element['content'].split()
            
            for word_idx, word in enumerate(words):
                space_prefix = " " if word_idx > 0 or current_line_elements else ""
                test_word = space_prefix + word
                
                word_width, _ = canvas.measure_text(test_word, element['font'])
                
                if current_line_width + word_width <= max_width:
                    current_line_elements.append({
                        **element,
                        'content': test_word,
                        'width': word_width
                    })
                    current_line_width += word_width
                else:
                    if current_line_elements:
                        current_y = self._render_line(canvas, current_line_elements, 
                                                    left_margin, current_y, line_height_multiplier)
                    
                    current_line_elements = [{
                        **element,
                        'content': word,
                        'width': canvas.measure_text(word, element['font'])[0]
                    }]
                    current_line_width = current_line_elements[0]['width']
        
        if current_line_elements:
            current_y = self._render_line(canvas, current_line_elements, 
                                        left_margin, current_y, line_height_multiplier)
        
        return current_y
    
    def _render_line(self, canvas, elements, left_margin, y_position, line_height_multiplier):
        """Render a line of formatted text elements"""
        current_x = left_margin
        
        for element in elements:
            color = 'rgb(0, 100, 200)' if element['color'] == 'blue' else 'rgb(0, 0, 0)'
            
            with canvas.context.Fill(color=color) as fill_context:
                    fill_context.write_text(
                        element['content'],
                        current_x,
                        y_position,
                        element['font'],
                        toga.constants.Baseline.TOP
                    )
            
            # Track link areas
            if element['type'] == 'link':
                self.link_areas.append({
                    'x': current_x,
                    'y': y_position,
                    'width': element['width'],
                    'height': element['font'].size,
                    'url': element['url']
                })
            
            current_x += element['width']
        
        return y_position + elements[0]['font'].size * line_height_multiplier
    
    def _handle_canvas_click(self, widget, x, y, **kwargs):
        """Handle clicks on description canvas for links"""
        import webbrowser
        for link_area in self.link_areas:
            if (link_area['x'] <= x <= link_area['x'] + link_area['width'] and
                link_area['y'] <= y <= link_area['y'] + link_area['height']):
                webbrowser.open(link_area['url'])
                break
    
    def show_progress_view(self, task_ids: List[str], folders: List[Path]):
        """Switch to progress view"""
        self.is_showing_progress = True
        
        # Create progress display
        if not self.progress_display:
            self.progress_display = DocumentProgressDisplay(self.document_window, self.document_id)
        
        # Start progress display
        self.progress_display.start_processing(task_ids, folders)
        
        # Replace content
        self.content_section.clear()
        self.content_section.add(self.progress_display.progress_container)
    
    def show_description_view(self):
        """Return to description view"""
        self.is_showing_progress = False
        self._show_description_view()
    
    def get_content_section(self):
        """Get the content section for the document window"""
        return self.content_section


class DocumentProgressDisplay:
    """
    Progress display for document windows.
    Shows progress for tasks from a specific document using a tree-based layout.
    """
    
    def __init__(self, document_window, document_id: str):
        if not TOGA_AVAILABLE:
            raise ImportError("Toga is required for GUI progress display")
        
        self.document_window = document_window
        self.document_id = document_id
        self.task_monitor = TaskMonitor.get_instance(document_window._app.director, f"gui_doc_{document_id}")
        
        # UI state
        self.progress_container = None
        self.task_table = None
        self.status_bar = None
        self.button_bar = None
        self.is_showing_progress = False
        
        # Auto-refresh for progress updates
        self.auto_refresh_task: Optional[asyncio.Task] = None
        self.current_task_ids = []
        
        # Register for task updates
        self.task_monitor.register_callback(self._on_task_update)
        
        logger.info(f"DocumentProgressDisplay initialized for document: {document_id}")
    
    def start_processing(self, task_ids: List[str], folders: List[Path]):
        """Start progress display for processing tasks"""
        try:
            # Create progress view
            self._create_progress_view()
            
            # Monitor the specific tasks
            self.current_task_ids = task_ids
            
            # Mark as showing progress
            self.is_showing_progress = True
            
            # Start auto-refresh loop for progress updates
            self._start_auto_refresh()
            
            logger.info(f"Started progress display for {len(task_ids)} tasks")
            
        except Exception as e:
            logger.error(f"Failed to start progress display: {e}")
    
    def stop_processing(self):
        """Stop progress display and cleanup"""
        self._stop_auto_refresh()
        self.current_task_ids = []
        self.is_showing_progress = False
        logger.info("Stopped progress display")
    
    def _create_progress_view(self):
        """Create progress view with simplified layout - only essential info"""
        if not self.is_showing_progress:
            self.is_showing_progress = True
            
            self.progress_container = toga.Box(style=Pack(direction=COLUMN, margin=3, flex=1))
            self.task_table = toga.Table(
                headings=["Folder", "Status", "Progress"],
                accessors=["folder", "status", "progress"],
                style=Pack(flex=1, margin=0),
                missing_value="",
                on_select=self._on_task_select
            )
            try:
                self.task_table.column_widths = [200, 150, 100]  # Wider columns for essential info
            except AttributeError:
                pass
            self.progress_container.add(self.task_table)
            
            # Bottom bar: button first, then status text
            bottom_bar = toga.Box(style=Pack(direction=ROW, margin=(5, 10, 0, 0)))
            self.button_bar = self._create_button_bar()
            bottom_bar.add(self.button_bar)
            self.status_bar = toga.Label(
                "Ready to process",
                style=Pack(font_size=10, color="#666666", margin_left=3)
            )
            bottom_bar.add(self.status_bar)
            spacer = toga.Box(style=Pack(flex=1))
            bottom_bar.add(spacer)
            self.progress_container.add(bottom_bar)
    
    def _create_button_bar(self):
        """Create compact button bar for document progress with only Stop"""
        button_box = toga.Box(style=Pack(direction=ROW), margin=(0, 0 ,0, 0))
        stop_btn = toga.Button(
            "■",
            on_press=self._stop_processing_handler,
            style=Pack(margin=(3, 3), font_size=9)
        )
        button_box.add(stop_btn)
        return button_box
    
    def _on_task_select(self, widget):
        """Handle task selection"""
        selection = widget.selection
        if selection:
            # Update status bar with task details
            folder = getattr(selection, 'folder', 'Unknown')
            status = getattr(selection, 'status', 'Unknown')
            progress = getattr(selection, 'progress', '')
            
            status_text = f"Selected: {folder} ({status})"
            if progress:
                status_text += f" - Progress: {progress}"
            
            self.status_bar.text = status_text
        else:
            self.status_bar.text = "No task selected"
    
    def _stop_processing_handler(self, widget):
        """Handle stop processing button"""
        try:
            # Cancel only selected tasks
            selected = self.task_table.selection
            cancelled_count = 0
            if selected:
                if isinstance(selected, list):
                    selected_tasks = selected
                else:
                    selected_tasks = [selected]
                for row in selected_tasks:
                    task_id = getattr(row, "task_id", None)
                    if task_id and self.task_monitor.cancel_task(task_id):
                        cancelled_count += 1
            self.status_bar.text = f"Stopped {cancelled_count} tasks"
            
            # Reset document window button state
            self.document_window._reset_to_process_button()
            
            # Return to main view
            if hasattr(self.document_window, 'content_display'):
                self.document_window.content_display.show_description_view()
                
        except Exception as e:
            self.status_bar.text = f"Error stopping processing: {e}"
    
    def _on_task_update(self, event_type: str, task: TaskInfo):
        """Handle task updates from TaskMonitor"""
        try:
            # Only handle tasks from this document
            if task.document_id != self.document_id:
                return
            
            # Update progress UI
            asyncio.create_task(self._update_progress_ui(task))
            
            # Handle completion
            if event_type == 'task_completed':
                asyncio.create_task(self._handle_task_completion(task))
                
        except Exception as e:
            logger.error(f"Error handling task update: {e}")
    
    async def _update_progress_ui(self, task: TaskInfo):
        """Update progress UI for a task"""
        try:
            # Update the task table
            self._update_task_table()
            
            # Update status bar with overall progress
            self._update_status_bar()
                    
        except Exception as e:
            logger.error(f"Error updating progress UI: {e}")
    
    def _update_task_table(self):
        """Update the task table with current document tasks - optimized to update existing items"""
        if not self.task_table:
            return
        
        platform_name = platform.system().lower()
        document_tasks = self.task_monitor.get_tasks_by_document(self.document_id)
        table_data = [format_task_row(task, platform_name) for task in document_tasks.values()]
        self.task_table.data = table_data
    
    def _update_status_bar(self):
        """Update status bar with simplified statistics - only essential info"""
        if not self.status_bar:
            return
        
        try:
            # Get backend info
            backend_info = self.task_monitor.get_backend_info()
            backend_name = backend_info.get('backend_name', 'Unknown')
            
            # Get statistics
            stats = self.task_monitor.get_session_stats()
            active_count = stats['active_tasks']
            
            # Simple status text - only show what matters
            if active_count > 0:
                status_text = f"Processing {active_count} folder{'s' if active_count != 1 else ''}"
            else:
                status_text = f"Ready ({backend_name})"
            
            self.status_bar.text = status_text
            
        except Exception as e:
            self.status_bar.text = f"Error updating status: {e}"
    
    async def _handle_task_completion(self, task: TaskInfo):
        """Handle task completion"""
        try:
            # Check if all tasks for this document are complete
            document_tasks = self.task_monitor.get_tasks_by_document(self.document_id)
            active_tasks = [t for t in document_tasks.values() if t.is_active]
            
            if not active_tasks:
                # All tasks completed - gather results
                completed_tasks = [t for t in document_tasks.values() if t.status == "completed"]
                failed_tasks = [t for t in document_tasks.values() if t.status == "failed"]
                
                # Stop activity indicator and reset button
                self.document_window.activity_indicator.stop()
                self.document_window.process_btn.enabled = True
                self.document_window.process_btn.text = "Process"
                # Reset button style
                if hasattr(self.document_window.process_btn.style, 'background_color'):
                    del self.document_window.process_btn.style.background_color
                if hasattr(self.document_window.process_btn.style, 'color'):
                    del self.document_window.process_btn.style.color
                
                # Update status bar with completion message
                total_tasks = len(document_tasks)
                success_rate = len(completed_tasks) / total_tasks if total_tasks > 0 else 0
                
                if len(failed_tasks) == 0:
                    self.status_bar.text = f"✅ All {total_tasks} tasks completed successfully!"
                elif success_rate >= 0.8:
                    self.status_bar.text = f"✅ {len(completed_tasks)}/{total_tasks} tasks completed ({len(failed_tasks)} failed)"
                else:
                    self.status_bar.text = f"⚠️ {len(completed_tasks)}/{total_tasks} tasks completed ({len(failed_tasks)} failed)"
                    
        except Exception as e:
            logger.error(f"Error handling task completion: {e}")
    
    def _start_auto_refresh(self):
        """Start auto-refresh task for progress updates"""
        if not self.auto_refresh_task:
            self.auto_refresh_task = asyncio.create_task(self._auto_refresh_loop())
            logger.debug("Started auto-refresh for document progress")
    
    def _stop_auto_refresh(self):
        """Stop auto-refresh task"""
        if self.auto_refresh_task:
            self.auto_refresh_task.cancel()
            self.auto_refresh_task = None
            logger.debug("Stopped auto-refresh for document progress")
    
    async def _auto_refresh_loop(self):
        """Auto-refresh loop for progress updates"""
        try:
            while True:
                logger.debug("Auto-refresh: updating task table and status bar")
                await self._refresh_all_tasks()
                await asyncio.sleep(0.1)  # Update every 0.1 seconds for smooth spinner
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Auto-refresh error in document progress: {e}")
    
    async def _refresh_all_tasks(self):
        """Refresh progress for all current tasks"""
        try:
            if not self.current_task_ids or not self.is_showing_progress:
                return
            
            # Update the task table
            self._update_task_table()
            
            # Update status bar
            self._update_status_bar()
            
        except Exception as e:
            logger.error(f"Error refreshing tasks: {e}", exc_info=True)


class ActivityMonitorDisplay:
    """
    Activity Monitor display for system-wide task monitoring.
    Shows all tasks across all document windows and CLI instances.
    Uses a tree-based layout similar to macOS Finder.
    """
    
    def __init__(self, app):
        if not TOGA_AVAILABLE:
            raise ImportError("Toga is required for GUI Activity Monitor")
        
        self.app = app
        self.task_monitor = TaskMonitor.get_instance(app.director, "gui_activity_monitor")
        self.window: Optional[toga.Window] = None
        self.is_visible = False
        self.auto_refresh_task: Optional[asyncio.Task] = None
        
        # UI components
        self.task_table = None
        self.status_bar = None
        self.button_bar = None
        
        logger.info("ActivityMonitorDisplay initialized")
    
    def show(self):
        """Show the activity monitor window"""
        if self.window is None:
            self._create_window()
        
        if not self.is_visible:
            self.window.show()
            self.is_visible = True
            self._start_auto_refresh()
            logger.info("Activity monitor display shown")
    
    def hide(self):
        """Hide the activity monitor window"""
        if self.window and self.is_visible:
            self.window.hide()
            self.is_visible = False
            self._stop_auto_refresh()
            logger.info("Activity monitor display hidden")
    
    def close(self):
        """Close the activity monitor window"""
        if self.window:
            self._stop_auto_refresh()
            self.window.close()
            self.window = None
            self.is_visible = False
            logger.info("Activity monitor display closed")
    
    def _create_window(self):
        """Create the activity monitor window with table-based layout and toolbar"""
        self.window = toga.Window(
            title="Fichero Activity Monitor",
            size=(425, 600),
            resizable=True
        )
        
        main_box = toga.Box(style=Pack(direction=COLUMN, margin=0))
        

        self.task_table = toga.Table(
            headings=["Folder", "Status", "Progress"],
            accessors=["folder", "status", "progress"],
            style=Pack(flex=1, margin=0),
            missing_value="",
            on_select=self._on_task_select
        )
        try:
            self.task_table.column_widths = [200, 150, 100]  # Wider columns for essential info
        except AttributeError:
            pass
        main_box.add(self.task_table)
        
        # Bottom bar: buttons on left, status text on right
        bottom_bar = toga.Box(style=Pack(direction=ROW, margin=(0, 0, 0, 0)))
        
        # Button bar with icon buttons
        button_bar = toga.Box(style=Pack(direction=ROW, margin=(0, 0, 0, 0)))
        
        # Stop button (simple text symbol)
        stop_btn = toga.Button(
            "■",
            on_press=self._cancel_all_handler,
            style=Pack(margin=(2, 2), font_size=9, width=24, height=24)
        )
        button_bar.add(stop_btn)
        
        # Refresh button (simple text symbol)
        refresh_btn = toga.Button(
            "↻",
            on_press=self._refresh_handler,
            style=Pack(margin=(2, 2), font_size=9, width=24, height=24)
        )
        button_bar.add(refresh_btn)
        
        bottom_bar.add(button_bar)
        
        # Status text on right
        self.status_bar = toga.Label(
            "Ready",
            style=Pack(font_size=9, color="#666666", margin_left=3, margin_top=6, margin_right=3)
        )
        bottom_bar.add(self.status_bar)
        spacer = toga.Box(style=Pack(flex=1))
        bottom_bar.add(spacer)
        main_box.add(bottom_bar)
        
        self.window.content = main_box
        self._update_display()
    

    
    def _on_task_select(self, widget):
        """Handle task selection"""
        selection = widget.selection
        if selection:
            # Update status bar with task details
            task_id = getattr(selection, 'task_id', 'Unknown')
            folder = getattr(selection, 'folder', 'Unknown')
            status = getattr(selection, 'status', 'Unknown')
            self.status_bar.text = f"Selected: {folder} ({status}) - Task ID: {task_id}"
        else:
            self.status_bar.text = "No task selected"
    
    def _cancel_all_handler(self, widget):
        """Handle cancel all button"""
        try:
            cancelled_count = self.task_monitor.cancel_all_tasks()
            self.status_bar.text = f"Cancelled {cancelled_count} tasks"
            self._update_display()
        except Exception as e:
            self.status_bar.text = f"Error cancelling tasks: {e}"
    
    def _refresh_handler(self, widget):
        """Handle refresh button"""
        try:
            self._update_display()
            self.status_bar.text = "Refreshed"
        except Exception as e:
            self.status_bar.text = f"Error refreshing: {e}"
    
    def _start_auto_refresh(self):
        """Start auto-refresh task"""
        if not self.auto_refresh_task:
            self.auto_refresh_task = asyncio.create_task(self._auto_refresh_loop())
    
    def _stop_auto_refresh(self):
        """Stop auto-refresh task"""
        if self.auto_refresh_task:
            self.auto_refresh_task.cancel()
            self.auto_refresh_task = None
    
    async def _auto_refresh_loop(self):
        """Auto-refresh loop"""
        try:
            while True:
                self._update_display()
                await asyncio.sleep(0.1)  # Update every 0.1 seconds for smooth spinner
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Auto-refresh error: {e}")
    
    def _update_display(self):
        """Update all display components"""
        try:
            self._update_task_table()
            self._update_status_bar()
        except Exception as e:
            logger.error(f"Display update error: {e}", exc_info=True)
    
    def _update_task_table(self):
        """Update the task table with current data - optimized to update existing items"""
        if not self.task_table:
            return
        
        # Get all tasks (active + recent completed)
        all_tasks = self.task_monitor.get_all_tasks()
        
        # Sort tasks by processing order
        def sort_key(task):
            # Simple status priority for sorting: running -> pending -> failed -> completed
            status_priority = {
                "running": 0,
                "pending": 1, 
                "failed": 2,
                "completed": 3
            }
            priority = status_priority.get(task.status, 1)
            
            if task.status == "running":
                return (priority, task.start_time or datetime.min)
            elif task.status == "pending":
                return (priority, task.created_at)
            else:  # failed or completed
                return (priority, task.end_time or datetime.min)
        
        sorted_tasks = sorted(all_tasks.values(), key=sort_key)
        
        # Create a map of current task IDs to their data
        current_task_map = {}
        for item in self.task_table.data:
            task_id = getattr(item, 'task_id', None)
            if task_id:
                current_task_map[task_id] = item
        
        # Update existing items and add new ones
        new_data = []
        for task in sorted_tasks:
            # Debug logging
            logger.debug(f"Processing task {task.task_id}: status='{task.status}', progress={task.overall_progress}")
            
            # Format duration
            duration_minutes = task.duration.total_seconds() / 60
            duration_str = f"{duration_minutes:.1f}m"
            
            # Get folder name (last part of path)
            folder_name = task.folder_name.split('/')[-1] if '/' in task.folder_name else task.folder_name
            
            # Get worker display name
            worker_display = get_worker_display_name(task.worker, getattr(task, 'executor_type', ''))
            
            # Create tree item data
            if task.status in ("running", "active", "submitted", "processing"):
                # Use animated spinner for running tasks
                status_icon = get_status_icon(task.status, task.worker, task.overall_progress)
                status_text = f"{status_icon} {task.current_step or 'Processing'}"
            else:
                # Use task monitor's status icon for non-running tasks
                status_text = f"{task.status_icon} {task.status.title()}"
            
            tree_item_data = {
                "status": status_text,
                "folder": folder_name,
                "progress": f"{task.overall_progress:.0f}%",
                "task_id": task.task_id,
                "status_text": task.status,
                "folder_full": task.folder_name
            }
            
            # Check if we have an existing item for this task
            if task.task_id in current_task_map:
                # Update existing item in place
                existing_item = current_task_map[task.task_id]
                for key, value in tree_item_data.items():
                    if hasattr(existing_item, key):
                        setattr(existing_item, key, value)
                new_data.append(existing_item)
            else:
                # Create new item
                new_data.append(tree_item_data)
        
        # Only update the table data if there are actual changes
        current_task_ids = []
        for item in self.task_table.data:
            if hasattr(item, 'task_id'):
                current_task_ids.append(item.task_id)
            elif isinstance(item, dict):
                current_task_ids.append(item.get('task_id', ''))
        
        new_task_ids = []
        for item in new_data:
            if hasattr(item, 'task_id'):
                new_task_ids.append(item.task_id)
            elif isinstance(item, dict):
                new_task_ids.append(item.get('task_id', ''))
            else:
                new_task_ids.append('')
        
        if len(new_task_ids) != len(current_task_ids) or new_task_ids != current_task_ids:
            # Create simple data format for Toga Table: list of dictionaries
            table_data = []
            for item in new_data:
                if isinstance(item, dict):
                    table_item = {
                        'folder': item.get('folder', ''),
                        'status': item.get('status', ''),
                        'progress': item.get('progress', ''),
                        'task_id': item.get('task_id', ''),
                        'status_text': item.get('status_text', ''),
                        'folder_full': item.get('folder_full', '')
                    }
                else:
                    # Handle Toga objects
                    table_item = {
                        'folder': getattr(item, 'folder', ''),
                        'status': getattr(item, 'status', ''),
                        'progress': getattr(item, 'progress', ''),
                        'task_id': getattr(item, 'task_id', ''),
                        'status_text': getattr(item, 'status_text', ''),
                        'folder_full': getattr(item, 'folder_full', '')
                    }
                table_data.append(table_item)
            
            self.task_table.data = table_data
    
    def _update_status_bar(self):
        """Update status bar with simplified statistics - only essential info"""
        if not self.status_bar:
            return
        
        try:
            # Get backend info
            backend_info = self.task_monitor.get_backend_info()
            backend_name = backend_info.get('backend_name', 'Unknown')
            
            # Get statistics
            stats = self.task_monitor.get_session_stats()
            active_count = stats['active_tasks']
            
            # Simple status text - only show what matters
            if active_count > 0:
                status_text = f"Processing {active_count} folder{'s' if active_count != 1 else ''}"
            else:
                status_text = f"Ready ({backend_name})"
            
            self.status_bar.text = status_text
            
        except Exception as e:
            self.status_bar.text = f"Error updating status: {e}"



# Convenience functions

def create_document_content_display(document_window, document_id: str):
    """Create a document content display"""
    return DocumentContentDisplay(document_window, document_id)

def create_document_progress_display(document_window, document_id: str):
    """Create a document progress display"""
    return DocumentProgressDisplay(document_window, document_id)

def create_activity_monitor_display(app):
    """Create an activity monitor display"""
    return ActivityMonitorDisplay(app) 

def format_task_row(task, platform_name=None):
    if platform_name is None:
        platform_name = platform.system().lower()
    is_macos = platform_name == "darwin"

    # Spinner/Status
    if task.status == "running":
        if is_macos:
            spinner = toga.ActivityIndicator()
            spinner.start()
            status_widget = spinner
        else:
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

    # Progress
    if is_macos:
        progress_widget = toga.ProgressBar(max=100, value=task.overall_progress)
    else:
        progress_widget = f"{task.overall_progress:.0f}%"

    return {
        "folder": task.folder_name,
        "status": status_widget,
        "progress": progress_widget,
        "task_id": task.task_id,  # for selection/cancellation
    } 