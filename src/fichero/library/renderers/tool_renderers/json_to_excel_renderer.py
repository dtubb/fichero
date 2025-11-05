"""JsonToExcelRenderer - Renderer for json_to_excel tool"""
import logging
from typing import Dict, Any, Optional
from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import DocumentRenderer

class JsonToExcelRenderer(DocumentRenderer):
    def render_cli(self, context: RenderContext) -> RenderedOutput:
        return RenderedOutput(text=f"Step {context.step_index}: {context.step_name}\nJSON→Excel: {context.file_path}", title=context.step_name)
    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        if not context.manifest_entry: return None
        return {'sheet_name': context.manifest_entry.get('sheet_name', 'Sheet1')}
    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        return True, None
    def apply_json_edits(self, context: RenderContext, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        return False, "Not implemented"
