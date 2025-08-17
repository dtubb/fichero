"""
Styling Module for Fichero Main Window

Provides color management, theming, and icon colorization.
"""

from .color_manager import ColorManager, ColorScheme
from .theme_manager import ThemeManager, Platform
from .icon_colorizer import IconColorizer
from .color_constants import *

__all__ = [
    'ColorManager',
    'ColorScheme',
    'ThemeManager',
    'Platform',
    'IconColorizer'
] 