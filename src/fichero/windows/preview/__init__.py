"""
Preview Window Module

Provides preview windows and views for both desktop and mobile platforms.
Handles file preview and editing capabilities.
"""

from fichero.windows.preview.preview_window import PreviewWindow
from fichero.windows.preview.mobile_view import PreviewMobileView

__all__ = [
    'PreviewWindow',
    'PreviewMobileView',
] 