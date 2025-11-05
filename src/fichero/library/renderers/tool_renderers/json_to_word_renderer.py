"""JsonToWordRenderer - Renderer for json_to_word tool"""
import logging
from typing import Dict, Any, Optional
from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import DocumentRenderer

class JsonToWordRenderer(DocumentRenderer):
    def render_cli(self, context: RenderContext) -> RenderedOutput:
        return RenderedOutput(text=f"Step {context.step_index}: {context.step_name}\nJSON→Word: {context.file_path}", title=context.step_name)
    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        if not context.manifest_entry: return None
        return {'template': context.manifest_entry.get('template', 'default')}
    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        return True, None
    def apply_json_edits(self, context: RenderContext, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        return False, "Not implemented"
