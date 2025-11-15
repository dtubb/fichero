"""
Preview View Module

Displays processing outputs with flexible dual-pane comparison,
file navigation, and step navigation.

Renamed from OutputView (Phase 2.3) to better reflect its role as a preview/display view,
distinct from adjustment/editing functionality.
"""

from .preview_view import PreviewView

__all__ = ['PreviewView']
