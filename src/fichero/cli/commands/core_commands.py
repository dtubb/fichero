"""
Core CLI Commands

Main application commands: process, status, list-plans, configure, info, activity-monitor
Extracted from the main cli.py file for better organization.
"""

import logging
import time
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console

from ...core.error_handler import create_cli_error_handler
from ...director import FicheroDirector

logger = logging.getLogger(__name__)


class CoreCommands:
    """Core CLI commands handler"""
    
    def __init__(self, director, console: Console):
        self.director = director
        self.console = console
    
    def _enable_verbose_logging(self):
        """Enable verbose logging for CLI"""
        import logging
        
        # Reconfigure root logger to INFO level
        logging.getLogger().setLevel(logging.INFO)
        
        # Also configure specific loggers that we want to see
        for logger_name in [
            'fichero.director',
            'fichero.tools',
            'fichero.director.backends',
            'fichero.director.workflow_executor'
        ]:
            logging.getLogger(logger_name).setLevel(logging.INFO)
        
        logger.info("🔊 Verbose logging enabled")
    
    def process(self,
        input_folder: Path = typer.Argument(..., help="Input folder to process (auto-detects subfolders)"),
        plan: Optional[Path] = typer.Option(None, "--plan", "-p", help="Processing plan file (.yml) - uses default if not specified"),
        output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
        workflow: str = typer.Option("default", "--workflow", "-w", help="Workflow to use"),
        backend: str = typer.Option("python", "--backend", "-b", help="Backend: python or celery/redis"),
        cpu_workers: int = typer.Option(None, "--cpu-workers", "-c", help="Number of CPU workers"),
        io_workers: int = typer.Option(None, "--io-workers", "-i", help="Number of I/O workers"),
        memory_per_worker: int = typer.Option(None, "--memory-per-worker", "-m", help="Memory per worker in MB"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
        simple: bool = typer.Option(False, "--simple", help="Use simple progress display"),
        table_view: bool = typer.Option(False, "--table", "-t", help="Show all tasks in table format (for multiple folders)")
    ):
        """Process folders using app defaults or specified plan/workflow"""
        # Reconfigure logging if verbose mode is requested
        if verbose:
            self._enable_verbose_logging()
        
        error_handler = create_cli_error_handler(self.console)
        
        try:
            # Basic validation with helpful error messaging
            if not input_folder.exists():
                self.console.print(f"❌ Input folder does not exist: {input_folder}", style="red")
                
                # Check if this looks like a path splitting issue (common with spaces)
                input_str = str(input_folder)
                if ' ' in input_str and not (input_str.startswith('"') and input_str.endswith('"')):
                    self.console.print("💡 Tip: Paths with spaces need quotes, e.g.:", style="dim")
                    self.console.print(f'   python -m fichero process "{input_folder}"', style="dim")
                    self.console.print("   Or escape spaces with backslashes", style="dim")
                
                raise typer.Exit(1)
            
            if not self.director or not FicheroDirector.is_initialized():
                self.console.print("❌ Director service not initialized", style="red")
                raise typer.Exit(1)
            
            # Use unified helper for plan/workflow defaults
            from ...config.core.plan_workflow_ui_helper import PlanWorkflowUIHelper
            ui_helper = PlanWorkflowUIHelper(self.director.app)
            
            # Determine plan to use
            if plan is not None:
                if not plan.exists():
                    self.console.print(f"❌ Plan file does not exist: {plan}", style="red")
                    raise typer.Exit(1)
                plan_name = plan.stem
                self.console.print(f"📋 Using specified plan: {plan_name}", style="blue")
            else:
                defaults = ui_helper.get_cli_defaults()
                plan_name = defaults.get('plan')
                
                if not plan_name:
                    self.console.print("❌ No default plan set and no plan specified", style="red")
                    self.console.print("💡 Set defaults in Settings (fichero) or use --plan option", style="dim")
                    self.console.print("💡 Use 'fichero-cli list-plans' to see available plans", style="dim")
                    raise typer.Exit(1)
                
                self.console.print(f"📋 Using default plan: {plan_name}", style="blue")
            
            # Determine workflow to use
            if workflow == "default":
                if plan is None:
                    defaults = ui_helper.get_cli_defaults()
                    workflow = defaults.get('workflow') or "default"
                else:
                    workflow = ui_helper.get_app_default_workflow(plan_name) or "default"
            
            # Always show workflow being used
            self.console.print(f"⚙️ Using workflow: {workflow}", style="cyan")
            
            # Set default output directory if not provided
            if output is None:
                output = input_folder.parent / f"{input_folder.name}_output"
            
            # Proper separation: processing vs display
            if simple:
                # Simple mode: just submit and wait
                task_ids = self.director.process_with_auto_detection(
                    input_path=input_folder,
                    output_path=output,
                    plan_name=plan_name,
                    workflow_name=workflow
                )
                success = len(task_ids) > 0 if task_ids else False
            else:
                # Rich mode: separate processing from display (clean architecture!)
                self.console.print(f"🚀 Starting processing...", style="bold blue")
                self.console.print(f"📁 Input: {input_folder}", style="dim")
                self.console.print(f"📂 Output: {output}", style="dim")
                self.console.print()
                
                # 1. Submit tasks (processing responsibility)
                task_ids = self.director.process_with_auto_detection(
                    input_path=input_folder,
                    output_path=output,
                    plan_name=plan_name,
                    workflow_name=workflow
                )
                
                if not task_ids:
                    self.console.print("❌ No tasks were submitted", style="red")
                    success = False
                else:
                    # Use rich CLITaskDisplay for progress monitoring
                    from ...director.monitoring.displays.cli_display import CLITaskDisplay
                    
                    # Get the TaskMonitor from the director (not create a new one)
                    task_monitor = self.director.get_task_monitor()
                    cli_display = CLITaskDisplay(self.console, task_monitor)
                    
                    # Small delay to allow tasks to be registered in TaskMonitor
                    time.sleep(0.1)
                    
                    self.console.print(f"🚀 Processing {len(task_ids)} task{'s' if len(task_ids) != 1 else ''}...", style="bold blue")
                    self.console.print()
                    
                    # Choose display mode based on number of tasks and user preference
                    if len(task_ids) > 1 and table_view:
                        # Table view for multiple tasks
                        self.console.print("📊 Monitoring all tasks in table format - Press Ctrl+C to exit", style="cyan")
                        self.console.print()
                        
                        try:
                            # Use live activity monitor to show all tasks in table
                            cli_display.show_all_tasks(live_updates=True)
                            
                            # Check final results after monitoring stops
                            success = self._check_all_tasks_completion(task_ids)
                        except KeyboardInterrupt:
                            self.console.print("\n👋 Task monitoring stopped", style="yellow")
                            # Check results even if interrupted
                            success = self._check_all_tasks_completion(task_ids)
                        except Exception as e:
                            logger.warning(f"Table display failed: {e}")
                            # Fallback to individual task monitoring
                            success = self._monitor_tasks_individually(task_ids, cli_display)
                    else:
                        # Individual task monitoring (default)
                        success = self._monitor_tasks_individually(task_ids, cli_display)
                    
                    self.console.print()
            
            # Simple success/failure output
            if success:
                # Check if there are any failed tasks to show more accurate message
                failed_count = 0
                total_count = len(task_ids)
                
                for task_id in task_ids:
                    try:
                        if hasattr(self.director.backend, 'get_task_status'):
                            status = self.director.backend.get_task_status(task_id)
                            # Handle ProcessingStatus enum - get the string value
                            if hasattr(status, 'value'):
                                status = status.value
                            if status == 'failed':
                                failed_count += 1
                    except Exception:
                        # Task might be completed and cleaned up
                        pass
                
                if failed_count > 0:
                    self.console.print(f"⚠️ Processing completed with {failed_count} failed tasks", style="bold yellow")
                else:
                    self.console.print("✅ Processing completed successfully!", style="bold green")
            else:
                self.console.print("❌ Processing failed or had errors", style="red")
                raise typer.Exit(1)
            
        except KeyboardInterrupt:
            error_handler.handle_keyboard_interrupt()
        except Exception as e:
            error_handler.handle_general_exception(e, "processing", verbose)

    def status(self):
        """Show director status"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            self.director.display_status(self.console)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "status check", verbose=True)

    def list_plans(self):
        """List available processing plans"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            self.director.display_available_plans(self.console)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "plan listing", verbose=True)

    def configure(self,
        show_defaults: bool = typer.Option(False, "--show-defaults", help="Show default values"),
        auto: bool = typer.Option(False, "--auto", help="Auto-configure optimal settings for this system"),
        backend: str = typer.Option(None, "--backend", "-b", help="Set backend: python or celery/redis"),
        cpu_workers: int = typer.Option(None, "--cpu-workers", "-c", help="Set number of CPU workers"),
        io_workers: int = typer.Option(None, "--io-workers", "-i", help="Set number of I/O workers"),
        memory_per_worker: int = typer.Option(None, "--memory-per-worker", "-m", help="Set memory per worker in MB"),
        plan: str = typer.Option(None, "--plan", "-p", help="Set default plan"),
        workflow: str = typer.Option(None, "--workflow", "-w", help="Set default workflow")
    ):
        """Configure director settings and app defaults"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            # Handle auto-configuration
            if auto:
                self._auto_configure()
                return
            
            # Delegate to director
            self.director.configure_settings(
                console=self.console,
                show_defaults=show_defaults,
                backend=backend,
                cpu_workers=cpu_workers,
                io_workers=io_workers,
                memory_per_worker=memory_per_worker,
                plan=plan,
                workflow=workflow
            )
            
        except Exception as e:
            error_handler.handle_general_exception(e, "configuration", verbose=True)

    def _auto_configure(self):
        """Auto-configure optimal settings for this system"""
        try:
            self.console.print("🤖 Auto-configuring optimal settings for your system...", style="bold blue")
            
            # Import worker sizing
            from ...director.backends import get_optimal_workers, suggest_backend
            
            # Get optimal configuration
            suggested_backend = suggest_backend()
            config = get_optimal_workers(suggested_backend)
            
            # Show what we detected
            self.console.print(f"📊 System Analysis: {config.reasoning}", style="dim")
            
            # Apply the configuration
            self.director.configure_settings(
                console=self.console,
                backend=suggested_backend,
                cpu_workers=config.cpu_workers,
                io_workers=config.io_workers,
                memory_per_worker=config.memory_per_worker_mb
            )
            
            self.console.print("✨ Auto-configuration complete!", style="bold green")
            
        except Exception as e:
            self.console.print(f"❌ Auto-configuration failed: {e}", style="red")

    def info(self):
        """Show director system information"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            self.director.display_system_info(self.console)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "system info", verbose=True)

    def activity_monitor(self,
        static: bool = typer.Option(False, "--static", "-s", help="Show one-time snapshot instead of live monitoring"),
        refresh_seconds: int = typer.Option(1, "--refresh", "-r", help="Refresh interval in seconds (live mode only)")
    ):
        """Show global activity monitor - continuously displays until Ctrl+C"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            # Get the task monitor from director
            from ...director.monitoring import TaskMonitor
            from ...director.monitoring.displays.cli_display import CLITaskDisplay
            
            task_monitor = TaskMonitor.get_instance(self.director)
            cli_display = CLITaskDisplay(self.console, task_monitor)
            
            if static:
                # One-time snapshot mode - use the rich static display
                cli_display.show_all_tasks(live_updates=False)
            else:
                # Live monitoring mode - use Rich Live functionality
                self.console.print("🔄 Starting Live Activity Monitor - Press Ctrl+C to exit", style="bold blue")
                self.console.print("   Rich live updating display with progress bars and real-time stats", style="dim")
                self.console.print()
                
                # Use the built-in Rich Live display - much smoother!
                cli_display.show_all_tasks(live_updates=True)
                
        except KeyboardInterrupt:
            self.console.print("\n👋 Activity Monitor stopped", style="yellow")
        except Exception as e:
            error_handler.handle_general_exception(e, "activity monitor", verbose=True)

    def _monitor_tasks_individually(self, task_ids, cli_display):
        """Monitor tasks individually using a single live display"""
        if len(task_ids) == 1:
            # Single task - use simple progress display
            try:
                cli_display.show_task_progress(task_ids[0], live_updates=True)
                return self._check_all_tasks_completion(task_ids)
            except Exception as e:
                logger.warning(f"Rich display failed for single task: {e}")
                return self._monitor_tasks_simple(task_ids)
        else:
            # Multiple tasks - use table view to avoid Rich conflicts
            self.console.print("📊 Monitoring multiple tasks in table format", style="cyan")
            try:
                cli_display.show_all_tasks(live_updates=True)
                return self._check_all_tasks_completion(task_ids)
            except KeyboardInterrupt:
                self.console.print("\n👋 Task monitoring stopped", style="yellow")
                return self._check_all_tasks_completion(task_ids)
            except Exception as e:
                logger.warning(f"Table display failed: {e}")
                return self._monitor_tasks_simple(task_ids)
    
    def _monitor_tasks_simple(self, task_ids):
        """Simple task monitoring without Rich displays"""
        self.console.print("⚡ Monitoring tasks with simple display...", style="blue")
        success = True
        
        while True:
            # Check if all tasks are complete
            all_complete = True
            for task_id in task_ids:
                task_info = self.task_monitor.get_task(task_id)
                if task_info and not task_info.is_finished:
                    all_complete = False
                    break
            
            if all_complete:
                break
            
            time.sleep(1.0)  # Check every second
        
        return self._check_all_tasks_completion(task_ids)

    def _check_all_tasks_completion(self, task_ids):
        """Check if all tasks are complete (finished running)"""
        for task_id in task_ids:
            try:
                if hasattr(self.director.backend, 'get_task_status'):
                    status = self.director.backend.get_task_status(task_id)
                    # Handle ProcessingStatus enum - get the string value
                    if hasattr(status, 'value'):
                        status = status.value
                    # Only check if task is finished (completed, failed, or cancelled)
                    # Don't care about success/failure here - that's handled in main logic
                    if status not in ['completed', 'failed', 'cancelled']:
                        # Task still running or unknown status
                        return False
            except Exception:
                # Task might be completed and cleaned up - assume it's done
                pass
        return True 