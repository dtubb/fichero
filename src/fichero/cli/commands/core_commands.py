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

from fichero.core.error_handler import create_cli_error_handler
from fichero.director import FicheroDirector

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
        plan: Optional[str] = typer.Option(None, "--plan", "-p", help="Plan name or path to .yml file - uses default if not specified"),
        output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
        workflow: str = typer.Option(None, "--workflow", "-w", help="Workflow to use"),
        backend: str = typer.Option("python", "--backend", "-b", help="Backend: python or celery/redis"),
        cpu_workers: int = typer.Option(None, "--cpu-workers", "-c", help="Number of CPU workers"),
        io_workers: int = typer.Option(None, "--io-workers", "-i", help="Number of I/O workers"),
        dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Test mode - show what would be processed without actually processing"),
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
            from fichero.config.core.settings import get_app_settings
            app_settings = get_app_settings(self.director.app if hasattr(self.director, 'app') else None)

            # Determine plan name
            if plan is None:
                # Get default plan from settings
                plan_name = app_settings.get_setting('defaults.plan', 'Default')
            else:
                # Check if it's a path or a name
                plan_path = Path(plan)
                if plan_path.exists() and plan_path.suffix == '.yml':
                    # It's a path to a plan file
                    plan_name = plan_path.stem
                else:
                    # It's a plan name
                    plan_name = plan
            
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

            if dry_run:
                self.console.print(f"🧪 Mode: DRY RUN (no actual processing)", style="bold yellow")

            self.console.print()

            # Dry-run mode: scan and show what would be processed
            if dry_run:
                self._show_dry_run_preview(input_folder, plan_name, workflow)
                self.console.print("\n✅ Dry-run complete - no files were modified", style="bold green")
                return

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
                from fichero.director.monitoring.displays.cli_display import CLITaskDisplay
                
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

    def process_list(self,
        list_file: Path = typer.Argument(..., help="Text file containing paths to process (one per line)"),
        plan: Optional[str] = typer.Option(None, "--plan", "-p", help="Plan name or path to .yml file - uses default if not specified"),
        output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
        workflow: str = typer.Option(None, "--workflow", "-w", help="Workflow to use"),
        backend: str = typer.Option("python", "--backend", "-b", help="Backend: python or celery/redis"),
        cpu_workers: int = typer.Option(None, "--cpu-workers", "-c", help="Number of CPU workers"),
        io_workers: int = typer.Option(None, "--io-workers", "-i", help="Number of I/O workers"),
        dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Test mode - show what would be processed without actually processing"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output")
    ):
        """Process files and folders from a list file (supports both files AND folders)"""
        error_handler = create_cli_error_handler(self.console)

        try:
            if verbose:
                self._enable_verbose_logging()

            if not self.director:
                self.console.print("❌ Director not available", style="red")
                raise typer.Exit(1)

            # Validate list file exists
            if not list_file.exists():
                self.console.print(f"❌ List file does not exist: {list_file}", style="red")
                raise typer.Exit(1)

            # Read paths from list file
            self.console.print(f"📄 Reading paths from: {list_file}", style="cyan")

            with open(list_file, 'r') as f:
                raw_lines = f.readlines()

            # Parse paths, skip empty lines and comments
            paths = []
            for line in raw_lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    path = Path(line)
                    if path.exists():
                        paths.append(path)
                    else:
                        self.console.print(f"⚠️ Path does not exist (skipping): {path}", style="yellow")

            if not paths:
                self.console.print("❌ No valid paths found in list file", style="red")
                raise typer.Exit(1)

            # Categorize paths into files and folders
            files = [p for p in paths if p.is_file()]
            folders = [p for p in paths if p.is_dir()]

            self.console.print(f"📋 Found {len(paths)} valid paths:", style="bold green")
            self.console.print(f"  • {len(files)} individual files", style="cyan")
            self.console.print(f"  • {len(folders)} folders", style="cyan")
            self.console.print()

            # Configure backend if specified
            if backend != "python":
                self.console.print(f"🔧 Configuring backend: {backend}", style="cyan")
                self.director.configure_settings(
                    console=self.console,
                    backend=backend,
                    cpu_workers=cpu_workers,
                    io_workers=io_workers
                )

            # Get default settings
            from fichero.config.core.settings import get_app_settings
            app_settings = get_app_settings(self.director.app if hasattr(self.director, 'app') else None)

            # Determine plan name
            if plan is None:
                plan_name = app_settings.get_setting('defaults.plan', 'Default')
            else:
                plan_path = Path(plan)
                if plan_path.exists() and plan_path.suffix == '.yml':
                    plan_name = plan_path.stem
                else:
                    plan_name = plan

            # Determine workflow name
            if workflow is None:
                workflow = app_settings.get_setting('defaults.workflow', '00) default')

            # Set output directory (use first path's parent if not specified)
            if output is None:
                output = paths[0].parent / "output"

            output.mkdir(parents=True, exist_ok=True)

            # Show processing info
            self.console.print(f"📁 Output: {output}", style="cyan")
            self.console.print(f"📋 Plan: {plan_name}", style="cyan")
            self.console.print(f"🔄 Workflow: {workflow}", style="cyan")
            self.console.print(f"⚙️ Backend: {backend}", style="cyan")

            if cpu_workers:
                self.console.print(f"🔧 CPU Workers: {cpu_workers}", style="cyan")
            if io_workers:
                self.console.print(f"🔧 I/O Workers: {io_workers}", style="cyan")

            if dry_run:
                self.console.print(f"🧪 Mode: DRY RUN (no actual processing)", style="bold yellow")

            self.console.print()

            # Dry-run mode: show what would be processed
            if dry_run:
                self._show_list_dry_run_preview(files, folders, plan_name, workflow)
                self.console.print("\n✅ Dry-run complete - no files were modified", style="bold green")
                return

            # Process each path
            all_task_ids = []

            # Process individual files
            if files:
                self.console.print(f"📄 Processing {len(files)} individual files...", style="bold blue")
                for file_path in files:
                    self.console.print(f"  • {file_path.name}", style="dim")
                    # For individual files, we'll use the Director's file processing
                    # Note: This may need adjustment based on Director API
                    try:
                        task_ids = self.director.process_with_auto_detection(
                            input_path=file_path.parent,
                            output_path=output,
                            plan_name=plan_name,
                            workflow_name=workflow
                        )
                        if task_ids:
                            all_task_ids.extend(task_ids)
                    except Exception as e:
                        self.console.print(f"    ⚠️ Failed to process {file_path.name}: {e}", style="yellow")
                self.console.print()

            # Process folders
            if folders:
                self.console.print(f"📁 Processing {len(folders)} folders...", style="bold blue")
                for folder_path in folders:
                    self.console.print(f"  • {folder_path.name}/", style="dim")
                    try:
                        task_ids = self.director.process_with_auto_detection(
                            input_path=folder_path,
                            output_path=output,
                            plan_name=plan_name,
                            workflow_name=workflow
                        )
                        if task_ids:
                            all_task_ids.extend(task_ids)
                    except Exception as e:
                        self.console.print(f"    ⚠️ Failed to process {folder_path.name}: {e}", style="yellow")
                self.console.print()

            if not all_task_ids:
                self.console.print("❌ No tasks were submitted", style="red")
                success = False
            else:
                # Show table display
                from fichero.director.monitoring.displays.cli_display import CLITaskDisplay

                task_monitor = self.director.get_task_monitor()
                cli_display = CLITaskDisplay(self.console, task_monitor)

                # Small delay to allow tasks to be registered
                time.sleep(0.1)

                self.console.print(f"🚀 Processing {len(all_task_ids)} task{'s' if len(all_task_ids) != 1 else ''}...", style="bold blue")
                self.console.print()

                # Show table and wait for completion
                try:
                    cli_display.show_tasks(filter_current_only=True)
                    success = self._check_all_tasks_completion(all_task_ids)
                except KeyboardInterrupt:
                    self.console.print("\n👋 Task monitoring stopped", style="yellow")
                    success = self._check_all_tasks_completion(all_task_ids)
                except Exception as e:
                    logger.warning(f"Table display failed: {e}")
                    success = self._monitor_tasks_simple(all_task_ids)

                self.console.print()

            # Simple success/failure output
            if success:
                failed_count = 0
                total_count = len(all_task_ids)

                for task_id in all_task_ids:
                    try:
                        if hasattr(self.director.backend, 'get_task_status'):
                            status = self.director.backend.get_task_status(task_id)
                            if hasattr(status, 'value'):
                                status = status.value
                            if status == 'failed':
                                failed_count += 1
                    except Exception:
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
            error_handler.handle_general_exception(e, "list processing", verbose)

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
            from fichero.settings_commands import CLISettingsCommands
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
            from fichero.director.backends import get_optimal_workers, suggest_backend
            
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

    def _show_dry_run_preview(self, input_path: Path, plan_name: str, workflow_name: str):
        """Show what would be processed in dry-run mode"""
        from fichero.tools.utils.files import get_image_files

        self.console.print("🔍 Scanning for files to process...\n", style="cyan")

        # Scan for image files recursively
        image_files = get_image_files(input_path)

        if not image_files:
            self.console.print("❌ No image files found", style="red")
            return

        # Group by directory
        by_dir = {}
        for img_path in image_files:
            dir_path = img_path.parent
            if dir_path not in by_dir:
                by_dir[dir_path] = []
            by_dir[dir_path].append(img_path)

        # Display summary
        self.console.print(f"📊 Found {len(image_files)} image files in {len(by_dir)} directories:\n", style="bold green")

        for dir_path, files in sorted(by_dir.items()):
            rel_path = dir_path.relative_to(input_path) if dir_path != input_path else Path(".")
            self.console.print(f"  📁 {rel_path}/ ({len(files)} files)", style="cyan")
            if len(files) <= 5:
                for f in files:
                    self.console.print(f"     • {f.name}", style="dim")
            else:
                for f in files[:3]:
                    self.console.print(f"     • {f.name}", style="dim")
                self.console.print(f"     • ... and {len(files) - 3} more", style="dim")
            self.console.print()

        self.console.print(f"\n📋 Would process with:", style="bold")
        self.console.print(f"  • Plan: {plan_name}", style="cyan")
        self.console.print(f"  • Workflow: {workflow_name}", style="cyan")

    def _show_list_dry_run_preview(self, files: list, folders: list, plan_name: str, workflow_name: str):
        """Show what would be processed from a list in dry-run mode"""
        from fichero.tools.utils.files import get_image_files

        self.console.print("🔍 Analyzing paths from list...\n", style="cyan")

        # Show individual files
        if files:
            self.console.print(f"📄 Individual files ({len(files)}):", style="bold cyan")
            for file_path in files:
                self.console.print(f"  • {file_path}", style="dim")
            self.console.print()

        # Show folders and scan for images
        if folders:
            self.console.print(f"📁 Folders ({len(folders)}):", style="bold cyan")
            total_images = 0
            for folder_path in folders:
                image_files = get_image_files(folder_path)
                total_images += len(image_files)
                self.console.print(f"  • {folder_path}/ ({len(image_files)} images)", style="dim")
            self.console.print()
            self.console.print(f"📊 Total images in folders: {total_images}", style="bold green")
            self.console.print()

        self.console.print(f"📋 Would process with:", style="bold")
        self.console.print(f"  • Plan: {plan_name}", style="cyan")
        self.console.print(f"  • Workflow: {workflow_name}", style="cyan") 