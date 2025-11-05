"""
Renderers Package - Tool-specific output renderers

This package provides a plugin architecture for rendering tool outputs.
Each tool can have its own renderer that knows how to display its outputs
in both GUI (HTML) and CLI (text) modes.
"""

from .base_renderer import (
    BaseRenderer,
    RenderContext,
    RenderedOutput,
    FallbackRenderer
)

from .type_renderers import (
    ImageRenderer,
    TextRenderer,
    JsonRenderer,
    DocumentRenderer,
    SvgRenderer,
    FolderRenderer
)

from .renderer_registry import RendererRegistry

__all__ = [
    'BaseRenderer',
    'RenderContext',
    'RenderedOutput',
    'FallbackRenderer',
    'ImageRenderer',
    'TextRenderer',
    'JsonRenderer',
    'DocumentRenderer',
    'SvgRenderer',
    'FolderRenderer',
    'RendererRegistry'
]
