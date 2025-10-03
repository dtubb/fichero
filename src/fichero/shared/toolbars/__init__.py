"""
Shared Toolbar Utilities for Fichero

Provides base toolbar classes and platform-specific utilities.
View-specific toolbars are in their respective view packages.
"""

from fichero.shared.toolbars.toolbar_coordinator import ToolbarCoordinator, EditModeState, ToolbarProtocol
from fichero.shared.toolbars.base_toolbar import BaseToolbar
from fichero.shared.toolbars.top_toolbar import TopToolbar
from fichero.shared.toolbars.bottom_toolbar import BottomToolbar
from fichero.shared.toolbars.color_constants import *

__all__ = [
    'ToolbarCoordinator',
    'EditModeState',
    'ToolbarProtocol',
    'BaseToolbar',
    'TopToolbar',
    'BottomToolbar'
] 