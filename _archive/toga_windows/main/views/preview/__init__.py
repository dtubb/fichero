"""
Preview Module - Dedicated Preview Panes

Contains specialized preview components:
- PreviewImagePane: For displaying processed images
- PreviewMetadataPane: For displaying transcriptions and metadata

Simplified from the complex old PreviewView system.
"""

from .preview_image_pane import PreviewImagePane
from .preview_metadata_pane import PreviewMetadataPane
from .preview_view import PreviewView

__all__ = ['PreviewImagePane', 'PreviewMetadataPane', 'PreviewView']