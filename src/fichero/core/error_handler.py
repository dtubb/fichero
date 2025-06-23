"""
Fichero Shared Error Handler

Common error handling patterns for both GUI and CLI interfaces.
Eliminates duplicate exception handling code.
"""

import sys
import traceback
from typing import Optional, Callable


class FicheroErrorHandler:
    """Shared error handling for GUI and CLI"""
    
    def __init__(self, is_cli=False, console=None, initializer=None):
        self.is_cli = is_cli
        self.console = console
        self.initializer = initializer
    
    def handle_keyboard_interrupt(self):
        """Handle Ctrl+C interruption"""
        if self.is_cli and self.console:
            self.console.print("\n⚠️ Fichero interrupted by user", style="yellow")
        else:
            print("\n👋 Fichero interrupted by user")
        
        self._cleanup()
        if self.is_cli:
            import typer
            raise typer.Exit(1)
        else:
            sys.exit(0)
    
    def handle_general_exception(self, e: Exception, context: str = "operation", verbose: bool = False):
        """Handle general exceptions with consistent messaging"""
        if self.is_cli and self.console:
            self.console.print(f"❌ {context.capitalize()} failed: {e}", style="red")
        else:
            print(f"💥 Fichero {context} failed: {e}")
        
        if verbose or not self.is_cli:
            traceback.print_exc()
        
        self._cleanup()
        if self.is_cli:
            import typer
            raise typer.Exit(1)
        else:
            sys.exit(1)
    
    def _cleanup(self):
        """Perform cleanup if initializer is available"""
        if self.initializer:
            try:
                self.initializer.cleanup()
            except Exception as cleanup_error:
                if self.is_cli and self.console:
                    self.console.print(f"⚠️ Cleanup warning: {cleanup_error}", style="yellow")
                else:
                    print(f"⚠️ Cleanup warning: {cleanup_error}")
    
    def wrap_main_function(self, main_func: Callable, context: str = "application"):
        """
        Decorator-style wrapper for main functions with consistent error handling
        
        Usage:
            handler = FicheroErrorHandler(is_cli=True, console=console)
            handler.wrap_main_function(app, "CLI")()
        """
        def wrapper(*args, **kwargs):
            try:
                return main_func(*args, **kwargs)
            except KeyboardInterrupt:
                self.handle_keyboard_interrupt()
            except Exception as e:
                self.handle_general_exception(e, context, verbose=True)
        
        return wrapper


def create_cli_error_handler(console, initializer=None):
    """Create error handler for CLI"""
    return FicheroErrorHandler(is_cli=True, console=console, initializer=initializer)


def create_gui_error_handler(initializer=None):
    """Create error handler for GUI"""
    return FicheroErrorHandler(is_cli=False, initializer=initializer) 