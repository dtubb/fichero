"""
CLI Commands Module

Organized command classes for better maintainability.
Each command group has its own module following the thin wrapper pattern.
"""

from fichero.core_commands import CoreCommands
from fichero.backend_commands import BackendCommands

__all__ = ['CoreCommands', 'BackendCommands'] 