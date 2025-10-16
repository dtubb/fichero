"""
Unified Command System for Fichero

Provides a consistent, platform-adaptive way to define and execute commands across:
- Native platform menus (desktop with keyboard shortcuts)
- Custom toolbar buttons (both platforms)
- Direct keyboard shortcuts (desktop only)

Commands are registered once and can be exposed differently on desktop vs mobile.
"""

from .command import FicheroCommand
from .registry import CommandRegistry
from .command_manager import CommandManager
from .view_mixin import ViewCommandMixin

__all__ = ['FicheroCommand', 'CommandRegistry', 'CommandManager', 'ViewCommandMixin']
