"""
Backend Management CLI Commands

Backend worker management commands: select, info, start, stop, restart, status, health, purge, flush
Extracted from the main cli.py file for better organization.
"""

import logging
import typer
from rich.console import Console
from rich.table import Table

from ...core.error_handler import create_cli_error_handler

logger = logging.getLogger(__name__)


class BackendCommands:
    """Backend management CLI commands handler"""
    
    def __init__(self, director, console: Console):
        self.director = director
        self.console = console
    
    def select(self,
        backend: str = typer.Argument(..., help="Backend to select: python or celery/redis")
    ):
        """Select which backend to use"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if backend not in ['python', 'celery', 'redis']:  # Accept 'redis' as alias for 'celery'
                self.console.print("❌ Invalid backend. Choose 'python' or 'celery/redis'", style="red")
                raise typer.Exit(1)
            
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            # Normalize 'redis' to 'celery' for internal consistency
            normalized_backend = 'celery' if backend == 'redis' else backend
            
            # Use the same logic as configure command
            self.director.configure_settings(
                console=self.console,
                backend=normalized_backend
            )
            
        except Exception as e:
            error_handler.handle_general_exception(e, "selecting backend", verbose=True)
    
    def info(self):
        """Show backend availability and current selection"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            # Use director's unified backend info method
            backend_info = self.director.get_backend_info()
            availability = backend_info.get('availability', {})
            
            # Create backend info table
            table = Table(title="Backend Information")
            table.add_column("Backend", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Details", style="yellow")
            
            # Show availability for each backend
            for backend_name, backend_data in availability.items():
                status = "✅ Available" if backend_data['available'] else "❌ Unavailable"
                table.add_row(backend_name.title(), status, backend_data['details'])
            
            # Current configuration
            current_backend = backend_info.get('backend_name', 'unknown')
            table.add_row("", "", "")  # Separator
            table.add_row("Current", f"🎯 {current_backend.title()}", "Currently active backend")
            
            self.console.print(table)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "getting backend info", verbose=True)
    
    def start(self,
        cpu_workers: int = typer.Option(None, "--cpu", "-c", help="Number of CPU workers"),
        io_workers: int = typer.Option(None, "--io", "-i", help="Number of I/O workers")
    ):
        """Start backend workers"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            self.console.print("🚀 Starting backend workers...", style="yellow")
            
            # Use director's unified method
            success = self.director.start_backend_workers(cpu_workers, io_workers)
            backend_name = self.director.get_backend_info().get('backend_name', 'unknown')
            
            if success:
                self.console.print(f"✅ {backend_name.title()} backend workers started successfully", style="bold green")
            else:
                self.console.print(f"❌ Failed to start {backend_name} backend workers", style="red")
                raise typer.Exit(1)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "starting workers", verbose=True)

    def stop(self):
        """Stop backend workers"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            self.console.print("🛑 Stopping backend workers...", style="yellow")
            
            # Use director's unified method
            success = self.director.stop_backend_workers()
            backend_name = self.director.get_backend_info().get('backend_name', 'unknown')
            
            if success:
                self.console.print(f"✅ {backend_name.title()} backend workers stopped successfully", style="bold green")
            else:
                self.console.print(f"❌ Failed to stop {backend_name} backend workers", style="red")
                raise typer.Exit(1)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "stopping workers", verbose=True)

    def restart(self,
        cpu_workers: int = typer.Option(None, "--cpu", "-c", help="Number of CPU workers"),
        io_workers: int = typer.Option(None, "--io", "-i", help="Number of I/O workers")
    ):
        """Restart backend workers"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            self.console.print("🔄 Restarting backend workers...", style="yellow")
            
            # Use director's unified method
            success = self.director.restart_backend_workers(cpu_workers, io_workers)
            backend_name = self.director.get_backend_info().get('backend_name', 'unknown')
            
            if success:
                self.console.print(f"✅ {backend_name.title()} backend workers restarted successfully", style="bold green")
            else:
                self.console.print(f"❌ Failed to restart {backend_name} backend workers", style="red")
                raise typer.Exit(1)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "restarting workers", verbose=True)

    def status(self):
        """Show detailed backend worker status"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            # Use director's unified method
            backend_name = self.director.get_backend_info().get('backend_name', 'unknown')
            worker_status = self.director.get_backend_worker_status()
            
            if not worker_status:
                self.console.print(f"❌ Backend {backend_name} does not support worker status", style="red")
                raise typer.Exit(1)
            
            # Create worker status table
            table = Table(title=f"{backend_name.title()} Backend Worker Status")
            table.add_column("Component", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Details", style="yellow")
            
            # Backend type
            table.add_row("Backend Type", backend_name.title(), "")
            
            # Redis status (for Celery backend)
            if 'redis_running' in worker_status:
                redis_status = "✅ Running" if worker_status['redis_running'] else "❌ Not Running"
                table.add_row("Redis", redis_status, "")
            
            # Worker summary
            summary = worker_status.get('summary', {})
            if summary:
                total_workers = summary.get('total_workers', 0)
                active_tasks = summary.get('active_tasks', 0)
                table.add_row("Workers", f"{total_workers} total", f"{active_tasks} active tasks")
            
            # Python backend specific info
            if 'cpu_workers' in worker_status:
                cpu_info = worker_status['cpu_workers']
                if isinstance(cpu_info, dict):
                    cpu_status = "✅ Active" if cpu_info.get('active', False) else "❌ Inactive"
                    table.add_row("CPU Workers", cpu_status, f"{cpu_info.get('count', 0)} workers ({cpu_info.get('type', 'Unknown')})")
            
            if 'io_workers' in worker_status:
                io_info = worker_status['io_workers']
                if isinstance(io_info, dict):
                    io_status = "✅ Active" if io_info.get('active', False) else "❌ Inactive"
                    table.add_row("IO Workers", io_status, f"{io_info.get('count', 0)} workers ({io_info.get('type', 'Unknown')})")
            
            # Individual workers (Celery backend)
            workers = worker_status.get('workers', {})
            for worker_name, worker_info in workers.items():
                status = worker_info.get('status', 'unknown')
                active_tasks = worker_info.get('active_tasks', 0)
                processed = worker_info.get('processed', 0)
                table.add_row(f"  {worker_name}", status.title(), f"{active_tasks} active, {processed} processed")
            
            self.console.print(table)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "getting worker status", verbose=True)

    def health(self):
        """Perform backend health check"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            # Use director's unified method
            backend_name = self.director.get_backend_info().get('backend_name', 'unknown')
            health_info = self.director.check_backend_health()
            
            if not health_info or 'healthy' not in health_info:
                self.console.print(f"❌ Backend {backend_name} does not support health checks", style="red")
                raise typer.Exit(1)
            
            # Create health check table
            table = Table(title=f"{backend_name.title()} Backend Health Check")
            table.add_column("Check", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Message", style="yellow")
            
            # Overall health
            overall_health = "✅ Healthy" if health_info.get('healthy', False) else "❌ Unhealthy"
            table.add_row("Overall", overall_health, "")
            
            # Individual checks
            checks = health_info.get('checks', {})
            for check_name, check_info in checks.items():
                status = check_info.get('status', 'unknown')
                message = check_info.get('message', '')
                
                status_icon = "✅" if status == "pass" else "❌"
                table.add_row(f"  {check_name.title()}", f"{status_icon} {status.title()}", message)
            
            self.console.print(table)
            
            # Exit with error code if unhealthy
            if not health_info.get('healthy', False):
                raise typer.Exit(1)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "performing health check", verbose=True)

    def purge(self):
        """Purge all pending tasks from backend queues"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            self.console.print("🧹 Purging all pending tasks...", style="yellow")
            
            # Use director's unified method
            success = self.director.purge_backend_tasks()
            backend_name = self.director.get_backend_info().get('backend_name', 'unknown')
            
            if success:
                self.console.print(f"✅ All tasks purged from {backend_name} backend successfully", style="bold green")
            else:
                self.console.print(f"❌ Failed to purge tasks from {backend_name} backend", style="red")
                raise typer.Exit(1)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "purging tasks", verbose=True)

    def flush(self):
        """Flush Redis database (Celery backend only)"""
        error_handler = create_cli_error_handler(self.console)
        
        try:
            if not self.director:
                self.console.print("❌ Director not available", style="red")
                return
            
            # Check if we're using Celery backend
            backend_info = self.director.get_backend_info()
            backend_name = backend_info.get('backend_name', 'unknown')
            
            if backend_name != 'celery':
                self.console.print("⚠️  Redis flush only works with Celery/Redis backend", style="yellow")
                return
            
            self.console.print("🧹 Flushing Redis database...", style="yellow")
            
            try:
                # Import redis and flush
                import redis
                r = redis.Redis(host='localhost', port=6379, db=0)
                r.flushdb()
                
                self.console.print("✅ Redis database flushed successfully", style="bold green")
                
            except ImportError:
                self.console.print("❌ Redis package not available", style="red")
                raise typer.Exit(1)
            
        except Exception as e:
            error_handler.handle_general_exception(e, "flushing Redis", verbose=True) 