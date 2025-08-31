"""
Progress Display Component

Handles task progress monitoring and display during processing.
Uses GUITaskDisplay for beautiful progress bars and real-time updates.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER
import asyncio
import logging
from typing import Optional, List, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class ProgressDisplay:
    """Progress display component for task monitoring"""
    
    def __init__(self, app, on_processing_complete: Optional[Callable] = None, on_processing_stopped: Optional[Callable] = None):
        """Initialize progress display"""
        self.app = app
        self.on_processing_complete = on_processing_complete
        self.on_processing_stopped = on_processing_stopped
        
        # State
        self.current_task_ids: List[str] = []
        self.task_display = None
        self.is_monitoring = False
        
        # UI components
        self.container: Optional[toga.Box] = None
    
    def create(self) -> toga.Box:
        """Create the progress display UI (initially empty)"""
        self.container = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=(20, 20, 20, 20),
                flex=1
            )
        )
        
        return self.container
    
    def start_processing(self, folder_path: Path, output_path: Path, plan_name: str, workflow_name: str):
        """Start processing and show progress display"""
        try:
            # Get director service
            if not hasattr(self.app, 'director') or not self.app.director:
                raise Exception("Director service not available")
            
            director = self.app.director
            
            # Submit tasks for processing
            self.current_task_ids = director.process_with_auto_detection(
                input_path=folder_path,
                output_path=output_path,
                plan_name=plan_name,
                workflow_name=workflow_name,
                document_context={
                    "document_window": self,
                    "document_id": f"processing_{folder_path.name}"
                }
            )
            
            if not self.current_task_ids:
                raise Exception("No tasks were submitted")
            
            logger.info(f"Submitted {len(self.current_task_ids)} tasks for processing")
            
            # Create and show GUI task display
            self._create_task_display()
            
            # Start monitoring task completion
            asyncio.create_task(self._monitor_task_completion())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start processing: {e}")
            return False
    
    def _create_task_display(self):
        """Create and show GUI task display"""
        try:
            from fichero.director.monitoring.displays.gui_display import GUITaskDisplay
            from fichero.director.monitoring.task_monitor import TaskMonitor
            
            # Get director and task monitor
            director = getattr(self.app, 'director', None)
            if director is None:
                components = getattr(self.app, 'components', {})
                director = components.get('director')
            
            if director is None:
                raise RuntimeError("Director not available")
            
            # Create task display filtered for this processing session
            task_monitor = TaskMonitor.get_instance(director)
            self.task_display = GUITaskDisplay(
                task_monitor,
                app=self.app,
                filter_document_id=f"processing_{id(self)}"
            )
            
            # Clear container and add task display
            self.container.clear()
            self.container.add(self.task_display.container)
            
            # Start monitoring
            self.task_display.start_monitoring()
            self.is_monitoring = True
            
            logger.info("Created task display for processing")
            
        except Exception as e:
            logger.error(f"Failed to create task display: {e}")
            raise
    
    async def _monitor_task_completion(self):
        """Monitor task completion in background"""
        if not self.current_task_ids:
            return
        
        director = self.app.director
        
        while self.is_monitoring:
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
                    # All tasks completed
                    completed_tasks = sum(1 for s in statuses if s == "SUCCESS")
                    failed_tasks = sum(1 for s in statuses if s == "FAILED")
                    cancelled_tasks = sum(1 for s in statuses if s == "CANCELLED")
                    
                    self._stop_monitoring()
                    
                    # Notify completion
                    if self.on_processing_complete:
                        self.on_processing_complete(completed_tasks, failed_tasks, cancelled_tasks)
                    
                    break
                
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"Error monitoring tasks: {e}")
                self._stop_monitoring()
                break
    
    def stop_processing(self):
        """Stop current processing"""
        try:
            if not self.current_task_ids:
                return 0, 0  # completed, failed
            
            director = self.app.director
            completed_tasks = 0
            failed_tasks = 0
            
            # Get status before cancelling
            for task_id in self.current_task_ids:
                try:
                    status = director.get_task_status(task_id)
                    if status and hasattr(status, 'value'):
                        if status.value == "SUCCESS":
                            completed_tasks += 1
                        elif status.value == "FAILED":
                            failed_tasks += 1
                    
                    # Cancel the task
                    director.cancel_task(task_id)
                    logger.info(f"Cancelled task: {task_id}")
                except Exception as e:
                    logger.warning(f"Could not cancel task {task_id}: {e}")
            
            # Stop monitoring
            self._stop_monitoring()
            
            # Notify stopped
            if self.on_processing_stopped:
                self.on_processing_stopped(completed_tasks, failed_tasks)
            
            return completed_tasks, failed_tasks
            
        except Exception as e:
            logger.error(f"Error stopping processing: {e}")
            return 0, 0
    
    def _stop_monitoring(self):
        """Stop monitoring tasks"""
        self.is_monitoring = False
        
        if self.task_display:
            self.task_display.stop_monitoring()
        
        self.current_task_ids = []
    
    def show_completion_message(self, completed_tasks: int, failed_tasks: int, output_path: Optional[Path] = None):
        """Show completion message"""
        # Clear container
        self.container.clear()
        
        # Create completion message
        completion_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                align_items=CENTER,
                margin=20
            )
        )
        
        # Title
        title_label = toga.Label(
            "✅ Processing Complete",
            style=Pack(
                font_size=16,
                font_weight='bold',
                color='#4CAF50',
                margin_bottom=15
            )
        )
        completion_container.add(title_label)
        
        # Results summary
        total_tasks = completed_tasks + failed_tasks
        if total_tasks > 0:
            results_text = f"📊 Results: {completed_tasks} completed"
            if failed_tasks > 0:
                results_text += f", {failed_tasks} failed"
        else:
            results_text = "✅ All tasks completed successfully"
            
        results_label = toga.Label(
            results_text,
            style=Pack(
                font_size=12,
                margin_bottom=10,
                text_align=CENTER
            )
        )
        completion_container.add(results_label)
        
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
            completion_container.add(output_label)
        
        # Action buttons
        button_container = toga.Box(
            style=Pack(direction=ROW, margin_top=10)
        )
        
        # View Output button (if output exists)
        if output_path and output_path.exists():
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
        
        completion_container.add(button_container)
        
        # Add to container
        self.container.add(completion_container)
    
    def show_stopped_message(self, completed_tasks: int, failed_tasks: int, output_path: Optional[Path] = None):
        """Show stopped message"""
        # Clear container
        self.container.clear()
        
        # Create stopped message
        stopped_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                align_items=CENTER,
                margin=20
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
        if output_path and output_path.exists():
            view_output_btn = toga.Button(
                "📁 View Output",
                on_press=lambda w: self._open_output_folder(output_path),
                style=Pack(margin_right=10)
            )
            button_container.add(view_output_btn)
        
        # Activity Monitor button
        activity_btn = toga.Button(
            "📊 Activity Monitor",
            on_press=lambda w: self._open_activity_monitor()
        )
        button_container.add(activity_btn)
        
        stopped_container.add(button_container)
        
        # Add to container
        self.container.add(stopped_container)
    
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
            if hasattr(self.app, 'show_activity_monitor'):
                self.app.show_activity_monitor()
            else:
                logger.warning("Activity monitor not available")
        except Exception as e:
            logger.error(f"Failed to open activity monitor: {e}")
    
    def reset(self):
        """Reset progress display"""
        self._stop_monitoring()
        self.container.clear()
    
    def is_processing(self) -> bool:
        """Check if currently processing"""
        return bool(self.current_task_ids and self.is_monitoring) 