"""
Core CLI Commands

Main application commands: process, list-plans, configure, info, activity-monitor
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
        workflow: str = typer.Option(None, "--workflow", "-w", help="Workflow to use"),
        backend: str = typer.Option("python", "--backend", "-b", help="Backend: python or celery/redis"),
        cpu_workers: int = typer.Option(None, "--cpu-workers", "-c", help="Number of CPU workers"),
        io_workers: int = typer.Option(None, "--io-workers", "-i", help="Number of I/O workers"),
    
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output")
    ):
        """Process folders with specified plan and workflow"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if verbose:
                self._enable_verbose_logging()
            
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                raise typer.Exit(1)
            
            # Configure backend if specified
            if backend != "python":
                self.console.print(f"🔧 Configuring backend: {backend}", style="cyan")
                self.director.configure_settings(
                    console=self.console,
                    backend=backend,
                    cpu_workers=cpu_workers,
                    io_workers=io_workers
                )
            
            # Validate input folder
            if not input_folder.exists():
                self.console.print(f"❌ Input folder does not exist: {input_folder}", style="red")
                raise typer.Exit(1)
            
            # Set output directory
            if output is None:
                output = input_folder / "output"
            
            output.mkdir(parents=True, exist_ok=True)
            
            # Get default settings
            from ...config.core.settings import get_app_settings
            app_settings = get_app_settings(self.director.app if hasattr(self.director, 'app') else None)
            
            # Determine plan name
            if plan is None:
                # Get default plan from settings
                plan_name = app_settings.get_setting('defaults.plan', 'Catalogue')
            else:
                if not plan.exists():
                    self.console.print(f"❌ Plan file does not exist: {plan}", style="red")
                    raise typer.Exit(1)
                plan_name = plan.stem
            
            # Determine workflow name
            if workflow is None:
                # Get default workflow from settings
                workflow = app_settings.get_setting('defaults.workflow', '00) default')
            
            # Show processing info
            self.console.print(f"📁 Input: {input_folder}", style="cyan")
            self.console.print(f"📁 Output: {output}", style="cyan")
            self.console.print(f"📋 Plan: {plan_name}", style="cyan")
            self.console.print(f"🔄 Workflow: {workflow}", style="cyan")
            self.console.print(f"⚙️ Backend: {backend}", style="cyan")
            
            if cpu_workers:
                self.console.print(f"🔧 CPU Workers: {cpu_workers}", style="cyan")
            if io_workers:
                self.console.print(f"🔧 I/O Workers: {io_workers}", style="cyan")
            
            self.console.print()
            
            # Submit tasks
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
                # Show table display
                from ...director.monitoring.displays.cli_display import CLITaskDisplay
                
                task_monitor = self.director.get_task_monitor()
                cli_display = CLITaskDisplay(self.console, task_monitor)
                
                # Small delay to allow tasks to be registered
                time.sleep(0.1)
                
                self.console.print(f"🚀 Processing {len(task_ids)} task{'s' if len(task_ids) != 1 else ''}...", style="bold blue")
                self.console.print()
                
                # Show table and wait for completion
                try:
                    cli_display.show_tasks(filter_current_only=True)
                    success = self._check_all_tasks_completion(task_ids)
                except KeyboardInterrupt:
                    self.console.print("\n👋 Task monitoring stopped", style="yellow")
                    success = self._check_all_tasks_completion(task_ids)
                except Exception as e:
                    logger.warning(f"Table display failed: {e}")
                    success = self._monitor_tasks_simple(task_ids)
                
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

    def plans(self):
        """List available processing plans with workflows and steps"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            self.director.display_available_plans(self.console)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "plan listing", verbose=True)

    def configure(self,
        # Display options
        show: bool = typer.Option(False, "--show", help="Show current configuration"),
        show_api_keys: bool = typer.Option(False, "--show-api-keys", help="Show current configuration including API keys"),
        help_options: bool = typer.Option(False, "--help-options", help="Show all available configuration options"),
        
        # Backend and performance
        backend: str = typer.Option(None, "--backend", "-b", help="Set backend: python or celery/redis"),
        cpu_workers: int = typer.Option(None, "--cpu-workers", "-c", help="Number of CPU workers (1-32)"),
        io_workers: int = typer.Option(None, "--io-workers", "-i", help="Number of I/O workers (1-128)"),
        auto: bool = typer.Option(False, "--auto", "-a", help="Auto-configure optimal settings"),
        
        # API Keys
        openai_key: str = typer.Option(None, "--openai-key", help="Set OpenAI API key"),
        qwen_key: str = typer.Option(None, "--qwen-key", help="Set Qwen API key"),
        claude_key: str = typer.Option(None, "--claude-key", help="Set Claude API key"),
        huggingface_key: str = typer.Option(None, "--huggingface-key", help="Set Hugging Face API key"),
        
        # Preferences
        language: str = typer.Option(None, "--language", help="Set interface language (en, es, fr)"),
        folder_order: str = typer.Option(None, "--folder-order", help="Set folder processing order"),
        
        # Defaults
        default_plan: str = typer.Option(None, "--default-plan", help="Set default plan for processing"),
        default_workflow: str = typer.Option(None, "--default-workflow", help="Set default workflow for processing"),
        
        # Legacy options (for backward compatibility)
        plan: str = typer.Option(None, "--plan", help="Set default plan (legacy)"),
        workflow: str = typer.Option(None, "--workflow", help="Set default workflow (legacy)")
    ):
        """Configure application settings with comprehensive options"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            # Handle auto-configuration first
            if auto:
                self._auto_configure()
                return
            
            # Import and create settings commands
            from .settings_commands import CLISettingsCommands
            settings_commands = CLISettingsCommands(self.director, self.console)
            
            # Handle display options first
            if help_options:
                settings_commands.show_available_options()
                return
                
            if show:
                settings_commands.show_current_settings(show_api_keys=show_api_keys)
                return
                
            if show_api_keys and not show:
                settings_commands.show_current_settings(show_api_keys=True)
                return
            
            # Track if any settings were changed
            changes_made = False
            
            # Configure backend
            if backend:
                success = settings_commands.configure_backend(backend)
                changes_made = changes_made or success
            
            # Configure workers
            if cpu_workers is not None or io_workers is not None:
                success = settings_commands.configure_workers(cpu_workers, io_workers)
                changes_made = changes_made or success
            
            # Configure API keys
            if openai_key:
                success = settings_commands.configure_api_key('openai', openai_key)
                changes_made = changes_made or success
                
            if qwen_key:
                success = settings_commands.configure_api_key('qwen', qwen_key)
                changes_made = changes_made or success
                
            if claude_key:
                success = settings_commands.configure_api_key('claude', claude_key)
                changes_made = changes_made or success
                
            if huggingface_key:
                success = settings_commands.configure_api_key('huggingface', huggingface_key)
                changes_made = changes_made or success
            
            # Configure defaults
            if default_plan:
                success = settings_commands.configure_preference('defaults.plan', default_plan)
                changes_made = changes_made or success
                
            if default_workflow:
                success = settings_commands.configure_preference('defaults.workflow', default_workflow)
                changes_made = changes_made or success
            
            # Configure preferences
            if language:
                if language not in ['en', 'es', 'fr']:
                    self.console.print("❌ Invalid language. Choose: en, es, fr", style="red")
                else:
                    success = settings_commands.configure_preference('preferences.language', language)
                    changes_made = changes_made or success
            
            if folder_order:
                valid_orders = ['alphabetical', 'reverse_alphabetical', 'least_images_first', 'most_images_first']
                if folder_order not in valid_orders:
                    self.console.print(f"❌ Invalid folder order. Choose: {', '.join(valid_orders)}", style="red")
                else:
                    success = settings_commands.configure_preference('preferences.folder_processing_order', folder_order)
                    changes_made = changes_made or success
            
            # Handle legacy plan/workflow options
            if plan or workflow:
                # Use the old director method for plan/workflow
                self.director.configure_settings(
                    console=self.console,
                    show_defaults=False,
                    plan=plan,
                    workflow=workflow
                )
                changes_made = True
            
            # If no options provided, show current settings
            if not changes_made and not any([
                show, show_api_keys, help_options, backend, cpu_workers, io_workers,
                openai_key, qwen_key, claude_key, huggingface_key, language, folder_order, 
                default_plan, default_workflow, plan, workflow, auto
            ]):
                settings_commands.show_current_settings()
            
        except Exception as e:
            error_handler.handle_general_exception(e, "configuring settings", verbose=True)

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
        
            )
            
            self.console.print("✨ Auto-configuration complete!", style="bold green")
            
        except Exception as e:
            self.console.print(f"❌ Auto-configuration failed: {e}", style="red")

    def info(self):
        """Show comprehensive system information including available plans"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            self.director.display_system_info(self.console)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "system info", verbose=True)



    def _monitor_tasks_simple(self, task_ids):
        """Simple task monitoring without Rich displays"""
        self.console.print("⚡ Monitoring tasks with simple display...", style="blue")
        success = True
        
        # Get task monitor from director
        task_monitor = self.director.get_task_monitor()
        
        while True:
            # Check if all tasks are complete
            all_complete = True
            for task_id in task_ids:
                task_info = task_monitor.get_task(task_id)
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