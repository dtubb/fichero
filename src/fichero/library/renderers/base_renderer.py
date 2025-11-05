"""
Base Renderer - Abstract base class for all tool renderers

This module provides the foundation for the renderer plugin system.
Each tool can have its own renderer that knows how to display its outputs.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RenderContext:
    """Context information for rendering"""
    # Step data
    item_id: str
    step_index: int
    step_name: str
    tool_name: str
    file_path: Path
    file_type: str

    # Optional data
    manifest_entry: Optional[Dict[str, Any]] = None
    file_content: Optional[Any] = None

    # Rendering options
    show_metadata: bool = True
    show_content: bool = True
    interactive: bool = False  # For GUI vs CLI rendering

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'item_id': self.item_id,
            'step_index': self.step_index,
            'step_name': self.step_name,
            'tool_name': self.tool_name,
            'file_path': str(self.file_path),
            'file_type': self.file_type,
            'manifest_entry': self.manifest_entry,
            'show_metadata': self.show_metadata,
            'show_content': self.show_content,
            'interactive': self.interactive
        }


@dataclass
class RenderedOutput:
    """Output from a renderer"""
    # Primary content
    html: Optional[str] = None  # HTML for GUI display
    text: Optional[str] = None  # Plain text for CLI

    # Metadata
    title: Optional[str] = None
    description: Optional[str] = None

    # Additional data for specialized renderers
    data: Optional[Dict[str, Any]] = None

    # Toolbar integration - Renderer can declare toolbar buttons it needs
    # Each command dict should have: id, label, icon, action (JS function name), shortcut (optional)
    toolbar_commands: Optional[List[Dict[str, Any]]] = None

    # Error handling
    error: Optional[str] = None

    @property
    def is_error(self) -> bool:
        """Check if rendering failed"""
        return self.error is not None

    @property
    def has_content(self) -> bool:
        """Check if there's renderable content"""
        return (self.html is not None or self.text is not None) and not self.is_error


class BaseRenderer(ABC):
    """
    Abstract base class for all renderers.

    Each tool-specific renderer should:
    1. Subclass BaseRenderer (or a type-specific base like ImageRenderer)
    2. Implement render_html() and render_cli()
    3. Optionally implement get_editable_json() and apply_json_edits()
    4. Register itself with the RendererRegistry

    Example:
        class PrepareImagesRenderer(ImageRenderer):
            def render_html(self, context: RenderContext) -> RenderedOutput:
                # Generate HTML for GUI
                ...

            def render_cli(self, context: RenderContext) -> RenderedOutput:
                # Generate text for CLI
                ...
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def render_html(self, context: RenderContext) -> RenderedOutput:
        """
        Render step data as HTML for GUI display.

        Args:
            context: Rendering context with step data

        Returns:
            RenderedOutput with HTML content
        """
        pass

    @abstractmethod
    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """
        Render step data as text for CLI display.

        Args:
            context: Rendering context with step data

        Returns:
            RenderedOutput with text content
        """
        pass

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """
        Get JSON representation suitable for editing.

        Override this to provide custom editing capabilities for a tool.

        Args:
            context: Rendering context with step data

        Returns:
            Dictionary of editable data or None if editing not supported
        """
        return None

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate edited JSON before applying.

        Args:
            json_data: Edited JSON data

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Default: accept all edits
        return True, None

    def apply_json_edits(
        self,
        context: RenderContext,
        json_data: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Apply JSON edits back to files/manifests.

        Override this to implement custom edit-save logic.

        Args:
            context: Rendering context
            json_data: Edited JSON data

        Returns:
            Tuple of (success, error_message)
        """
        return False, "Editing not implemented for this renderer"

    def get_metadata(self, context: RenderContext) -> Dict[str, Any]:
        """
        Extract metadata from step data.

        Override this to provide custom metadata extraction.

        Args:
            context: Rendering context

        Returns:
            Dictionary of metadata
        """
        metadata = {
            'item_id': context.item_id,
            'step_index': context.step_index,
            'step_name': context.step_name,
            'tool_name': context.tool_name,
            'file_path': str(context.file_path),
            'file_type': context.file_type
        }

        if context.manifest_entry:
            metadata['manifest'] = context.manifest_entry

        return metadata

    def format_metadata_html(self, metadata: Dict[str, Any]) -> str:
        """
        Format metadata as HTML.

        Args:
            metadata: Metadata dictionary

        Returns:
            HTML string
        """
        html_parts = ['<div class="metadata">']
        html_parts.append('<h3>Metadata</h3>')
        html_parts.append('<table>')

        for key, value in metadata.items():
            if key == 'manifest':
                continue  # Handle separately
            html_parts.append(f'<tr><th>{key}</th><td>{value}</td></tr>')

        html_parts.append('</table>')
        html_parts.append('</div>')

        return '\n'.join(html_parts)

    def format_metadata_cli(self, metadata: Dict[str, Any]) -> str:
        """
        Format metadata as plain text for CLI.

        Args:
            metadata: Metadata dictionary

        Returns:
            Text string
        """
        lines = ['Metadata:']
        for key, value in metadata.items():
            if key == 'manifest':
                continue  # Handle separately
            lines.append(f'  {key}: {value}')

        return '\n'.join(lines)


class FallbackRenderer(BaseRenderer):
    """
    Fallback renderer for tools without specific renderers.

    Provides basic rendering based on file type.
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """Basic HTML rendering"""
        metadata = self.get_metadata(context)
        html_parts = []

        # Title
        html_parts.append(f'<h2>{context.step_name}</h2>')

        # Metadata
        if context.show_metadata:
            html_parts.append(self.format_metadata_html(metadata))

        # Content based on file type
        if context.show_content and context.file_content:
            html_parts.append('<div class="content">')

            if context.file_type == 'text':
                html_parts.append(f'<pre>{context.file_content}</pre>')
            elif context.file_type == 'json':
                import json
                html_parts.append(f'<pre>{json.dumps(context.file_content, indent=2)}</pre>')
            elif context.file_type == 'image':
                html_parts.append(f'<img src="file://{context.file_path}" />')
            else:
                html_parts.append(f'<p>File type: {context.file_type}</p>')
                html_parts.append(f'<p>Path: {context.file_path}</p>')

            html_parts.append('</div>')

        return RenderedOutput(
            html='\n'.join(html_parts),
            title=context.step_name,
            description=f'Step {context.step_index}: {context.step_name}'
        )

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """Basic CLI rendering"""
        metadata = self.get_metadata(context)
        text_parts = []

        # Title
        text_parts.append(f'Step {context.step_index}: {context.step_name}')
        text_parts.append('=' * 60)

        # Metadata
        if context.show_metadata:
            text_parts.append('')
            text_parts.append(self.format_metadata_cli(metadata))

        # Content
        if context.show_content and context.file_content:
            text_parts.append('')
            text_parts.append('Content:')
            text_parts.append('-' * 60)

            if context.file_type == 'text':
                text_parts.append(context.file_content)
            elif context.file_type == 'json':
                import json
                text_parts.append(json.dumps(context.file_content, indent=2))
            else:
                text_parts.append(f'File type: {context.file_type}')
                text_parts.append(f'Path: {context.file_path}')

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f'Step {context.step_index}: {context.step_name}'
        )
