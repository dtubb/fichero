"""
Path Icons Utility

Loads folder icons from disk and builds platform-specific paths with icons.
Supports macOS, Windows, and Linux with appropriate fallbacks.
"""

import sys
import subprocess
import os
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import logging

# Try to import Toga for image loading
try:
    import toga
    TOGA_AVAILABLE = True
except ImportError:
    TOGA_AVAILABLE = False
    logger.debug("Toga not available - image loading disabled")

logger = logging.getLogger(__name__)

# Image cache for loaded icons
_image_cache = {}

# Icon path cache to avoid repeated file system calls
_icon_path_cache = {}

# Try to import PyObjC for macOS icon loading
try:
    import objc
    from AppKit import NSWorkspace, NSImage, NSBitmapImageRep, NSBitmapImageFileTypePNG
    PYOBC_AVAILABLE = True
except ImportError:
    PYOBC_AVAILABLE = False
    logger.debug("PyObjC not available - will use fallback icons")


def load_image(image_path: str) -> Optional[Any]:
    """Load and cache a Toga image"""
    if not TOGA_AVAILABLE:
        return None
    
    if image_path in _image_cache:
        return _image_cache[image_path]
    
    try:
        if Path(image_path).exists():
            image = toga.Image(image_path)
            _image_cache[image_path] = image
            return image
    except Exception as e:
        logger.debug(f"Could not load image {image_path}: {e}")
    
    return None


def get_fallback_folder_icon() -> Optional[str]:
    """Get the path to the fallback folder icon"""
    # Get the path to the resources folder
    current_file = Path(__file__)
    resources_path = current_file.parent.parent / "resources" / "icons" / "folder_small_icon.png"
    
    if resources_path.exists():
        return str(resources_path)
    
    return None


class PathIconLoader:
    """Loads folder icons from disk for different platforms"""
    
    @staticmethod
    def get_folder_icon_path(folder_path: Path, size: int = 16) -> Optional[str]:
        """
        Get the path to a folder's icon file.
        
        Args:
            folder_path: Path to the folder
            size: Icon size in pixels (default 16)
            
        Returns:
            Path to icon file if found, None otherwise
        """
        # Check cache first (include size in cache key)
        cache_key = f"{folder_path}_{size}"
        if cache_key in _icon_path_cache:
            return _icon_path_cache[cache_key]
        
        # Get icon path based on platform
        if sys.platform == "darwin":
            result = PathIconLoader._get_macos_folder_icon_path(folder_path, size)
        elif sys.platform == "win32":
            result = PathIconLoader._get_windows_folder_icon_path(folder_path, size)
        else:
            result = PathIconLoader._get_linux_folder_icon_path(folder_path, size)
        
        # Cache the result
        _icon_path_cache[cache_key] = result
        return result
    
    @staticmethod
    def _get_macos_folder_icon_path(folder_path: Path, size: int = 16) -> Optional[str]:
        """Get macOS folder icon path"""
        try:
            # Quick check for system folders first (most common case)
            folder_name = folder_path.name
            if folder_name in ["Applications", "System", "Library", "Users", "Documents", 
                             "Desktop", "Downloads", "Pictures", "Music", "Movies"]:
                # For system folders, always use system icon
                if PYOBC_AVAILABLE:
                    return PathIconLoader._get_macos_system_icon_path(folder_path, size)
            
            # For non-system folders, check for custom icons first (faster than system call)
            # Check for custom icon in .icns format (Icon\r)
            icon_path = folder_path / "Icon\r"
            if icon_path.exists():
                # Convert custom icon to PNG using NSWorkspace
                if PYOBC_AVAILABLE:
                    return PathIconLoader._get_macos_system_icon_path(folder_path, size)
                return str(icon_path)  # Fallback
            
            # Check for custom icon in .icns format in hidden file
            icon_path = folder_path / ".icns"
            if icon_path.exists():
                # Convert custom icon to PNG using NSWorkspace
                if PYOBC_AVAILABLE:
                    return PathIconLoader._get_macos_system_icon_path(folder_path, size)
                return str(icon_path)  # Fallback
            
            # Check for custom icon in .png format (already usable)
            icon_path = folder_path / "icon.png"
            if icon_path.exists():
                return str(icon_path)
            
            # Only call system icon for non-system folders if no custom icon found
            if PYOBC_AVAILABLE:
                return PathIconLoader._get_macos_system_icon_path(folder_path, size)
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not get macOS folder icon path: {e}")
            return None
    
    @staticmethod
    def _get_macos_system_icon_path(folder_path: Path, size: int = 16) -> Optional[str]:
        """Get macOS system icon path using NSWorkspace - based on alexwlchan.net approach"""
        try:
            # Create a more specific cache key for system icons (include size)
            folder_name = folder_path.name or "root"
            temp_path = os.path.join(tempfile.gettempdir(), f"fichero_icon_{folder_name}_{size}x{size}.png")
            
            # Check if icon file already exists and is recent (< 1 hour old)
            if os.path.exists(temp_path):
                import time
                file_age = time.time() - os.path.getmtime(temp_path)
                if file_age < 3600:  # 1 hour
                    return temp_path
            
            # Get the system icon for this folder using NSWorkspace.shared.icon(forFile:)
            workspace = NSWorkspace.sharedWorkspace()
            icon = workspace.iconForFile_(str(folder_path))
            
            if icon:
                # Set icon size to requested size
                icon.setSize_((size, size))
                
                # Convert NSImage to PNG data using the approach from alexwlchan.net
                tiff_data = icon.TIFFRepresentation()
                if tiff_data:
                    bitmap_rep = NSBitmapImageRep.alloc().initWithData_(tiff_data)
                    if bitmap_rep:
                        png_data = bitmap_rep.representationUsingType_properties_(
                            NSBitmapImageFileTypePNG, 
                            {}
                        )
                        
                        if png_data:
                            # Write PNG data to file
                            with open(temp_path, 'wb') as f:
                                f.write(png_data.bytes())
                            
                            return temp_path
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not get macOS system icon: {e}")
            return None
    
    @staticmethod
    def _get_windows_folder_icon_path(folder_path: Path, size: int = 16) -> Optional[str]:
        """Get Windows folder icon path"""
        try:
            # Check for desktop.ini file which might contain icon reference
            desktop_ini = folder_path / "desktop.ini"
            if desktop_ini.exists():
                # Parse desktop.ini for icon reference
                # This is complex, so for now return None
                return None
            
            # Check for custom icon files
            for icon_name in ["icon.ico", "icon.png", "folder.ico"]:
                icon_path = folder_path / icon_name
                if icon_path.exists():
                    return str(icon_path)
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not get Windows folder icon path: {e}")
            return None
    
    @staticmethod
    def _get_linux_folder_icon_path(folder_path: Path, size: int = 16) -> Optional[str]:
        """Get Linux folder icon path"""
        try:
            # Check for .directory file which might contain icon reference
            directory_file = folder_path / ".directory"
            if directory_file.exists():
                # Parse .directory file for icon reference
                # This is complex, so for now return None
                return None
            
            # Check for custom icon files
            for icon_name in ["icon.png", "folder.png", ".icon.png"]:
                icon_path = folder_path / icon_name
                if icon_path.exists():
                    return str(icon_path)
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not get Linux folder icon path: {e}")
            return None


class PathBuilder:
    """Builds platform-specific paths with icons"""
    
    # System folder icons (optimized for macOS appearance)
    SYSTEM_ICONS = {
        "Users": "👤",  # Single user icon, cleaner
        "System": "⚙️", 
        "Applications": "🔷",  # Blue diamond, more macOS-like
        "Library": "📚",
        "Documents": "📄",
        "Desktop": "🖥️",
        "Downloads": "⬇️",
        "Pictures": "🖼️",
        "Music": "🎵",
        "Movies": "🎬",
        "Public": "🌐",
        "tmp": "📁",  # Regular folder for temp
        "home": "🏠",
        "root": "🏠",
        "C:": "💿",  # Windows drive
        "D:": "💿",
        "E:": "💿",
    }
    
    @staticmethod
    def build_path_with_icons(path_str: str) -> List[Dict[str, Any]]:
        """
        Build a path with icons for each component.
        
        Args:
            path_str: The path string to format
            
        Returns:
            List of path components with icon paths and names
        """
        if sys.platform == "darwin":
            return PathBuilder._build_macos_path(path_str)
        elif sys.platform == "win32":
            return PathBuilder._build_windows_path(path_str)
        else:
            return PathBuilder._build_linux_path(path_str)
    
    @staticmethod
    def _build_macos_path(path_str: str) -> List[Dict[str, Any]]:
        """Build macOS-style path with icons"""
        try:
            path = Path(path_str)
            components = []
            
            # Handle absolute paths
            if path.is_absolute():
                # Add root/volume component
                components.append({
                    "name": "",
                    "icon_path": None,
                    "is_root": True
                })
                path_parts = path.parts[1:]  # Skip root "/"
            else:
                path_parts = path.parts
            
            # Build path with icons for each component
            for i, part in enumerate(path_parts):
                # Get icon for this component
                icon_data = PathBuilder._get_component_icon_data(path, i, part)
                components.append(icon_data)
            
            return components
            
        except Exception as e:
            logger.debug(f"Could not build macOS path: {e}")
            # Fallback to simple path
            return [{"name": path_str, "icon_path": None, "is_root": False}]
    
    @staticmethod
    def _build_windows_path(path_str: str) -> List[Dict[str, Any]]:
        """Build Windows-style path with icons"""
        try:
            path = Path(path_str)
            components = []
            
            # Handle drive letter
            if path.drive:
                components.append({
                    "name": path.drive,
                    "icon_path": None,
                    "is_drive": True
                })
            
            # Build path with icons for each component
            path_parts = path.parts
            if path.drive:
                path_parts = path_parts[1:]  # Skip drive
            
            for i, part in enumerate(path_parts):
                # Get icon for this component
                icon_data = PathBuilder._get_component_icon_data(path, i, part)
                components.append(icon_data)
            
            return components
            
        except Exception as e:
            logger.debug(f"Could not build Windows path: {e}")
            return [{"name": path_str, "icon_path": None, "is_root": False}]
    
    @staticmethod
    def _build_linux_path(path_str: str) -> List[Dict[str, Any]]:
        """Build Linux-style path with icons"""
        try:
            path = Path(path_str)
            components = []
            
            # Handle absolute paths
            if path.is_absolute():
                components.append({
                    "name": "",
                    "icon_path": None,
                    "is_root": True
                })
                path_parts = path.parts[1:]  # Skip root "/"
            else:
                path_parts = path.parts
            
            # Build path with icons for each component
            for i, part in enumerate(path_parts):
                # Get icon for this component
                icon_data = PathBuilder._get_component_icon_data(path, i, part)
                components.append(icon_data)
            
            return components
            
        except Exception as e:
            logger.debug(f"Could not build Linux path: {e}")
            return [{"name": path_str, "icon_path": None, "is_root": False}]
    
    @staticmethod
    def format_path_as_string(path_str: str) -> str:
        """
        Format a path as a string with emoji icons.
        
        Args:
            path_str: The path string to format
            
        Returns:
            Formatted path string with emoji icons
        """
        try:
            components = PathBuilder.build_path_with_icons(path_str)
            result = []
            
            for i, component in enumerate(components):
                # Add icon
                if component.get("is_root"):
                    result.append("🏠")
                elif component.get("is_drive"):
                    result.append("💿")
                elif component["name"] in PathBuilder.SYSTEM_ICONS:
                    result.append(PathBuilder.SYSTEM_ICONS[component["name"]])
                else:
                    result.append("📁")
                
                # Add name (bold for last component in string representation)
                if component["name"]:
                    is_last_component = (i == len(components) - 1)
                    if is_last_component:
                        # For string representation, we can't make it bold, but we could use different formatting
                        result.append(component["name"])
                    else:
                        result.append(component["name"])
                
                # Add separator (except for last component)
                if i < len(components) - 1:
                    result.append(" › ")
            
            return "".join(result)
            
        except Exception as e:
            logger.debug(f"Could not format path as string: {e}")
            return path_str
    
    # Canvas rendering removed - we now use ImageView + Label widgets
    
    @staticmethod
    def _get_component_icon_data(full_path: Path, component_index: int, component_name: str) -> Dict[str, Any]:
        """Get icon data for a specific path component"""
        try:
            # Build the path up to this component
            path_parts = full_path.parts
            if full_path.is_absolute() and len(path_parts) > 1:
                # Skip root "/" for absolute paths
                component_path = Path("/").joinpath(*path_parts[1:component_index + 2])
            else:
                component_path = Path().joinpath(*path_parts[:component_index + 1])
            
            # Only get icon for actual folders that exist, skip non-existent intermediate paths
            icon_path = None
            if component_path.exists() and component_path.is_dir():
                # Try to get the actual icon for this specific folder
                icon_path = PathIconLoader.get_folder_icon_path(component_path)
            
            return {
                "name": component_name,
                "icon_path": icon_path,
                "is_root": False
            }
            
        except Exception as e:
            logger.debug(f"Could not get icon data for component {component_name}: {e}")
            return {
                "name": component_name,
                "icon_path": None,
                "is_root": False
            }


def render_path_with_icons(path_str: str):
    """
    Format a path as a string with emoji icons (for compatibility).
    
    Note: Canvas rendering has been removed. Use ImageView + Label widgets instead.
    
    Args:
        path_str: The path string to format
        
    Returns:
        Formatted path string with emoji icons
    """
    return PathBuilder.format_path_as_string(path_str)


def get_folder_icon_path(folder_path: Path, size: int = 16) -> Optional[str]:
    """
    Convenience function to get a folder's icon path.
    
    Args:
        folder_path: Path to the folder
        size: Icon size in pixels (default 16)
        
    Returns:
        Path to icon file if found, None otherwise
    """
    return PathIconLoader.get_folder_icon_path(folder_path, size)


def clear_icon_cache():
    """Clear the icon path cache. Useful for testing or memory management."""
    global _icon_path_cache, _image_cache
    _icon_path_cache.clear()
    _image_cache.clear() 