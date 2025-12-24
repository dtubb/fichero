"""
SF Symbols helper for Toga Canvas rendering.

Provides access to SF Symbols (macOS system icons) for rendering on Canvas.

SF Symbols are available on macOS 11+ and can be rendered as text using
the SF Pro font with specific Unicode code points.

Usage:
    from .sf_symbols import get_sf_symbol

    symbol = get_sf_symbol('folder')  # Returns '􀈕'
    canvas.write_text(symbol, x=10, y=10, font=Font('SF Pro', 16))
"""

import sys
import logging

logger = logging.getLogger(__name__)


# SF Symbol Unicode mappings (macOS 11+)
# These are in the Private Use Area (PUA) of Unicode
# SF Symbols can be found at: /System/Applications/SF Symbols.app
SF_SYMBOLS = {
    # Folders - using hex representations for SF Symbols
    'folder': '\U000100B9',           # 􀂹 folder
    'folder.fill': '\U000100BA',      # 􀂺 folder.fill
    'folder.badge.plus': '\U00010146', # 􀅆 folder.badge.plus

    # Documents
    'doc': '\U00010152',              # 􀅒 doc
    'doc.fill': '\U00010153',         # 􀅓 doc.fill
    'doc.text': '\U00010154',         # 􀅔 doc.text
    'doc.text.fill': '\U00010155',    # 􀅕 doc.text.fill

    # Images
    'photo': '\U000101FC',            # 􀇼 photo
    'photo.fill': '\U000101FD',       # 􀇽 photo.fill
    'photo.on.rectangle': '\U00010269', # 􀉩 photo.on.rectangle

    # Collections
    'tray': '\U000101F0',             # 􀇰 tray
    'tray.fill': '\U000101F1',        # 􀇱 tray.fill
    'tray.2': '\U000101F2',           # 􀇲 tray.2
    'tray.2.fill': '\U000101F3',      # 􀇳 tray.2.fill

    # Generic items
    'square.grid.2x2': '\U0000f3fc',  # 􀏼 square.grid.2x2
    'list.bullet': '\U0000f154',      # 􀅔 list.bullet
    'rectangle.stack': '\U0000f248',  # 􀉈 rectangle.stack
    'rectangle.stack.fill': '\U0000f249', # 􀉉 rectangle.stack.fill

    # Navigation
    'chevron.right': '\U0000f360',    # 􀍠 chevron.right
    'chevron.left': '\U0000f35f',     # 􀍟 chevron.left
    'chevron.down': '\U0000f35e',     # 􀍞 chevron.down
    'chevron.up': '\U0000f35d',       # 􀍝 chevron.up

    # Actions
    'plus': '\U0000f2c3',             # 􀋃 plus
    'minus': '\U0000f2c4',            # 􀋄 minus
    'xmark': '\U0000f2c5',            # 􀋅 xmark
    'checkmark': '\U0000f2c6',        # 􀋆 checkmark
}


# Simple Unicode symbols that actually render (better than SF Symbols that show as ?)
# These work across all platforms and actually display in Toga Canvas
FALLBACK_SYMBOLS = {
    'folder': '▸',        # Right-pointing triangle (folder indicator)
    'folder.fill': '▾',   # Down-pointing triangle (expanded folder)
    'folder.badge.plus': '+',
    'doc': '◦',          # Small circle (document)
    'doc.fill': '●',     # Filled circle
    'doc.text': '◦',
    'doc.text.fill': '●',
    'photo': '◐',        # Half-filled circle (image)
    'photo.fill': '◉',   # Filled circle with dot
    'photo.on.rectangle': '◐',
    'tray': '▭',         # Rectangle (collection/tray)
    'tray.fill': '▬',    # Filled rectangle
    'tray.2': '▬',
    'tray.2.fill': '▬',
    'square.grid.2x2': '⊞',
    'list.bullet': '•',
    'rectangle.stack': '▭',
    'rectangle.stack.fill': '■',
    'chevron.right': '›',
    'chevron.left': '‹',
    'chevron.down': '∨',
    'chevron.up': '∧',
    'plus': '+',
    'minus': '-',
    'xmark': '×',
    'checkmark': '✓',
}


def is_sf_symbols_available() -> bool:
    """
    Check if SF Symbols are available on this platform.

    Returns:
        True if SF Symbols are available (macOS 11+), False otherwise
    """
    if sys.platform != 'darwin':
        return False

    # Check macOS version (SF Symbols available on 11+)
    try:
        import platform
        version = platform.mac_ver()[0]
        major_version = int(version.split('.')[0])
        return major_version >= 11
    except Exception as e:
        logger.warning(f"Could not detect macOS version: {e}")
        return False


def get_sf_symbol(symbol_name: str, use_fallback: bool = True) -> str:
    """
    Get SF Symbol Unicode character by name.

    Note: SF Symbols (PUA) don't render properly in Toga Canvas currently,
    so we use simple Unicode symbols as fallback which actually display.

    Args:
        symbol_name: SF Symbol name (e.g., 'folder', 'doc.fill')
        use_fallback: If True, return fallback symbols (default: True)

    Returns:
        Unicode character for the symbol

    Example:
        >>> symbol = get_sf_symbol('folder')
        >>> print(f"Icon: {symbol}")
        Icon: ▸
    """
    # SF Symbols don't render in Toga Canvas, so always use fallback
    # (SF Symbols are in Private Use Area which Toga Canvas doesn't support)

    fallback = FALLBACK_SYMBOLS.get(symbol_name, '●')
    logger.debug(f"Using symbol for '{symbol_name}': {fallback}")
    return fallback


def get_sf_symbol_font():
    """
    Get the font constant to use for SF Symbols.

    On macOS, SF Symbols are part of the system font, so we use SYSTEM.
    Toga doesn't support custom font names like 'SF Pro', but SYSTEM
    on macOS will use SF Pro which includes SF Symbols.

    Returns:
        Font constant (SYSTEM from toga.fonts)
    """
    from toga.fonts import SYSTEM
    # Always use SYSTEM font - on macOS this is SF Pro which includes SF Symbols
    return SYSTEM


# Icon type mappings for common use cases
ICON_TYPES = {
    'collection': 'tray.fill',
    'folder': 'folder.fill',
    'file': 'doc.fill',
    'image': 'photo.fill',
    'document': 'doc.text.fill',
    'generic': 'square.grid.2x2',
}


def get_icon_for_type(item_type: str) -> str:
    """
    Get SF Symbol for a common item type.

    Args:
        item_type: Item type ('collection', 'folder', 'file', etc.)

    Returns:
        Unicode character for the appropriate icon

    Example:
        >>> icon = get_icon_for_type('collection')
        >>> print(f"Collection icon: {icon}")
        Collection icon: 􀏩
    """
    symbol_name = ICON_TYPES.get(item_type, 'square.grid.2x2')
    return get_sf_symbol(symbol_name)


__all__ = [
    'get_sf_symbol',
    'get_sf_symbol_font',
    'get_icon_for_type',
    'is_sf_symbols_available',
    'SF_SYMBOLS',
    'ICON_TYPES',
]
