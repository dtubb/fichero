"""
Color Manager for Fichero

Manages view-specific colors and themes with support for:
- Icon colorization (convert black icons to custom colors)
- View background colors (different shades of grey)
- Text colors (light blue accents)
- Toolbar transparency
"""

import logging
from typing import Dict, Optional, Any, Tuple
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ColorScheme(Enum):
    """Predefined color schemes"""
    DEFAULT = "default"
    DARK = "dark"
    LIGHT = "light"
    CUSTOM = "custom"


class ColorManager:
    """Manages view-specific colors and themes"""
    
    def __init__(self):
        """Initialize color manager"""
        # Default color schemes
        self.color_schemes = {
            ColorScheme.DEFAULT: {
                'library': {
                    'background': '#F8F8F8',
                    'text': '#333333',
                    'accent': '#87CEEB',
                    'border': '#E0E0E0'
                },
                'collection': {
                    'background': '#F5F5F5',
                    'text': '#333333',
                    'accent': '#87CEEB',
                    'border': '#D0D0D0'
                },
                'fiche': {
                    'background': '#FFFFFF',
                    'text': '#333333',
                    'accent': '#87CEEB',
                    'border': '#C0C0C0'
                },
                'preview': {
                    'background': '#FAFAFA',
                    'text': '#333333',
                    'accent': '#87CEEB',
                    'border': '#B0B0B0'
                }
            },
            ColorScheme.DARK: {
                'library': {
                    'background': '#2D2D2D',
                    'text': '#FFFFFF',
                    'accent': '#4A9FE1',
                    'border': '#404040'
                },
                'collection': {
                    'background': '#252525',
                    'text': '#FFFFFF',
                    'accent': '#4A9FE1',
                    'border': '#353535'
                },
                'fiche': {
                    'background': '#1E1E1E',
                    'text': '#FFFFFF',
                    'accent': '#4A9FE1',
                    'border': '#2A2A2A'
                },
                'preview': {
                    'background': '#181818',
                    'text': '#FFFFFF',
                    'accent': '#4A9FE1',
                    'border': '#202020'
                }
            },
            ColorScheme.LIGHT: {
                'library': {
                    'background': '#FFFFFF',
                    'text': '#000000',
                    'accent': '#007AFF',
                    'border': '#E5E5E5'
                },
                'collection': {
                    'background': '#F9F9F9',
                    'text': '#000000',
                    'accent': '#007AFF',
                    'border': '#E0E0E0'
                },
                'fiche': {
                    'background': '#FFFFFF',
                    'text': '#000000',
                    'accent': '#007AFF',
                    'border': '#D0D0D0'
                },
                'preview': {
                    'background': '#FCFCFC',
                    'text': '#000000',
                    'accent': '#007AFF',
                    'border': '#C0C0C0'
                }
            }
        }
        
        # Current color scheme
        self.current_scheme = ColorScheme.DEFAULT
        
        # Custom colors (user-defined)
        self.custom_colors: Dict[str, Dict[str, str]] = {}
        
        # Icon colorization settings
        self.icon_colors = {
            'library': '#87CEEB',      # Light blue
            'collection': '#87CEEB',   # Light blue
            'fiche': '#87CEEB',        # Light blue
            'preview': '#87CEEB'       # Light blue
        }
        
        # Toolbar transparency settings
        self.toolbar_transparency = {
            'library': 0.9,      # 90% opacity
            'collection': 0.9,   # 90% opacity
            'fiche': 0.9,        # 90% opacity
            'preview': 0.9       # 90% opacity
        }
    
    def get_colors_for_view(self, view_name: str, scheme: Optional[ColorScheme] = None) -> Dict[str, str]:
        """Get colors for a specific view"""
        try:
            scheme = scheme or self.current_scheme
            
            if scheme == ColorScheme.CUSTOM and view_name in self.custom_colors:
                return self.custom_colors[view_name]
            
            if scheme in self.color_schemes and view_name in self.color_schemes[scheme]:
                return self.color_schemes[scheme][view_name]
            
            # Fallback to default
            return self.color_schemes[ColorScheme.DEFAULT].get(view_name, {})
            
        except Exception as e:
            logger.error(f"Failed to get colors for view {view_name}: {e}")
            return {}
    
    def set_custom_colors(self, view_name: str, colors: Dict[str, str]):
        """Set custom colors for a specific view"""
        try:
            self.custom_colors[view_name] = colors
            logger.debug(f"Custom colors set for {view_name}: {colors}")
            
        except Exception as e:
            logger.error(f"Failed to set custom colors for {view_name}: {e}")
    
    def get_icon_color(self, view_name: str) -> str:
        """Get the icon color for a specific view"""
        return self.icon_colors.get(view_name, '#87CEEB')
    
    def set_icon_color(self, view_name: str, color: str):
        """Set the icon color for a specific view"""
        try:
            self.icon_colors[view_name] = color
            logger.debug(f"Icon color set for {view_name}: {color}")
            
        except Exception as e:
            logger.error(f"Failed to set icon color for {view_name}: {color}")
    
    def get_toolbar_transparency(self, view_name: str) -> float:
        """Get the toolbar transparency for a specific view"""
        return self.toolbar_transparency.get(view_name, 0.9)
    
    def set_toolbar_transparency(self, view_name: str, transparency: float):
        """Set the toolbar transparency for a specific view"""
        try:
            # Clamp transparency between 0.0 and 1.0
            transparency = max(0.0, min(1.0, transparency))
            self.toolbar_transparency[view_name] = transparency
            logger.debug(f"Toolbar transparency set for {view_name}: {transparency}")
            
        except Exception as e:
            logger.error(f"Failed to set toolbar transparency for {view_name}: {transparency}")
    
    def set_color_scheme(self, scheme: ColorScheme):
        """Set the current color scheme"""
        try:
            self.current_scheme = scheme
            logger.info(f"Color scheme changed to: {scheme.value}")
            
        except Exception as e:
            logger.error(f"Failed to set color scheme: {e}")
    
    def get_current_scheme(self) -> ColorScheme:
        """Get the current color scheme"""
        return self.current_scheme
    
    def get_available_schemes(self) -> list[ColorScheme]:
        """Get list of available color schemes"""
        return list(self.color_schemes.keys())
    
    def create_custom_scheme(self, name: str, colors: Dict[str, Dict[str, str]]) -> bool:
        """Create a custom color scheme"""
        try:
            # Create new scheme enum value
            new_scheme = ColorScheme(name)
            
            # Add to color schemes
            self.color_schemes[new_scheme] = colors
            
            logger.info(f"Custom color scheme created: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create custom color scheme: {e}")
            return False
    
    def get_all_view_colors(self, scheme: Optional[ColorScheme] = None) -> Dict[str, Dict[str, str]]:
        """Get colors for all views in a scheme"""
        try:
            scheme = scheme or self.current_scheme
            
            if scheme == ColorScheme.CUSTOM:
                return self.custom_colors
            
            if scheme in self.color_schemes:
                return self.color_schemes[scheme]
            
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get all view colors: {e}")
            return {}
    
    def export_color_scheme(self, scheme: ColorScheme) -> Dict[str, Any]:
        """Export a color scheme to a dictionary"""
        try:
            if scheme in self.color_schemes:
                return {
                    'name': scheme.value,
                    'colors': self.color_schemes[scheme],
                    'icon_colors': self.icon_colors,
                    'toolbar_transparency': self.toolbar_transparency
                }
            return {}
            
        except Exception as e:
            logger.error(f"Failed to export color scheme: {e}")
            return {}
    
    def import_color_scheme(self, scheme_data: Dict[str, Any]) -> bool:
        """Import a color scheme from a dictionary"""
        try:
            name = scheme_data.get('name', 'imported')
            colors = scheme_data.get('colors', {})
            icon_colors = scheme_data.get('icon_colors', {})
            toolbar_transparency = scheme_data.get('toolbar_transparency', {})
            
            # Create new scheme
            new_scheme = ColorScheme(name)
            self.color_schemes[new_scheme] = colors
            
            # Update icon colors and transparency
            self.icon_colors.update(icon_colors)
            self.toolbar_transparency.update(toolbar_transparency)
            
            logger.info(f"Color scheme imported: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to import color scheme: {e}")
            return False
    
    def reset_to_defaults(self):
        """Reset all colors to default values"""
        try:
            self.current_scheme = ColorScheme.DEFAULT
            self.custom_colors.clear()
            
            # Reset icon colors
            self.icon_colors = {
                'library': '#87CEEB',
                'collection': '#87CEEB',
                'fiche': '#87CEEB',
                'preview': '#87CEEB'
            }
            
            # Reset toolbar transparency
            self.toolbar_transparency = {
                'library': 0.9,
                'collection': 0.9,
                'fiche': 0.9,
                'preview': 0.9
            }
            
            logger.info("Colors reset to defaults")
            
        except Exception as e:
            logger.error(f"Failed to reset colors: {e}")
    
    def get_color_info(self) -> Dict[str, Any]:
        """Get information about current color configuration"""
        return {
            'current_scheme': self.current_scheme.value,
            'available_schemes': [s.value for s in self.available_schemes],
            'custom_colors': list(self.custom_colors.keys()),
            'icon_colors': self.icon_colors,
            'toolbar_transparency': self.toolbar_transparency
        } 