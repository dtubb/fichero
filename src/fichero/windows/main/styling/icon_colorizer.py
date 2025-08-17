"""
Icon Colorizer for Fichero

Converts black icons to custom colors with support for:
- Different icon formats (PNG, SVG, etc.)
- Color replacement algorithms
- Caching for performance
"""

import logging
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
import hashlib
import json

logger = logging.getLogger(__name__)


class IconColorizer:
    """Converts black icons to custom colors"""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize icon colorizer"""
        self.cache_dir = cache_dir or Path.home() / ".fichero" / "icon_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Color replacement cache
        self.color_cache: Dict[str, str] = {}
        
        # Supported icon formats
        self.supported_formats = {'.png', '.svg', '.ico', '.icns'}
        
        # Load existing cache
        self._load_cache()
    
    def _load_cache(self):
        """Load color replacement cache from disk"""
        try:
            cache_file = self.cache_dir / "color_cache.json"
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    self.color_cache = json.load(f)
                logger.debug(f"Loaded {len(self.color_cache)} cached color replacements")
        except Exception as e:
            logger.warning(f"Failed to load color cache: {e}")
            self.color_cache = {}
    
    def _save_cache(self):
        """Save color replacement cache to disk"""
        try:
            cache_file = self.cache_dir / "color_cache.json"
            with open(cache_file, 'w') as f:
                json.dump(self.color_cache, f, indent=2)
            logger.debug("Color cache saved to disk")
        except Exception as e:
            logger.warning(f"Failed to save color cache: {e}")
    
    def _get_cache_key(self, icon_path: str, target_color: str) -> str:
        """Generate cache key for icon and color combination"""
        # Create hash of icon path and target color
        key_data = f"{icon_path}:{target_color}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def colorize_icon(self, icon_path: str, target_color: str) -> Optional[str]:
        """Colorize an icon to the target color"""
        try:
            # Check if icon exists
            icon_file = Path(icon_path)
            if not icon_file.exists():
                logger.warning(f"Icon file not found: {icon_path}")
                return None
            
            # Check if format is supported
            if icon_file.suffix.lower() not in self.supported_formats:
                logger.warning(f"Unsupported icon format: {icon_file.suffix}")
                return None
            
            # Check cache first
            cache_key = self._get_cache_key(icon_path, target_color)
            if cache_key in self.color_cache:
                cached_path = self.color_cache[cache_key]
                if Path(cached_path).exists():
                    logger.debug(f"Using cached colorized icon: {cached_path}")
                    return cached_path
            
            # Generate colorized icon
            colorized_path = self._generate_colorized_icon(icon_path, target_color)
            
            if colorized_path:
                # Cache the result
                self.color_cache[cache_key] = colorized_path
                self._save_cache()
                logger.debug(f"Icon colorized and cached: {colorized_path}")
                return colorized_path
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to colorize icon {icon_path}: {e}")
            return None
    
    def _generate_colorized_icon(self, icon_path: str, target_color: str) -> Optional[str]:
        """Generate a colorized version of the icon"""
        try:
            icon_file = Path(icon_path)
            
            # For now, we'll implement a basic approach
            # In a real implementation, this would use image processing libraries
            # like Pillow (PIL) for PNG/ICO or other libraries for SVG
            
            if icon_file.suffix.lower() == '.png':
                return self._colorize_png_icon(icon_path, target_color)
            elif icon_file.suffix.lower() == '.svg':
                return self._colorize_svg_icon(icon_path, target_color)
            elif icon_file.suffix.lower() in {'.ico', '.icns'}:
                return self._colorize_ico_icon(icon_path, target_color)
            else:
                logger.warning(f"No colorization method for format: {icon_file.suffix}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to generate colorized icon: {e}")
            return None
    
    def _colorize_png_icon(self, icon_path: str, target_color: str) -> Optional[str]:
        """Colorize a PNG icon"""
        try:
            # This is a placeholder implementation
            # In a real implementation, you would:
            # 1. Load the PNG image using Pillow
            # 2. Convert black pixels to the target color
            # 3. Save the modified image
            
            logger.debug(f"PNG colorization not yet implemented for {icon_path}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to colorize PNG icon: {e}")
            return None
    
    def _colorize_svg_icon(self, icon_path: str, target_color: str) -> Optional[str]:
        """Colorize an SVG icon"""
        try:
            # This is a placeholder implementation
            # In a real implementation, you would:
            # 1. Parse the SVG XML
            # 2. Replace black color values with target color
            # 3. Save the modified SVG
            
            logger.debug(f"SVG colorization not yet implemented for {icon_path}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to colorize SVG icon: {e}")
            return None
    
    def _colorize_ico_icon(self, icon_path: str, target_color: str) -> Optional[str]:
        """Colorize an ICO/ICNS icon"""
        try:
            # This is a placeholder implementation
            # In a real implementation, you would:
            # 1. Load the ICO/ICNS file
            # 2. Extract and modify the images
            # 3. Save the modified icon file
            
            logger.debug(f"ICO/ICNS colorization not yet implemented for {icon_path}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to colorize ICO/ICNS icon: {e}")
            return None
    
    def batch_colorize_icons(self, icon_paths: list[str], target_color: str) -> Dict[str, str]:
        """Colorize multiple icons in batch"""
        results = {}
        
        for icon_path in icon_paths:
            try:
                colorized_path = self.colorize_icon(icon_path, target_color)
                if colorized_path:
                    results[icon_path] = colorized_path
                else:
                    results[icon_path] = None
            except Exception as e:
                logger.error(f"Failed to colorize icon in batch: {icon_path}")
                results[icon_path] = None
        
        logger.info(f"Batch colorization completed: {len([v for v in results.values() if v])}/{len(icon_paths)} successful")
        return results
    
    def clear_cache(self):
        """Clear the color replacement cache"""
        try:
            self.color_cache.clear()
            self._save_cache()
            logger.info("Icon colorization cache cleared")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about the cache"""
        return {
            'cache_size': len(self.color_cache),
            'cache_dir': str(self.cache_dir),
            'supported_formats': list(self.supported_formats)
        }
    
    def is_icon_colorizable(self, icon_path: str) -> bool:
        """Check if an icon can be colorized"""
        try:
            icon_file = Path(icon_path)
            return (icon_file.exists() and 
                   icon_file.suffix.lower() in self.supported_formats)
        except Exception:
            return False
    
    def get_supported_formats(self) -> set[str]:
        """Get supported icon formats"""
        return self.supported_formats.copy()
    
    def add_supported_format(self, format_ext: str):
        """Add a supported format extension"""
        if format_ext.startswith('.'):
            self.supported_formats.add(format_ext.lower())
            logger.debug(f"Added supported format: {format_ext}")
        else:
            logger.warning(f"Format extension must start with '.': {format_ext}")
    
    def remove_supported_format(self, format_ext: str):
        """Remove a supported format extension"""
        if format_ext in self.supported_formats:
            self.supported_formats.remove(format_ext)
            logger.debug(f"Removed supported format: {format_ext}")
        else:
            logger.warning(f"Format not in supported formats: {format_ext}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            cache_files = list(self.cache_dir.glob("*"))
            total_size = sum(f.stat().st_size for f in cache_files if f.is_file())
            
            return {
                'cache_entries': len(self.color_cache),
                'cache_files': len(cache_files),
                'total_size_bytes': total_size,
                'total_size_mb': total_size / (1024 * 1024)
            }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {}
    
    def cleanup_cache(self, max_age_days: int = 30):
        """Clean up old cache entries"""
        try:
            import time
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            # This would implement cache cleanup logic
            # For now, just log the intention
            logger.info(f"Cache cleanup requested for entries older than {max_age_days} days")
            
        except Exception as e:
            logger.error(f"Failed to cleanup cache: {e}") 