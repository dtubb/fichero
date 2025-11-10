"""
Platform-adaptive list widget with extensible renderer system.

Public API exports:
- ListWidget: Main widget class with source-based architecture
- Platform: Platform enumeration
"""

from .base import ListWidget, Platform

__all__ = ['ListWidget', 'Platform']
