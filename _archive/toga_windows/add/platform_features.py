"""
Platform Feature Detection for Add Window

Detects what add functionality is available on the current platform.
Provides clean platform compatibility information without custom styling.
"""

import toga
import logging
from typing import Dict, List, Any
from dataclasses import dataclass

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


@dataclass
class PlatformFeatures:
    """Platform capability flags"""
    has_file_dialog: bool = False
    has_folder_dialog: bool = False
    has_camera: bool = False
    has_audio_recording: bool = False
    has_web_view: bool = True
    has_url_input: bool = True
    is_mobile: bool = False
    is_desktop: bool = False


def detect_platform_features(app: toga.App) -> PlatformFeatures:
    """
    Detect what features are available on the current platform.
    
    Args:
        app: Toga application instance
        
    Returns:
        PlatformFeatures: Object containing capability flags
    """
    features = PlatformFeatures()
    
    try:
        # Detect mobile vs desktop
        features.is_mobile = getattr(app, 'is_mobile', False)
        features.is_desktop = not features.is_mobile
        
        # Platform-specific feature detection using app's platform detection (respects debug flags)
        import toga.platform
        import os

        # Use app's platform detection logic that respects FORCE_MOBILE_UI
        env_mobile = os.environ.get('FORCE_MOBILE_UI')
        if env_mobile is not None:
            # Environment override - determine platform based on actual platform but respect mobile override
            actual_platform = toga.platform.current_platform.lower()
            if env_mobile.lower() in ('true', '1', 'yes', 'on'):
                # Force mobile UI - treat as iOS for feature detection
                platform_name = 'ios' if actual_platform == 'macos' else actual_platform
            else:
                # Force desktop UI
                platform_name = actual_platform
        else:
            # Normal detection
            platform_name = toga.platform.current_platform.lower()
        
        # File dialogs (desktop only)
        if platform_name in ['macos', 'windows', 'linux', 'gtk', 'cocoa']:
            features.has_file_dialog = True
            features.has_folder_dialog = True
        
        # Camera (iOS, Android, macOS only - not Windows/GTK)
        if platform_name in ['ios', 'android', 'macos', 'cocoa']:
            # Camera works well on mobile and macOS, check if app can actually access it
            try:
                features.has_camera = hasattr(app, 'camera') and app.camera is not None
            except Exception:
                # If camera initialization fails (permissions, no hardware, etc), disable it
                features.has_camera = False
        
        # Audio recording (future feature)
        features.has_audio_recording = False
        
        # Web view (all platforms)
        features.has_web_view = True
        
        # URL input (all platforms)
        features.has_url_input = True
        
        logger.info(f"Platform features detected for {platform_name}: "
                   f"file_dialog={features.has_file_dialog}, "
                   f"folder_dialog={features.has_folder_dialog}, "
                   f"camera={features.has_camera}")
        
    except Exception as e:
        logger.error(f"Error detecting platform features: {e}")
        # Safe defaults
        features.has_web_view = True
        features.has_url_input = True
    
    return features


def get_available_add_options(features: PlatformFeatures) -> List[Dict[str, Any]]:
    """
    Get list of available add options based on platform features.
    
    Args:
        features: Platform features object
        
    Returns:
        List of dictionaries containing option metadata
    """
    options = [
        {
            'id': 'url',
            'title': _('Add URL'),
            'description': _('Add content from a web URL'),
            'available': features.has_url_input,
            'platforms': ['All Platforms']
        },
        {
            'id': 'website',
            'title': _('Add Website'),
            'description': _('Browse and add content from websites'),
            'available': features.has_web_view,
            'platforms': ['All Platforms']
        }
    ]
    
    # Desktop-only options
    if features.has_file_dialog:
        options.append({
            'id': 'file',
            'title': _('Add File'),
            'description': _('Add files from your computer'),
            'available': True,
            'platforms': ['macOS', 'Windows', 'Linux']
        })
    
    if features.has_folder_dialog:
        options.append({
            'id': 'folder',
            'title': _('Add Folder'),
            'description': _('Add entire folders to your library'),
            'available': True,
            'platforms': ['macOS', 'Windows', 'Linux']
        })
    
    # Camera-enabled platforms
    if features.has_camera:
        options.append({
            'id': 'camera',
            'title': _('Add Picture'),
            'description': _('Take a photo with your camera'),
            'available': True,
            'platforms': ['macOS', 'iOS', 'Android']
        })
    
    # Future features
    options.append({
        'id': 'audio',
        'title': _('Add Audio Recording'),
        'description': _('Record audio to add to your library'),
        'available': features.has_audio_recording,
        'platforms': ['Future Release']
    })
    
    return options 