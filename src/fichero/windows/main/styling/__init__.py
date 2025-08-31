"""
Styling Module for Fichero Main Window

Provides color management, theming, and icon colorization.
"""

from fichero.windows.main.styling.color_manager import ColorManager, ColorScheme
from fichero.windows.main.styling.theme_manager import ThemeManager, Platform
from fichero.windows.main.styling.icon_colorizer import IconColorizer
from fichero.windows.main.styling.color_constants import *

__all__ = [
    'ColorManager',
    'ColorScheme',
    'ThemeManager',
    'Platform',
    'IconColorizer'
] 