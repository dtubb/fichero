"""
GUI Task Displays

Toga-based displays for task monitoring.
Provides both Activity Monitor window and document progress widgets.
"""

import asyncio
import logging
from typing import Optional, Dict, List, Callable
from datetime import datetime
from pathlib import Path

try:
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN, ROW, CENTER
    TOGA_AVAILABLE = True
except ImportError:
    TOGA_AVAILABLE = False

from ..task_monitor import TaskMonitor, TaskInfo

logger = logging.getLogger(__name__)


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
            style=Pack(direction=COLUMN, margin=(0, 0, 0, 0))
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
                height=200,
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
        left_padding = 15
        top_padding = 15
        right_padding = 10
        max_width = canvas.layout.content_width - left_padding - right_padding
        
        paragraphs = text.split('\n\n')
        current_y = top_padding
        
        for paragraph_idx, paragraph in enumerate(paragraphs):
            if paragraph_idx > 0:
                current_y += regular_font.size * line_height_multiplier * 0.8
            
            current_y = self._render_paragraph(canvas, paragraph, left_padding, current_y, 
                                             max_width, regular_font, bold_font, line_height_multiplier)
    
    def _render_paragraph(self, canvas, text, left_padding, start_y, max_width, 
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
                                                    left_padding, current_y, line_height_multiplier)
                    
                    current_line_elements = [{
                        **element,
                        'content': word,
                        'width': canvas.measure_text(word, element['font'])[0]
                    }]
                    current_line_width = current_line_elements[0]['width']
        
        if current_line_elements:
            current_y = self._render_line(canvas, current_line_elements, 
                                        left_padding, current_y, line_height_multiplier)
        
        return current_y
    
    def _render_line(self, canvas, elements, left_padding, y_position, line_height_multiplier):
        """Render a line of formatted text elements"""
        current_x = left_padding
        
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
    Shows progress for tasks from a specific document.
    """
    
    def __init__(self, document_window, document_id: str):
        if not TOGA_AVAILABLE:
            raise ImportError("Toga is required for GUI progress display")
        
        self.document_window = document_window
        self.document_id = document_id
        self.task_monitor = TaskMonitor.get_instance(document_window._app.director, f"gui_doc_{document_id}")
        
        # UI state
        self.progress_widgets: Dict[str, Dict] = {}
        self.progress_container = None
        self.progress_box = None
        self.is_showing_progress = False
        
        # Register for task updates
        self.task_monitor.register_callback(self._on_task_update)
        
        logger.info(f"DocumentProgressDisplay initialized for document: {document_id}")
    
    def start_processing(self, task_ids: List[str], folders: List[Path]):
        """Start progress display for processing tasks"""
        try:
            # Create progress view
            self._create_progress_view()
            
            # Initialize progress widgets for each folder
            self._initialize_folder_progress(folders)
            
            # Monitor the specific tasks
            self.current_task_ids = task_ids
            
            logger.info(f"Started progress display for {len(task_ids)} tasks")
            
        except Exception as e:
            logger.error(f"Failed to start progress display: {e}")
    
    def _create_progress_view(self):
        """Create progress view container"""
        if not self.is_showing_progress:
            self.is_showing_progress = True
            
            # Create scrollable progress container
            self.progress_container = toga.ScrollContainer(
                style=Pack(
                    margin_top=20,
                    margin_right=20,
                    margin_bottom=10,
                    margin_left=20,
                    flex=1,
                    height=200,
                )
            )
            
            self.progress_box = toga.Box(
                style=Pack(direction=COLUMN, margin=10)
            )
            
            self.progress_container.content = self.progress_box
    
    def _initialize_folder_progress(self, folders: List[Path]):
        """Initialize progress widgets for each folder"""
        if not self.is_showing_progress or not self.progress_box:
            return
        
        self.progress_widgets.clear()
        self.progress_box.clear()
        
        # Header
        header = toga.Label(
            f"🚀 Processing {len(folders)} folder{'s' if len(folders) != 1 else ''}:",
            style=Pack(margin_bottom=15, font_size=14, font_weight='bold')
        )
        self.progress_box.add(header)
        
        # Create progress widgets
        for folder in folders:
            folder_widget = self._create_folder_progress_widget(folder)
            self.progress_widgets[folder.name] = folder_widget
            self.progress_box.add(folder_widget['container'])
            
            # Add separator between folders
            separator = toga.Divider(style=Pack(margin=(10, 0)))
            self.progress_box.add(separator)
    
    def _create_folder_progress_widget(self, folder: Path) -> Dict:
        """Create progress widget for a single folder"""
        container = toga.Box(
            style=Pack(direction=COLUMN, margin=(5, 0, 15, 0))
        )
        
        # Header with folder name and status
        header_row = toga.Box(
            style=Pack(direction=ROW, align_items=CENTER, margin_bottom=8)
        )
        
        status_icon = toga.Label(
            "⏳",
            style=Pack(font_size=16, width=30, margin_right=10)
        )
        
        # Get just the folder name (last part of path)
        folder_name = folder.name
        
        folder_label = toga.Label(
            f"📁 {folder_name}",
            style=Pack(flex=1, font_size=12, font_weight='bold')
        )
        
        header_row.add(status_icon)
        header_row.add(folder_label)
        
        # Progress percentage (instead of bar)
        progress_label = toga.Label(
            "0.0%",
            style=Pack(width=60, margin_bottom=5, font_size=11, font_weight='bold')
        )
        
        # Status text
        status_text = toga.Label(
            "Waiting to start...",
            style=Pack(font_size=10, color='#666666')
        )
        
        # Assemble widget
        container.add(header_row)
        container.add(progress_label)
        container.add(status_text)
        
        return {
            'container': container,
            'status_icon': status_icon,
            'folder_label': folder_label,
            'progress_label': progress_label,
            'status_text': status_text,
            'folder': folder
        }
    
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
            folder_name = task.folder_name.split('/')[-1] if '/' in task.folder_name else task.folder_name
            if folder_name in self.progress_widgets:
                widgets = self.progress_widgets[folder_name]
                
                # Update status icon
                widgets['status_icon'].text = task.status_icon
                
                # Update progress label
                if task.status == "running" and task.overall_progress > 0:
                    widgets['progress_label'].text = f"{task.overall_progress:.1f}%"
                elif task.status == "completed":
                    widgets['progress_label'].text = "100.0%"
                elif task.status == "failed":
                    widgets['progress_label'].text = "Failed"
                else:
                    widgets['progress_label'].text = "Waiting"
                
                # Update status text
                if task.current_step:
                    widgets['status_text'].text = f"🔧 {task.current_step}"
                elif task.status == "completed":
                    widgets['status_text'].text = "🎉 Completed successfully!"
                elif task.status == "failed":
                    widgets['status_text'].text = f"❌ {task.error_message or 'Processing failed'}"
                else:
                    widgets['status_text'].text = f"📊 {task.status.title()}"
                    
        except Exception as e:
            logger.error(f"Error updating progress UI: {e}")
    
    async def _handle_task_completion(self, task: TaskInfo):
        """Handle task completion"""
        try:
            # Check if all tasks for this document are complete
            document_tasks = self.task_monitor.get_tasks_by_document(self.document_id)
            active_tasks = [t for t in document_tasks.values() if t.is_active]
            
            if not active_tasks:
                # All tasks completed
                completed_tasks = [t for t in document_tasks.values() if t.status == "completed"]
                failed_tasks = [t for t in document_tasks.values() if t.status == "failed"]
                
                # Stop activity indicator
                self.document_window.activity_indicator.stop()
                self.document_window.process_btn.enabled = True
                self.document_window.process_btn.text = "Process"
                
                # Show completion dialog
                if failed_tasks:
                    await self.document_window.dialog(toga.InfoDialog(
                        "❌ Processing Failed",
                        f"{len(failed_tasks)} of {len(document_tasks)} tasks failed"
                    ))
                else:
                    await self.document_window.dialog(toga.InfoDialog(
                        "🎉 Processing Complete",
                        "All folders have been processed successfully!"
                    ))
                
                # Add return button
                if self.progress_box:
                    return_button = toga.Button(
                        "🏠 Return to Main View",
                        on_press=self._return_to_main_view,
                        style=Pack(margin_top=20, width=200, padding=10)
                    )
                    self.progress_box.add(return_button)
                    
        except Exception as e:
            logger.error(f"Error handling task completion: {e}")
    
    def _return_to_main_view(self, widget):
        """Return to description view"""
        try:
            self.is_showing_progress = False
            self.progress_widgets.clear()
            
            # Notify the document window to return to description view
            if hasattr(self.document_window, 'content_display'):
                self.document_window.content_display.show_description_view()
            
        except Exception as e:
            logger.error(f"Error returning to main view: {e}")


class ActivityMonitorDisplay:
    """
    Activity Monitor display for system-wide task monitoring.
    Shows all tasks across all document windows and CLI instances.
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
        self.backend_status_label = None
        self.stats_label = None
        self.task_table = None
        
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
        """Create the activity monitor window"""
        self.window = toga.Window(
            title="Fichero Activity Monitor",
            size=(800, 600),
            resizable=True
        )
        
        # Create main container
        main_box = toga.Box(style=Pack(direction=COLUMN, margin=10))
        
        # Backend status section
        backend_section = self._create_backend_section()
        main_box.add(backend_section)
        
        # Stats section
        stats_section = self._create_stats_section()
        main_box.add(stats_section)
        
        # Task list section
        task_section = self._create_task_section()
        main_box.add(task_section)
        
        # No control buttons - just monitoring
        
        self.window.content = main_box
        
        # Remove problematic close handler that causes crashes
        # Let Toga handle window closing naturally
        
        # Initial update
        self._update_display()
    
    def _create_backend_section(self):
        """Create backend status section"""
        section = toga.Box(style=Pack(direction=COLUMN, margin_bottom=10))
        
        # Title
        title = toga.Label(
            "Backend Status",
            style=Pack(font_size=14, font_weight='bold', margin_bottom=5)
        )
        section.add(title)
        
        # Status label
        self.backend_status_label = toga.Label(
            "Backend: Loading...",
            style=Pack(font_size=11, margin_bottom=10)
        )
        section.add(self.backend_status_label)
        
        return section
    
    def _create_stats_section(self):
        """Create statistics section"""
        section = toga.Box(style=Pack(direction=COLUMN, margin_bottom=10))
        
        # Title
        title = toga.Label(
            "Task Statistics",
            style=Pack(font_size=14, font_weight='bold', margin_bottom=5)
        )
        section.add(title)
        
        # Stats label
        self.stats_label = toga.Label(
            "Loading statistics...",
            style=Pack(font_size=11, margin_bottom=10)
        )
        section.add(self.stats_label)
        
        return section
    
    def _create_task_section(self):
        """Create task list section"""
        section = toga.Box(style=Pack(direction=COLUMN, margin_bottom=10, flex=1))
        
        # Title
        title = toga.Label(
            "Active Tasks",
            style=Pack(font_size=14, font_weight='bold', margin_bottom=5)
        )
        section.add(title)
        
        # Task table
        self.task_table = toga.DetailedList(
            style=Pack(flex=1, margin_bottom=10)
        )
        section.add(self.task_table)
        
        return section
    
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
                await asyncio.sleep(1.0)  # Update every second
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Auto-refresh error: {e}")
    
    def _update_display(self):
        """Update all display components"""
        try:
            # Update backend status
            self._update_backend_status()
            
            # Update statistics
            self._update_statistics()
            
            # Update task list
            self._update_task_list()
            
        except Exception as e:
            logger.error(f"Display update error: {e}")
    
    def _update_backend_status(self):
        """Update backend status display"""
        if not self.backend_status_label:
            return
        
        backend_info = self.task_monitor.get_backend_info()
        status_text = f"Backend: {backend_info.get('backend_name', 'Unknown')}"
        status_text += f" | Status: {backend_info.get('status', 'Unknown')}"
        
        self.backend_status_label.text = status_text
    
    def _update_statistics(self):
        """Update statistics display"""
        if not self.stats_label:
            return
        
        # Statistics
        stats = self.task_monitor.get_session_stats()
        stats_text = f"Active Tasks: {stats['active_tasks']} | "
        stats_text += f"Session: {stats['session_tasks']} | "
        stats_text += f"Completed: {stats['completed_tasks']} | "
        stats_text += f"Failed: {stats['failed_tasks']}"
        
        self.stats_label.text = stats_text
    
    def _update_task_list(self):
        """Update task list display"""
        if not self.task_table:
            return
        
        # Clear existing items
        self.task_table.data.clear()
        
        # Get active tasks and separate them
        active_tasks = self.task_monitor.get_active_tasks()
        running_tasks = []
        waiting_tasks = []
        
        for task in active_tasks.values():
            if task.status == "pending":
                waiting_tasks.append(task)
            else:
                running_tasks.append(task)
        
        # Add running tasks first
        for task in running_tasks:
            # Format duration in minutes
            duration_minutes = task.duration.total_seconds() / 60
            duration_str = f"{duration_minutes:.1f}m"
            
            # Get just the folder name (last part of path)
            folder_name = task.folder_name.split('/')[-1] if '/' in task.folder_name else task.folder_name
            
            # Create detailed list item
            item = {
                "title": f"{task.status_icon} {folder_name}",
                "subtitle": f"Plan: {task.plan_name} | Step: {task.current_step} | Progress: {task.overall_progress:.1f}% | Duration: {duration_str} | Worker: {task.worker}",
                "icon": None,
                "data": task
            }
            
            self.task_table.data.append(item)
        
        # Add waiting tasks at the bottom
        if waiting_tasks:
            # Add separator if we had running tasks
            if running_tasks:
                self.task_table.data.append({
                    "title": "--- Waiting Tasks ---",
                    "subtitle": "",
                    "icon": None,
                    "data": None
                })
            
            for task in waiting_tasks:
                # Format duration in minutes
                duration_minutes = task.duration.total_seconds() / 60
                duration_str = f"{duration_minutes:.1f}m"
                
                # Get just the folder name (last part of path)
                folder_name = task.folder_name.split('/')[-1] if '/' in task.folder_name else task.folder_name
                
                # Create detailed list item for waiting task
                item = {
                    "title": f"{task.status_icon} {folder_name}",
                    "subtitle": f"Plan: {task.plan_name} | Waiting... | Progress: 0.0% | Duration: {duration_str} | Worker: queue",
                    "icon": None,
                    "data": task
                }
                
                self.task_table.data.append(item)
        
        # Add message if no tasks
        if not active_tasks:
            self.task_table.data.append({
                "title": "No active tasks",
                "subtitle": "All tasks completed or no tasks running",
                "icon": None,
                "data": None
            })
    
    # Pure monitoring - no manual controls needed
    



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