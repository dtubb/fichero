import os
os.environ["TOGA_BACKEND"] = "toga_textual"
"""
Fichero CLI Application
Handles command-line interface for Fichero
"""

import typer
from typing import Optional
import logging
from rich.console import Console

from fichero.core.app_initializer import FicheroAppInitializer
from fichero.cli.commands.core_commands import CoreCommands
from fichero.cli.commands.backend_commands import BackendCommands
from fichero.cli.commands.library import LibraryCommands

# Get version from package
try:
    from importlib.metadata import version
    __version__ = version("fichero")
except ImportError:
    __version__ = "0.1.0"

logger = logging.getLogger(__name__)

class CLIApp:
    """Main CLI application class"""
    
    def __init__(self):
        """Initialize CLI application"""
        self.console = Console()
        self.app = typer.Typer(
            name="fichero",
            help="Fichero - Document Processing System",
            add_completion=False
        )
        
        # Initialize app components
        self.app_initializer = FicheroAppInitializer()
        self.director = self.app_initializer.director
        
        # Set up version command
        self._setup_version_command()
        
        # Register commands
        self._register_commands()

        # Add textual command
        self._setup_textual_command()
    
    def _setup_version_command(self):
        """Set up --version flag"""
        def version_callback(value: bool):
            if value:
                self.console.print(f"Fichero CLI version: {__version__}")
                raise typer.Exit()

        @self.app.callback()
        def main_callback(
            version: Optional[bool] = typer.Option(
                None, 
                "--version", 
                callback=version_callback,
                is_eager=True,
                help="Show version and exit"
            )
        ):
            """Fichero Director - Document Processing System"""
            pass

    def _register_commands(self):
        """Register all command modules"""
        try:
            # Initialize command handlers
            core_commands = CoreCommands(self.director, self.console)
            backend_commands = BackendCommands(self.director, self.console)
            library_commands = LibraryCommands(self.app_initializer)
            
            # Register core commands
            self.app.command()(core_commands.process)
            self.app.command()(core_commands.plans)
            self.app.command()(core_commands.configure)
            self.app.command()(core_commands.info)
            
            # Register library commands using the Typer app
            self.app.add_typer(library_commands.app, name="library")
            
            # Register backend commands
            backend_app = typer.Typer(help="Backend management commands")
            backend_app.command("select")(backend_commands.select)
            backend_app.command("info")(backend_commands.info)
            backend_app.command("start")(backend_commands.start_with_capability_check)
            backend_app.command("stop")(backend_commands.stop_with_capability_check)
            backend_app.command("restart")(backend_commands.restart_with_capability_check)
            backend_app.command("status")(backend_commands.status_with_capability_check)
            backend_app.command("health")(backend_commands.health_with_capability_check)
            backend_app.command("purge")(backend_commands.purge_with_capability_check)
            backend_app.command("flush")(backend_commands.flush_with_capability_check)
            
            self.app.add_typer(backend_app, name="backend")
            
        except Exception as e:
            logger.error(f"Failed to register commands: {e}")

    def _setup_textual_command(self):
        """Set up textual interface command"""
        @self.app.command()
        def textual():
            """Launch interactive textual interface for navigation testing"""
            import asyncio
            from fichero.textual_app import main as textual_main

            self.console.print("🔧 Starting Fichero Textual Interface...")
            asyncio.run(textual_main())

    def run(self):
        """Run the CLI application"""
        try:
            self.app()
        finally:
            # Cleanup
            self.app_initializer.cleanup()

# Create global app instance
app = CLIApp()

def main():
    """Main entry point for CLI"""
    app.run()

if __name__ == "__main__":
    main()

# Export for backward compatibility
FicheroCLI = CLIApp
