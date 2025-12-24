"""
TokenFieldWidget - Native macOS NSTokenField for tag display.

Displays values as macOS Finder-style blue pill tokens.
Falls back to a Toga-based implementation on non-macOS platforms.
"""

from .widget import TokenFieldWidget, parse_metadata_value

__all__ = ['TokenFieldWidget', 'parse_metadata_value']
