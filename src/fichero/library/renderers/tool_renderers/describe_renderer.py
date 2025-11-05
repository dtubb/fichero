"""DescribeRenderer - Renderer for describe_images tool output"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import JsonRenderer

logger = logging.getLogger(__name__)


class DescribeRenderer(JsonRenderer):
    """Renderer for describe_images tool - outputs JSON descriptions"""

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        text_parts = [
            f"Step {context.step_index}: {context.step_name}",
            "=" * 60,
            "",
            f"File: {context.file_path}",
            ""
        ]

        if context.manifest_entry:
            data = context.manifest_entry
            text_parts.extend([
                "Description Parameters:",
                f"  Model: {data.get('model', 'qwen-vl')}",
                f"  Description Type: {data.get('description_type', 'general')}",
                f"  Detail Level: {data.get('detail_level', 'medium')}",
                ""
            ])

        return RenderedOutput(text='\n'.join(text_parts), title=context.step_name)

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        if not context.manifest_entry:
            return None
        return {
            'model': context.manifest_entry.get('model', 'qwen-vl'),
            'description_type': context.manifest_entry.get('description_type', 'general'),
            'detail_level': context.manifest_entry.get('detail_level', 'medium')
        }

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        if 'detail_level' in json_data and json_data['detail_level'] not in ['low', 'medium', 'high']:
            return False, "detail_level must be 'low', 'medium', or 'high'"
        return True, None

    def apply_json_edits(self, context: RenderContext, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        return False, "Re-description not implemented yet"
