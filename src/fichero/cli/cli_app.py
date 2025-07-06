"""
Fichero CLI Application - Thin Wrapper

Lightweight CLI application that follows the same pattern as app.py.
Delegates initialization to core systems and command logic to organized modules.

Architecture:
- Thin wrapper pattern: CLI app delegates to core/app_initializer.py
- Command logic separated into organized modules
- Shared error handling and business logic with GUI
"""

import logging
import warnings
import typer
from typing import Optional
from rich.console import Console

# Suppress Toga/Rubicon deprecation warning about EventLoopPolicy
# This is a framework issue that will be fixed in future Toga versions
warnings.filterwarnings(
    "ignore", 
    message="Custom EventLoopPolicy instances have been deprecated by Python 3.14.*",
    category=DeprecationWarning,
    module="toga_cocoa.app"
)

from ..core.app_initializer import initialize_cli_app
from ..core.error_handler import create_cli_error_handler
from ..director import FicheroDirector
from .. import __version__

logger = logging.getLogger(__name__)


class FicheroCLI:
    """Thin wrapper CLI application - delegates to organized command modules"""
    
    # Application metadata (same as app.py pattern)
    name = "Fichero CLI"
    version = __version__
    description = "Multi-Step Document Processing"
    author = "Daniel Tubb"
    home_page = "https://www.tubb.ca/fichero/"
    
    def __init__(self):
        """Initialize CLI components (same pattern as app.py)"""
        print("🚀 Fichero CLI starting up...")
        
        # Initialize components using shared initializer (same as GUI)
        try:
            self.components, self.initializer = initialize_cli_app()
            
            # Extract core components (same subset as GUI gets)
            self.settings = self.components['settings']
            self.director = self.components['director']
            
            print("✅ Fichero CLI components initialized")
            
        except Exception as e:
            print(f"❌ Failed to initialize Fichero: {e}")
            import traceback
            traceback.print_exc()
            import sys
            sys.exit(1)
        
        # Set up CLI interface
        self._setup_cli_interface()
        print("✨ Fichero CLI ready!")
    
    def _setup_cli_interface(self):
        """Set up CLI interface - thin setup that delegates to command modules"""
        try:
            # Initialize CLI interface
            self.app = typer.Typer(help="Fichero - Multi-Step Document Processing")
            self.console = Console()
            
            # Set up version command
            self._setup_version_command()
            
            # Register command modules (organized and clean)
            self._register_commands()
            
        except Exception as e:
            print(f"⚠️ Warning: CLI interface setup failed: {e}")

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
        """Register all command modules - organized and maintainable"""
        # Import command modules
        from .commands.core_commands import CoreCommands
        from .commands.backend_commands import BackendCommands
        
        # Initialize command handlers with shared components
        core_commands = CoreCommands(self.director, self.console)
        backend_commands = BackendCommands(self.director, self.console)
        
        # Register core commands
        self.app.command()(core_commands.process)
        self.app.command()(core_commands.plans)
        self.app.command()(core_commands.configure)
        self.app.command()(core_commands.info)
        
        # Register backend subcommand group - always show all commands but check capabilities at runtime
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
        backend_app.command("activity-monitor")(backend_commands.activity_monitor)
        
        self.app.add_typer(backend_app, name="backend")

    def finalize(self):
        """Clean up when CLI closes - delegates to shared cleanup"""
        print("🔄 Fichero CLI closing...")
        try:
            if hasattr(self, 'initializer') and self.initializer:
                self.initializer.cleanup()
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")
            import traceback
            traceback.print_exc()


def main():
    """Main entry point with shared error handling"""
    cli_instance = FicheroCLI()
    error_handler = create_cli_error_handler(cli_instance.console)
    
    try:
        wrapped_app = error_handler.wrap_main_function(cli_instance.app, "CLI")
        wrapped_app()
    finally:
        cli_instance.finalize()


if __name__ == "__main__":
    main() 