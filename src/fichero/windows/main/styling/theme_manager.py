"""
Theme Manager for Fichero

Manages overall app theming with support for:
- View-specific color schemes
- Platform-specific styling
- Dynamic color switching
- Theme persistence
"""

import logging
from typing import Dict, Optional, Any, List
from enum import Enum
from pathlib import Path
import json
import platform

from fichero.windows.main.styling.color_manager import ColorManager, ColorScheme
from fichero.windows.main.styling.icon_colorizer import IconColorizer

logger = logging.getLogger(__name__)


class Platform(Enum):
    """Supported platforms"""
    DESKTOP = "desktop"
    MOBILE = "mobile"
    IOS = "ios"
    ANDROID = "android"
    MACOS = "macos"
    WINDOWS = "windows"
    LINUX = "linux"


class ThemeManager:
    """Manages overall app theming"""
    
    def __init__(self, app, config_dir: Optional[Path] = None):
        """Initialize theme manager"""
        self.app = app
        self.config_dir = config_dir or Path.home() / ".fichero" / "themes"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Platform detection
        self.current_platform = self._detect_platform()
        
        # Core managers
        self.color_manager = ColorManager()
        self.icon_colorizer = IconColorizer()
        
        # Theme configuration
        self.current_theme = "default"
        self.available_themes: List[str] = []
        self.theme_configs: Dict[str, Dict[str, Any]] = {}
        
        # Platform-specific themes
        self.platform_themes: Dict[Platform, str] = {
            Platform.DESKTOP: "default",
            Platform.MOBILE: "mobile_default",
            Platform.IOS: "ios_default",
            Platform.ANDROID: "android_default",
            Platform.MACOS: "macos_default",
            Platform.WINDOWS: "windows_default",
            Platform.LINUX: "linux_default"
        }
        
        # Load themes and configuration
        self._load_themes()
        self._load_theme_config()
        
        # Apply current theme
        self.apply_theme(self.current_theme)
    
    def _detect_platform(self) -> Platform:
        """Detect the current platform"""
        try:
            system = platform.system().lower()
            machine = platform.machine().lower()
            
            if system == "darwin":  # macOS
                # Check if it's iOS (simulator or device)
                if "ios" in machine or "iphone" in machine or "ipad" in machine:
                    return Platform.IOS
                else:
                    return Platform.MACOS
            elif system == "windows":
                return Platform.WINDOWS
            elif system == "linux":
                # Check if it's Android
                if "android" in machine or "aarch64" in machine:
                    return Platform.ANDROID
                else:
                    return Platform.LINUX
            else:
                # Default to desktop for unknown systems
                return Platform.DESKTOP
                
        except Exception as e:
            logger.error(f"Failed to detect platform: {e}")
            return Platform.DESKTOP
    
    def _load_themes(self):
        """Load available themes"""
        try:
            # Built-in themes
            self.available_themes = [
                "default",
                "dark",
                "light",
                "mobile_default",
                "ios_default",
                "android_default",
                "macos_default",
                "windows_default",
                "linux_default"
            ]
            
            # Load custom themes from config directory
            custom_theme_files = list(self.config_dir.glob("*.json"))
            for theme_file in custom_theme_files:
                theme_name = theme_file.stem
                if theme_name not in self.available_themes:
                    self.available_themes.append(theme_name)
            
            logger.debug(f"Loaded {len(self.available_themes)} themes")
            
        except Exception as e:
            logger.error(f"Failed to load themes: {e}")
    
    def _load_theme_config(self):
        """Load theme configuration"""
        try:
            config_file = self.config_dir / "theme_config.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    self.current_theme = config.get('current_theme', 'default')
                    self.platform_themes = config.get('platform_themes', self.platform_themes)
                    logger.debug("Theme configuration loaded")
            else:
                # Create default configuration
                self._save_theme_config()
                
        except Exception as e:
            logger.error(f"Failed to load theme configuration: {e}")
    
    def _save_theme_config(self):
        """Save theme configuration"""
        try:
            config = {
                'current_theme': self.current_theme,
                'platform_themes': self.platform_themes
            }
            
            config_file = self.config_dir / "theme_config.json"
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.debug("Theme configuration saved")
            
        except Exception as e:
            logger.error(f"Failed to save theme configuration: {e}")
    
    def get_available_themes(self) -> List[str]:
        """Get list of available themes"""
        return self.available_themes.copy()
    
    def get_current_theme(self) -> str:
        """Get current theme name"""
        return self.current_theme
    
    def get_current_platform(self) -> Platform:
        """Get current platform"""
        return self.current_platform
    
    def apply_theme(self, theme_name: str) -> bool:
        """Apply a specific theme"""
        try:
            if theme_name not in self.available_themes:
                logger.warning(f"Theme not found: {theme_name}")
                return False
            
            # Update current theme
            self.current_theme = theme_name
            
            # Apply color scheme based on theme
            if theme_name == "dark":
                self.color_manager.set_color_scheme(ColorScheme.DARK)
            elif theme_name == "light":
                self.color_manager.set_color_scheme(ColorScheme.LIGHT)
            else:
                self.color_manager.set_color_scheme(ColorScheme.DEFAULT)
            
            # Save configuration
            self._save_theme_config()
            
            logger.info(f"Theme applied: {theme_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply theme {theme_name}: {e}")
            return False
    
    def apply_platform_theme(self) -> bool:
        """Apply the appropriate theme for the current platform"""
        try:
            platform = self.current_platform
            
            # Get platform-specific theme
            if platform in self.platform_themes:
                theme_name = self.platform_themes[platform]
                return self.apply_theme(theme_name)
            else:
                # Fallback to default theme
                return self.apply_theme("default")
                
        except Exception as e:
            logger.error(f"Failed to apply platform theme: {e}")
            return False
    
    def set_platform_theme(self, platform: Platform, theme_name: str) -> bool:
        """Set the theme for a specific platform"""
        try:
            if theme_name not in self.available_themes:
                logger.warning(f"Theme not found: {theme_name}")
                return False
            
            self.platform_themes[platform] = theme_name
            self._save_theme_config()
            
            logger.info(f"Platform theme set: {platform.value} -> {theme_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set platform theme: {e}")
            return False
    
    def create_custom_theme(self, name: str, colors: Dict[str, Dict[str, str]]) -> bool:
        """Create a custom theme"""
        try:
            # Add to available themes
            if name not in self.available_themes:
                self.available_themes.append(name)
            
            # Set custom colors
            for view_name, view_colors in colors.items():
                self.color_manager.set_custom_colors(view_name, view_colors)
            
            # Save theme configuration
            self._save_theme_config()
            
            logger.info(f"Custom theme created: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create custom theme: {e}")
            return False
    
    def delete_custom_theme(self, name: str) -> bool:
        """Delete a custom theme"""
        try:
            if name in self.available_themes:
                self.available_themes.remove(name)
                
                # Remove from platform themes if it's set
                for platform, theme in self.platform_themes.items():
                    if theme == name:
                        self.platform_themes[platform] = "default"
                
                # If it's the current theme, switch to default
                if self.current_theme == name:
                    self.apply_theme("default")
                
                # Save configuration
                self._save_theme_config()
                
                logger.info(f"Custom theme deleted: {name}")
                return True
            else:
                logger.warning(f"Theme not found for deletion: {name}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete custom theme: {e}")
            return False
    
    def export_theme(self, theme_name: str) -> Optional[Dict[str, Any]]:
        """Export a theme to a dictionary"""
        try:
            if theme_name not in self.available_themes:
                return None
            
            # Get theme colors
            colors = self.color_manager.get_all_view_colors()
            
            # Get icon colors and transparency
            icon_colors = self.color_manager.icon_colors
            toolbar_transparency = self.color_manager.toolbar_transparency
            
            theme_data = {
                'name': theme_name,
                'colors': colors,
                'icon_colors': icon_colors,
                'toolbar_transparency': toolbar_transparency,
                'platform': self.current_platform.value
            }
            
            return theme_data
            
        except Exception as e:
            logger.error(f"Failed to export theme: {e}")
            return None
    
    def import_theme(self, theme_data: Dict[str, Any]) -> bool:
        """Import a theme from a dictionary"""
        try:
            name = theme_data.get('name', 'imported')
            colors = theme_data.get('colors', {})
            icon_colors = theme_data.get('icon_colors', {})
            toolbar_transparency = theme_data.get('toolbar_transparency', {})
            
            # Create custom theme
            success = self.create_custom_theme(name, colors)
            
            if success:
                # Update icon colors and transparency
                for view_name, color in icon_colors.items():
                    self.color_manager.set_icon_color(view_name, color)
                
                for view_name, transparency in toolbar_transparency.items():
                    self.color_manager.set_toolbar_transparency(view_name, transparency)
                
                logger.info(f"Theme imported: {name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to import theme: {e}")
            return False
    
    def get_theme_info(self, theme_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific theme"""
        try:
            if theme_name not in self.available_themes:
                return None
            
            # Get theme colors
            colors = self.color_manager.get_all_view_colors()
            
            # Get icon colors and transparency
            icon_colors = self.color_manager.icon_colors
            toolbar_transparency = self.color_manager.toolbar_transparency
            
            # Check if it's a platform theme
            is_platform_theme = any(theme == theme_name for theme in self.platform_themes.values())
            
            theme_info = {
                'name': theme_name,
                'colors': colors,
                'icon_colors': icon_colors,
                'toolbar_transparency': toolbar_transparency,
                'is_platform_theme': is_platform_theme,
                'platform': self.current_platform.value
            }
            
            return theme_info
            
        except Exception as e:
            logger.error(f"Failed to get theme info: {e}")
            return None
    
    def reset_to_defaults(self):
        """Reset all themes to default values"""
        try:
            # Reset color manager
            self.color_manager.reset_to_defaults()
            
            # Reset platform themes
            self.platform_themes = {
                Platform.DESKTOP: "default",
                Platform.MOBILE: "mobile_default",
                Platform.IOS: "ios_default",
                Platform.ANDROID: "android_default",
                Platform.MACOS: "macos_default",
                Platform.WINDOWS: "windows_default",
                Platform.LINUX: "linux_default"
            }
            
            # Apply default theme
            self.apply_theme("default")
            
            # Save configuration
            self._save_theme_config()
            
            logger.info("Themes reset to defaults")
            
        except Exception as e:
            logger.error(f"Failed to reset themes: {e}")
    
    def get_theme_summary(self) -> Dict[str, Any]:
        """Get a summary of all themes and configuration"""
        return {
            'current_theme': self.current_theme,
            'current_platform': self.current_platform.value,
            'available_themes': self.available_themes,
            'platform_themes': {p.value: t for p, t in self.platform_themes.items()},
            'color_scheme': self.color_manager.get_current_scheme().value,
            'icon_colorizer_info': self.icon_colorizer.get_cache_info()
        } 