"""
Add Option Views Package

Individual views for each add option, following BaseView pattern.
Each view handles a specific type of content addition with proper navigation.
"""

from fichero.windows.add.views.url_view import URLAddView
from fichero.windows.add.views.camera_view import CameraAddView

__all__ = [
    "URLAddView",
    "CameraAddView"
] 