"""
Debug Constants

Global debug constants for testing and development.
These override normal platform detection for easier debugging.
"""

# UI Debug Settings
# Set to True to force mobile UI mode even on desktop (for debugging)
FORCE_MOBILE_UI = False

# Set to True to force desktop UI mode even on mobile (for debugging) 
FORCE_DESKTOP_UI = True

# Set to True to force iOS-specific behavior
FORCE_IOS_BEHAVIOR = True

# Set to True to force Android-specific behavior  
FORCE_ANDROID_BEHAVIOR = False

# Window size overrides (set to None to use platform defaults)
DEBUG_WINDOW_WIDTH = 375  # e.g., 375 for iPhone size
DEBUG_WINDOW_HEIGHT = 812  # e.g., 812 for iPhone size

# Development logging
VERBOSE_UI_LOGGING = True

def get_debug_mobile_override():
    """
    Get mobile mode override for debugging.
    
    Returns:
        None: Use platform detection
        True: Force mobile mode
        False: Force desktop mode
    """
    if FORCE_MOBILE_UI:
        return True
    elif FORCE_DESKTOP_UI:
        return False
    else:
        return None

def get_debug_platform_override():
    """
    Get platform override for debugging.
    
    Returns:
        None: Use actual platform
        'ios': Force iOS behavior
        'android': Force Android behavior
    """
    if FORCE_IOS_BEHAVIOR:
        return 'ios'
    elif FORCE_ANDROID_BEHAVIOR:
        return 'android'
    else:
        return None

def get_debug_window_size():
    """
    Get debug window size override.
    
    Returns:
        tuple: (width, height) if overridden
        None: Use platform defaults
    """
    if DEBUG_WINDOW_WIDTH and DEBUG_WINDOW_HEIGHT:
        return (DEBUG_WINDOW_WIDTH, DEBUG_WINDOW_HEIGHT)
    else:
        return None 