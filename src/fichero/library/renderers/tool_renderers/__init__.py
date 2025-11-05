"""
Tool-specific renderers

This package contains renderers for specific processing tools.
Each tool can provide its own renderer with custom display and editing logic.
"""

# Image processing renderers
from .crop_renderer import CropRenderer
from .rotate_renderer import RotateRenderer
from .enhance_renderer import EnhanceRenderer
from .remove_background_renderer import RemoveBackgroundRenderer
from .prepare_images_renderer import PrepareImagesRenderer
from .split_renderer import SplitRenderer
from .segment_renderer import SegmentRenderer
from .recombine_renderer import RecombineRenderer

# AI/text processing renderers
from .transcribe_renderer import TranscribeRenderer
from .describe_renderer import DescribeRenderer
from .llm_process_renderer import LLMProcessRenderer

# Document generation renderers
from .convert_to_word_renderer import ConvertToWordRenderer
from .convert_to_svg_renderer import ConvertToSVGRenderer
from .json_to_word_renderer import JsonToWordRenderer
from .json_to_excel_renderer import JsonToExcelRenderer

# Metadata/analysis renderers
from .analyze_groups_renderer import AnalyzeGroupsRenderer
from .extract_metadata_renderer import ExtractMetadataRenderer
from .build_manifest_renderer import BuildManifestRenderer
from .fuzzy_clean_renderer import FuzzyCleanRenderer

__all__ = [
    # Image processing
    'CropRenderer',
    'RotateRenderer',
    'EnhanceRenderer',
    'RemoveBackgroundRenderer',
    'PrepareImagesRenderer',
    'SplitRenderer',
    'SegmentRenderer',
    'RecombineRenderer',
    # AI/text
    'TranscribeRenderer',
    'DescribeRenderer',
    'LLMProcessRenderer',
    # Documents
    'ConvertToWordRenderer',
    'ConvertToSVGRenderer',
    'JsonToWordRenderer',
    'JsonToExcelRenderer',
    # Metadata
    'AnalyzeGroupsRenderer',
    'ExtractMetadataRenderer',
    'BuildManifestRenderer',
    'FuzzyCleanRenderer',
]
