"""
Color Constants for Fichero

Simple color overrides for line art icons.
Everything else uses Toga's native colors.
"""

# ============================================================================
# ICON COLORS
# ============================================================================

# Primary color for line art icons (buttons, active states, etc.)
ICON_PRIMARY = "#0E7AFE"            # Exact color: R=14/255, G=122/255, B=254/255

# Secondary icon color for inactive states (not used - all icons get primary color)
ICON_SECONDARY = ICON_PRIMARY       # Use same color for all icons

# ============================================================================
# BACKWARD COMPATIBILITY
# ============================================================================

# Keep these for existing code that expects them
PRIMARY_COLOR = ICON_PRIMARY
BUTTON_PRIMARY = ICON_PRIMARY
BUTTON_SECONDARY = ICON_SECONDARY
BUTTON_SUCCESS = ICON_PRIMARY
BUTTON_WARNING = ICON_PRIMARY
BUTTON_DANGER = ICON_PRIMARY

STATUS_SUCCESS = ICON_PRIMARY
STATUS_WARNING = ICON_PRIMARY
STATUS_ERROR = ICON_PRIMARY
STATUS_INFO = ICON_PRIMARY

NAV_ACTIVE = ICON_PRIMARY
NAV_INACTIVE = ICON_SECONDARY

LIBRARY_ACCENT = ICON_PRIMARY
COLLECTION_ACCENT = ICON_PRIMARY
FICHE_ACCENT = ICON_PRIMARY
PREVIEW_ACCENT = ICON_PRIMARY

TOOLBAR_ACTIVE = ICON_PRIMARY
TOOLBAR_INACTIVE = ICON_SECONDARY

# Let Toga handle all text, backgrounds, and borders
LIBRARY_TEXT = None
COLLECTION_TEXT = None
FICHE_TEXT = None
PREVIEW_TEXT = None
COMMON_SECONDARY_TEXT = None
COMMON_PLACEHOLDER = None
TOOLBAR_TEXT = None
TOOLBAR_ICON = None

# Use Toga's default backgrounds and borders
LIBRARY_BACKGROUND = None
COLLECTION_BACKGROUND = None
FICHE_BACKGROUND = None
PREVIEW_BACKGROUND = None
LEFT_PANE_BACKGROUND = None
MIDDLE_PANE_BACKGROUND = None
RIGHT_PANE_BACKGROUND = None
TOOLBAR_BACKGROUND = None
TOOLBAR_BORDER = None
COMMON_BORDER = None
BORDER_MAIN = None
BACKGROUND_MAIN = None
BACKGROUND_SECONDARY = None
BACKGROUND_TERTIARY = None

# Keep special colors that aren't icon-related
COLLECTION_ACTIVE = "#FFD700"       # Gold for active collections
COLLECTION_INACTIVE = "#FF6B6B"     # Red for inactive collections 

# Toolbar colors
TOOLBAR_BACKGROUND = "#EBEAEB"  # Grey toolbar background
TOOLBAR_BORDER = "#EBEAEB"      # Subtle border lines
VIEW_BACKGROUND = "#FFFFFF"     # White view background 