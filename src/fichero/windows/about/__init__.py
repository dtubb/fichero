"""
About Window Package

Desktop window and mobile view for displaying application information,
version details, credits, and help links.
"""

from fichero.windows.about.about_window import AboutWindow
from fichero.windows.about.about_content import AboutContent
from fichero.windows.about.mobile_view import AboutMobileView

__all__ = [
    'AboutWindow',
    'AboutContent', 
    'AboutMobileView'
] 