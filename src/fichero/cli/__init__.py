"""
Fichero CLI Module

Organized CLI commands following the thin wrapper architecture pattern.
Each command group is in its own module for maintainability.
"""

from fichero.cli_app import FicheroCLI, main

# Expose app function for backward compatibility with __main__.py
def app():
    """CLI app entry point for backward compatibility"""
    main()

__all__ = ['FicheroCLI', 'app', 'main'] 