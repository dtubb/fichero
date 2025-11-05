"""
RecombineRenderer - Renderer for recombine_segments tool output
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import ImageRenderer

logger = logging.getLogger(__name__)


class RecombineRenderer(ImageRenderer):
    """Renderer for recombine_segments tool output"""

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """Render recombine info for CLI"""
        text_parts = [
            f"Step {context.step_index}: {context.step_name}",
            "=" * 60,
            "",
            f"File: {context.file_path}",
            f"Type: {context.file_type}",
            ""
        ]

        if context.manifest_entry:
            data = context.manifest_entry
            text_parts.append("Recombination Parameters:")
            text_parts.append(f"  Layout: {data.get('layout', 'grid')}")
            text_parts.append(f"  Spacing: {data.get('spacing', 0)}px")
            text_parts.append(f"  Background: {data.get('background_color', 'white')}")
            text_parts.append("")

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f"Recombined image: {context.file_path.name}"
        )

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        if not context.manifest_entry:
            return None
        return {
            'layout': context.manifest_entry.get('layout', 'grid'),
            'spacing': context.manifest_entry.get('spacing', 0),
            'background_color': context.manifest_entry.get('background_color', 'white')
        }

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        if 'layout' in json_data and json_data['layout'] not in ['grid', 'horizontal', 'vertical']:
            return False, "layout must be 'grid', 'horizontal', or 'vertical'"
        if 'spacing' in json_data and (not isinstance(json_data['spacing'], int) or json_data['spacing'] < 0):
            return False, "spacing must be non-negative integer"
        return True, None

    def apply_json_edits(self, context: RenderContext, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        is_valid, error = self.validate_json(json_data)
        if not is_valid:
            return False, error
        return False, "Recombination not implemented yet"
