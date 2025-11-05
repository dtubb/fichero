"""FuzzyCleanRenderer - Renderer for fuzzy_clean tool"""
import logging
from typing import Dict, Any, Optional
from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import TextRenderer

class FuzzyCleanRenderer(TextRenderer):
    def render_cli(self, context: RenderContext) -> RenderedOutput:
        return RenderedOutput(text=f"Step {context.step_index}: {context.step_name}\nFuzzy Text Cleaning", title=context.step_name)
    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        if not context.manifest_entry: return None
        return {'fuzzy_threshold': context.manifest_entry.get('fuzzy_threshold', 0.8)}
    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        return True, None
    def apply_json_edits(self, context: RenderContext, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        return False, "Not implemented"
