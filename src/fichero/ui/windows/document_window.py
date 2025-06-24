"""
Document Window for Fichero - Thin Wrapper

Lightweight document window that delegates all business logic to director.py.
This ensures GUI and CLI share the same codebase for:
- Progress tracking with rich Toga progress bars via DocumentProgressDisplay
- Logging and error handling
- Status monitoring
- Task management

The UI focuses on display and user interaction, while director.py handles all processing.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER, LEFT
from pathlib import Path
import asyncio
import webbrowser
import yaml
import os
import time
from typing import Optional, Any, Dict, List
import logging

from ..i18n import _, translator
from ...config.core.plan_manager import PlanManager
from ...config.core.settings import get_app_settings
from ...director import FicheroDirector
from ...director.monitoring.displays.gui_display import DocumentContentDisplay

logger = logging.getLogger(__name__)


class FicheroDocumentWindow(toga.DocumentWindow):
    """
    Thin document window wrapper that delegates processing to director.py.
    
    Features beautiful Toga UI with progress bars via DocumentContentDisplay
    while keeping business logic in the director service for code reuse between GUI and CLI.
    """
    
    def __init__(self, doc):
        logger.info(f"Initializing document window for document {doc.document_id}")
        
        # Store references
        self._document = doc
        self._app = doc.app
        
        # Initialize state
        self.selected_folder = None
        self.current_plan = None
        self.current_workflow = None
        
        # Content display via DocumentContentDisplay
        self.content_display: Optional[DocumentContentDisplay] = None
        self.current_task_ids = []
        
        # Create UI content
        content = self._create_content()
        
        super().__init__(doc=doc, content=content)
        
        # Set up window handlers and restore position
        self._setup_window_handlers()
        
        # Initialize plan selection after window is created
        asyncio.create_task(self._initialize_after_show())
        
        logger.info("Document window initialized successfully")
    
    async def _initialize_after_show(self):
        """Initialize components after window is shown"""
        await asyncio.sleep(0.1)  # Let window fully render
        try:
            self._draw_folder_background()
            self._initialize_plan_workflow()
            self._restore_window_position()
        except Exception as e:
            logger.error(f"Initialization error: {e}")
    
    def _create_content(self):
        """Create simplified document window UI"""
        # Create main sections
        self._create_folder_selection_section()
        self._create_content_section()
        self._create_footer()
        
        # Assemble layout
        main_sections = toga.Box(style=Pack(direction=COLUMN, flex=1))
        main_sections.add(self.folder_section)
        main_sections.add(self.content_section)
        
        main_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
        main_content.add(main_sections)
        main_content.add(self.footer_section)
        
        return main_content

    def _create_folder_selection_section(self):
        """Create folder selection section with icon and background"""
        # Folder icon
        try:
            fichero_image = toga.Image("resources/icons/folder_with_question_mark.png")
            folder_icon = toga.ImageView(
                fichero_image,
                style=Pack(width=62, height=62, margin=3)
            )
        except Exception as e:
            logger.warning(f"Could not load folder icon: {e}")
            folder_icon = toga.Label(
                "📁?",
                style=Pack(font_size=32, text_align=CENTER, margin=8)
            )
        
        # Choose folder button
        self.choose_folder_btn = toga.Button(
            _("choose_folder"),
            on_press=self.choose_folder_handler,
            style=Pack(width=120)
        )
        
        # Button container with centering
        button_row = toga.Box(
            children=[
                toga.Box(style=Pack(flex=1)),  # Left spacer
                self.choose_folder_btn,
                toga.Box(style=Pack(flex=1))   # Right spacer
            ],
            style=Pack(direction=ROW, align_items=CENTER)
        )
        
        # Canvas for rounded background
        self.folder_canvas = toga.Canvas(
            style=Pack(width=540, height=68),
            on_resize=self._draw_folder_background
        )
        
        # Overlay button on canvas
        path_container = toga.Box(
            children=[button_row],
            style=Pack(
                direction=COLUMN,
                justify_content=CENTER,
                width=540,
                height=68,
            )
        )
        
        # Stack canvas and button
        path_with_background = toga.Box(
            children=[self.folder_canvas],
            style=Pack(
                direction=COLUMN,
                margin_top=20,
                margin_right=20,
                margin_bottom=10,
                margin_left=10,
            )
        )
        
        overlaid_container = toga.Box(
            children=[path_container],
            style=Pack(
                direction=COLUMN,
                margin_top=-78,
                margin_right=20,
                margin_left=10,
            )
        )
        
        path_stack = toga.Box(
            children=[path_with_background, overlaid_container],
            style=Pack(direction=COLUMN)
        )
        
        # Icon container
        icon_container = toga.Box(
            children=[folder_icon],
            style=Pack(
                direction=COLUMN,
                justify_content=CENTER,
                margin_top=20 + 34 - 34,
                margin_left=20
            )
        )
        
        # Main container
        self.folder_section = toga.Box(
            children=[icon_container, path_stack],
            style=Pack(direction=ROW, margin=(0, 0, 0, 0))
        )

    def _draw_folder_background(self, canvas=None, **kwargs):
        """Draw rounded gray background"""
        if canvas is None:
            canvas = self.folder_canvas
            
        canvas.context.clear()
        
        width = canvas.layout.content_width
        height = canvas.layout.content_height
        corner_radius = 6
        
        with canvas.context.Fill(color='rgb(217, 217, 217)') as background:
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

    def _create_content_section(self):
        """Create content section that delegates to DocumentContentDisplay"""
        # Initialize content display
        self.content_display = DocumentContentDisplay(self, self._document.document_id)
        
        # Get the content section from the display
        self.content_section = self.content_display.get_content_section()

    def _create_footer(self):
        """Create footer with controls"""
        # Left side: Help and plan selection
        left_section = toga.Box(style=Pack(direction=ROW))
        
        help_btn = toga.Button(
            _("help"),
            on_press=self.help_handler,
            style=Pack(font_size=12, font_weight='bold', width=24, height=24)
        )
        left_section.add(help_btn)
        
        # Plan selector
        self.plan_selector = toga.Selection(
            items=PlanManager.get_plan_dropdown_options(self._app),
            style=Pack(width=120, font_size=11, margin_left=5, height=24),
            on_change=self._on_plan_change
        )
        left_section.add(self.plan_selector)
        
        # Workflow selector
        self.workflow_selector = toga.Selection(
            items=["Select a plan first"],
            style=Pack(width=120, font_size=11, margin_left=5, height=24),
            on_change=self._on_workflow_change
        )
        left_section.add(self.workflow_selector)
        
        # Right side: Process controls
        right_section = toga.Box(style=Pack(direction=ROW))
        
        self.activity_indicator = toga.ActivityIndicator(
            style=Pack(margin_right=10)
        )
        
        self.process_btn = toga.Button(
            _("process"),
            on_press=self.process_handler,
            enabled=False,
            style=Pack(font_size=12, height=32)
        )
        
        right_section.add(self.activity_indicator)
        right_section.add(self.process_btn)
        
        # Assemble footer
        spacer = toga.Box(style=Pack(flex=1))
        
        self.footer_section = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(10, 20, 20, 20),
                align_items=CENTER
            )
        )
        
        self.footer_section.add(left_section)
        self.footer_section.add(spacer)
        self.footer_section.add(right_section)

    # Progress Management - Delegated to DocumentContentDisplay
    
    def _reset_to_process_button(self):
        """Reset button back to process state"""
        self.activity_indicator.stop()
        self.process_btn.enabled = bool(self.selected_folder and self.current_plan)
        self.process_btn.text = _("process")
        self.process_btn.on_press = self.process_handler
        # Reset button style to default (remove red background)
        if hasattr(self.process_btn.style, 'background_color'):
            del self.process_btn.style.background_color
        if hasattr(self.process_btn.style, 'color'):
            del self.process_btn.style.color
    
    def _get_content_display(self):
        """Lazily initialize DocumentContentDisplay when needed"""
        if not self.content_display:
            try:
                self.content_display = DocumentContentDisplay(self, self._document.document_id)
                logger.info(f"DocumentContentDisplay initialized for document: {self._document.document_id}")
            except Exception as e:
                logger.error(f"Failed to initialize DocumentContentDisplay: {e}")
                return None
        return self.content_display
    
    def _show_stopped_message(self, output_path, completed_tasks, failed_tasks):
        """Show a custom stopped message with results and options"""
        content_display = self._get_content_display()
        if not content_display:
            return
        
        # Mark as not showing progress so we can create custom content
        content_display.is_showing_progress = False
        
        # Clear content and create stopped message view
        content_display.content_section.clear()
        
        # Create main container
        stopped_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=(20, 20, 20, 20),
                align_items=CENTER
            )
        )
        
        # Title
        title_label = toga.Label(
            "🛑 Processing Stopped",
            style=Pack(
                font_size=16,
                font_weight='bold',
                color='#d32f2f',
                margin_bottom=15
            )
        )
        stopped_container.add(title_label)
        
        # Results summary
        total_tasks = completed_tasks + failed_tasks
        if total_tasks > 0:
            results_text = f"📊 Results: {completed_tasks} completed"
            if failed_tasks > 0:
                results_text += f", {failed_tasks} failed"
        else:
            results_text = "⏸️ Processing was interrupted before completion"
            
        results_label = toga.Label(
            results_text,
            style=Pack(
                font_size=12,
                margin_bottom=10,
                text_align=CENTER
            )
        )
        stopped_container.add(results_label)
        
        # Output location (if available)
        if output_path:
            output_label = toga.Label(
                f"📁 Output: {output_path}",
                style=Pack(
                    font_size=11,
                    color='#666666',
                    margin_bottom=20,
                    text_align=CENTER
                )
            )
            stopped_container.add(output_label)
        
        # Action buttons
        button_container = toga.Box(
            style=Pack(direction=ROW, margin_top=10)
        )
        
        # View Output button (if output exists)
        if output_path and Path(output_path).exists():
            view_output_btn = toga.Button(
                "📁 View Output",
                on_press=lambda w: self._open_output_folder(output_path),
                style=Pack(margin_right=10)
            )
            button_container.add(view_output_btn)
        
        # Activity Monitor button
        activity_btn = toga.Button(
            "📊 Activity Monitor",
            on_press=lambda w: self._open_activity_monitor(),
            style=Pack(margin_right=10)
        )
        button_container.add(activity_btn)
        
        # Back button
        back_btn = toga.Button(
            "↩️ Back",
            on_press=lambda w: content_display.show_description_view(),
            style=Pack(background_color='#1976d2', color='white')
        )
        button_container.add(back_btn)
        
        stopped_container.add(button_container)
        
        # Add to content section
        content_display.content_section.add(stopped_container)
    
    def _open_output_folder(self, output_path):
        """Open the output folder in Finder/Explorer"""
        try:
            import subprocess
            import platform
            
            path = Path(output_path)
            if path.exists():
                if platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", str(path)])
                elif platform.system() == "Windows":
                    subprocess.run(["explorer", str(path)])
                else:  # Linux
                    subprocess.run(["xdg-open", str(path)])
            else:
                logger.warning(f"Output path does not exist: {path}")
        except Exception as e:
            logger.error(f"Failed to open output folder: {e}")
    
    def _open_activity_monitor(self):
        """Open the activity monitor window"""
        try:
            # Use the app's activity monitor functionality
            if hasattr(self._app, 'show_activity_monitor'):
                self._app.show_activity_monitor()
            else:
                logger.warning("Activity monitor not available")
        except Exception as e:
            logger.error(f"Failed to open activity monitor: {e}")
    
    # Event Handlers - Thin Wrappers for Director
    
    async def choose_folder_handler(self, widget):
        """Handle folder selection"""
        try:
            folder_path = await self.dialog(toga.SelectFolderDialog(
                title=_("select_folder_title")
            ))
            
            if folder_path:
                self.selected_folder = Path(folder_path)
                folder_name = self.selected_folder.name
                self.choose_folder_btn.text = f"📁 {folder_name}"
                self.process_btn.enabled = bool(self.current_plan)
                logger.info(f"Selected folder: {self.selected_folder}")
            
        except Exception as e:
            logger.error(f"Error selecting folder: {e}")
            await self.dialog(toga.InfoDialog("Error", f"Failed to select folder: {e}"))

    def help_handler(self, widget):
        """Handle help button - return to description view"""
        content_display = self._get_content_display()
        if content_display and content_display.is_showing_progress:
            content_display.show_description_view()
        webbrowser.open("https://www.tubb.ca/fichero/")
    
    async def stop_handler(self, widget):
        """Handle stop button - cancel current processing and show results"""
        try:
            if not self.current_task_ids:
                return
            
            # Ask for confirmation
            confirm = await self.dialog(toga.QuestionDialog(
                "Stop Processing",
                "Are you sure you want to stop the current processing?"
            ))
            
            if confirm:
                # Get task status before cancelling to show what was completed
                director = self._app.director
                completed_tasks = 0
                failed_tasks = 0
                output_path = None
                
                for task_id in self.current_task_ids:
                    try:
                        status = director.get_task_status(task_id)
                        if status and hasattr(status, 'value'):
                            if status.value == "SUCCESS":
                                completed_tasks += 1
                            elif status.value == "FAILED":
                                failed_tasks += 1
                        
                        # Get output path from task info
                        if not output_path:
                            task_info = director.get_task_info(task_id)
                            if task_info:
                                output_path = getattr(task_info, 'output_path', None)
                        
                        # Cancel the task
                        director.cancel_task(task_id)
                        logger.info(f"Cancelled task: {task_id}")
                    except Exception as e:
                        logger.warning(f"Could not cancel task {task_id}: {e}")
                
                # Store total tasks before clearing
                total_tasks = len(self.current_task_ids)
                
                # Reset UI state
                self._reset_to_process_button()
                self.current_task_ids = []
                
                # Stop progress monitoring in content display
                content_display = self._get_content_display()
                if content_display and content_display.progress_display:
                    content_display.progress_display.stop_processing()
                
                # Show custom stopped message instead of returning to description
                if content_display and content_display.is_showing_progress:
                    self._show_stopped_message(output_path, completed_tasks, failed_tasks)
                
                # Show summary dialog
                message = f"Processing stopped.\n\nCompleted: {completed_tasks}/{total_tasks} tasks"
                if failed_tasks > 0:
                    message += f"\nFailed: {failed_tasks}"
                if output_path:
                    message += f"\n\nOutput location:\n{output_path}"
                
                await self.dialog(toga.InfoDialog("Processing Stopped", message))
                
        except Exception as e:
            logger.error(f"Error stopping processing: {e}")
            await self.dialog(toga.InfoDialog("Error", f"Failed to stop processing: {e}"))

    async def process_handler(self, widget):
        """
        Handle process button - delegate everything to director.py and DocumentContentDisplay
        
        This uses DocumentContentDisplay for UI management and director.py for business logic.
        """
        if not self.selected_folder:
            await self.dialog(toga.InfoDialog("Error", "Please select a folder to process"))
            return
        
        if not self.current_plan:
            await self.dialog(toga.InfoDialog("Error", "Please select a plan"))
            return
        
        # Use default workflow if none selected
        workflow_to_use = self.current_workflow or "default"
        
        # Ask user where to save output - default to Desktop
        try:
            # Get desktop path cross-platform
            desktop_path = Path.home() / "Desktop"
            if not desktop_path.exists():
                # Fallback to home directory if Desktop doesn't exist
                desktop_path = Path.home()
            
            folder_name = self.selected_folder.name
            suggested_name = f"{folder_name}_processed"
            
            # Use SelectFolderDialog with desktop as initial directory
            parent_path = await self.dialog(toga.SelectFolderDialog(
                title="Choose where to save processed results...",
                initial_directory=desktop_path
            ))
            
            if not parent_path:
                return  # User cancelled
            
            # Create the output path with suggested name
            output_path = Path(parent_path) / suggested_name
            
            # Ensure the path doesn't already exist, or confirm reprocessing
            if output_path.exists():
                reprocess = await self.dialog(toga.QuestionDialog(
                    "Folder Exists",
                    f"A folder named '{output_path.name}' already exists. Do you want to continue processing and replace it?"
                ))
                if not reprocess:
                    return
            
            logger.info(f"User chose save location: {output_path}")
            
        except Exception as e:
            logger.error(f"Error with save dialog: {e}")
            await self.dialog(toga.InfoDialog("Error", f"Failed to select save location: {e}"))
            return
        
        # Start activity indicator and change to stop button
        self.activity_indicator.start()
        self.process_btn.enabled = True
        self.process_btn.text = "🛑 Stop"
        self.process_btn.on_press = self.stop_handler
        self.process_btn.style.update(background_color="#ff4444", color="#ffffff")
        
        try:
            # Get director service (app should have initialized it)
            if not hasattr(self._app, 'director') or not self._app.director:
                raise Exception("Director service not available")
            
            director = self._app.director
            
            if not FicheroDirector.is_initialized():
                raise Exception("Director service not initialized")
            
            # Director handles folder detection internally
            detected_folders = [self.selected_folder]
            
            # Submit tasks using director's auto-detection - this handles everything!
            self.current_task_ids = director.process_with_auto_detection(
                input_path=self.selected_folder,
                output_path=output_path,
                plan_name=self.current_plan,
                workflow_name=workflow_to_use,
                document_context={
                    "document_window": self,
                    "document_id": self._document.document_id
                }
            )
            
            if not self.current_task_ids:
                raise Exception("No tasks were submitted")
            
            logger.info(f"Submitted {len(self.current_task_ids)} tasks for processing")
            
            # Start content display via DocumentContentDisplay
            content_display = self._get_content_display()
            if content_display:
                content_display.show_progress_view(self.current_task_ids, detected_folders)
            
            # Start monitoring task completion
            asyncio.create_task(self._monitor_task_completion())
            
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            await self.dialog(toga.InfoDialog("Error", f"Failed to start processing: {e}"))
            self._reset_to_process_button()
    
    async def _monitor_task_completion(self):
        """Monitor task completion in background - DocumentContentDisplay handles UI updates"""
        if not self.current_task_ids:
            return
        
        director = self._app.director
        
        while True:
            try:
                # Check if all tasks completed
                statuses = []
                for task_id in self.current_task_ids:
                    status = director.get_task_status(task_id)
                    if status and hasattr(status, 'value'):
                        statuses.append(status.value)
                    else:
                        statuses.append('UNKNOWN')
                
                if all(s in ["SUCCESS", "FAILED", "CANCELLED"] for s in statuses):
                    # All tasks completed - DocumentContentDisplay handles UI updates
                    # Just reset button states here
                    self._reset_to_process_button()
                    
                    # Stop progress monitoring in content display
                    content_display = self._get_content_display()
                    if content_display and content_display.progress_display:
                        content_display.progress_display.stop_processing()
                    
                    self.current_task_ids = []
                    break
                
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"Error monitoring tasks: {e}")
                # Reset button states on error
                self._reset_to_process_button()
                
                # Stop progress monitoring on error
                content_display = self._get_content_display()
                if content_display and content_display.progress_display:
                    content_display.progress_display.stop_processing()
                break

    # Plan Management - Simplified
    
    def _initialize_plan_workflow(self):
        """Initialize plan and workflow using unified helper"""
        try:
            from ...config.core.plan_workflow_ui_helper import PlanWorkflowUIHelper
            
            # Create unified helper
            self.ui_helper = PlanWorkflowUIHelper(self._app)
            
            # Initialize widgets with app defaults (document-specific mode)
            result = self.ui_helper.initialize_document_widgets(
                self.plan_selector, 
                self.workflow_selector
            )
            
            # Store current selections
            self.current_plan = result.get('plan')
            self.current_workflow = result.get('workflow')
            
            # Enable process button if folder selected
            self.process_btn.enabled = bool(self.selected_folder)
            
        except Exception as e:
            logger.error(f"Error initializing plan/workflow: {e}")
    
    def _on_plan_change(self, widget):
        """Handle plan selection change using unified helper"""
        try:
            if not hasattr(self, 'ui_helper'):
                return
            
            # Use unified helper with save_as_default=False (document-specific)
            result = self.ui_helper.handle_plan_change(
                widget, 
                self.workflow_selector, 
                save_as_default=False
            )
            
            # Update current selections
            self.current_plan = result.get('plan')
            self.current_workflow = result.get('workflow')
            
            # Enable process button if folder selected
            self.process_btn.enabled = bool(self.selected_folder)
            
            logger.info(f"Document plan changed: {result}")
            
        except Exception as e:
            logger.error(f"Error handling plan change: {e}")
    
    def _on_workflow_change(self, widget):
        """Handle workflow selection change using unified helper"""
        try:
            if not hasattr(self, 'ui_helper'):
                return
            
            # Use unified helper with save_as_default=False (document-specific)
            workflow_name = self.ui_helper.handle_workflow_change(
                widget, 
                save_as_default=False
            )
            
            # Update current selection
            self.current_workflow = workflow_name
            
            logger.info(f"Document workflow changed: {workflow_name}")
        
        except Exception as e:
            logger.error(f"Error handling workflow change: {e}")

    # Window Management
    
    def _setup_window_handlers(self):
        """Set up window event handlers"""
        try:
            def on_position_change(widget, **kwargs):
                try:
                    if hasattr(widget, 'position') and hasattr(widget, 'size'):
                        self._document.save_window_position(widget.position, widget.size)
                except Exception as e:
                    logger.warning(f"Error saving window position: {e}")
            
            def on_close_handler(widget, **kwargs):
                try:
                    if hasattr(widget, 'position') and hasattr(widget, 'size'):
                        self._document.save_window_position(widget.position, widget.size)
                    return self._document.close()
                except Exception as e:
                    logger.warning(f"Error in close handler: {e}")
                    return True
            
            # Set handlers if available
            if hasattr(self, 'on_move'):
                self.on_move = on_position_change
            if hasattr(self, 'on_resize'):
                self.on_resize = on_position_change
            if hasattr(self, 'on_close'):
                self.on_close = on_close_handler
                
        except Exception as e:
            logger.warning(f"Failed to set up window handlers: {e}")
    
    def _restore_window_position(self):
        """Restore window position from document settings"""
        try:
            saved_position = self._document.get_window_position()
            saved_size = self._document.get_window_size()
            
            if saved_position != (100, 100):
                self.position = saved_position
            
            if saved_size != (650, 406):
                self.size = saved_size
                
        except Exception as e:
            logger.warning(f"Failed to restore window position: {e}")