"""
Shared Toolbar Components

Platform-specific toolbar implementations:
- Desktop: Uses Toga's native command system
- Mobile: Custom button-based toolbars (top for iOS, bottom for Android)
"""

from fichero.shared.toolbars.desktop_toolbar import DesktopToolbar
from fichero.shared.toolbars.mobile_toolbar import MobileToolbar

__all__ = [
    'DesktopToolbar',
    'MobileToolbar'
] 