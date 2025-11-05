"""
SegmentRenderer - Renderer for segment tool output

Extends FolderRenderer since segment creates multiple output segments.
Shows gallery view of all segments with segmentation parameters.
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import FolderRenderer

logger = logging.getLogger(__name__)


class SegmentRenderer(FolderRenderer):
    """
    Renderer for segment tool output.

    Extends FolderRenderer to display gallery of segmented regions.

    Example manifest entry:
        {
            "path": "segments/",
            "type": "folder",
            "segment_method": "contour",
            "min_area": 1000,
            "padding": 10,
            "segment_count": 15
        }
    """

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """Render segment info for CLI"""
        text_parts = []

        text_parts.append(f"Step {context.step_index}: {context.step_name}")
        text_parts.append("=" * 60)
        text_parts.append("")
        text_parts.append(f"Folder: {context.file_path}")
        text_parts.append(f"Type: {context.file_type}")
        text_parts.append("")

        if context.manifest_entry:
            data = self._extract_segment_data(context.manifest_entry)
            text_parts.append("Segmentation Parameters:")
            text_parts.append(f"  Method: {data.get('segment_method', 'contour')}")
            text_parts.append(f"  Min Area: {data.get('min_area', 1000)}px²")
            text_parts.append(f"  Padding: {data.get('padding', 10)}px")
            text_parts.append(f"  Segments: {data.get('segment_count', 0)}")
            text_parts.append("")

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f"Segmented regions: {context.file_path.name}"
        )

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """Get editable JSON for segment parameters"""
        if not context.manifest_entry:
            return None
        return self._extract_segment_data(context.manifest_entry)

    def _extract_segment_data(self, manifest_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract segment-specific data"""
        return {
            'segment_method': manifest_entry.get('segment_method', 'contour'),
            'min_area': manifest_entry.get('min_area', 1000),
            'padding': manifest_entry.get('padding', 10),
            'segment_count': manifest_entry.get('segment_count', 0)
        }

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate segment JSON"""
        if 'segment_method' in json_data:
            method = json_data['segment_method']
            if method not in ['contour', 'threshold', 'adaptive']:
                return False, f"segment_method must be 'contour', 'threshold', or 'adaptive'"

        if 'min_area' in json_data:
            area = json_data['min_area']
            if not isinstance(area, int) or area < 0:
                return False, f"min_area must be non-negative integer"

        if 'padding' in json_data:
            padding = json_data['padding']
            if not isinstance(padding, int) or padding < 0:
                return False, f"padding must be non-negative integer"

        return True, None

    def apply_json_edits(self, context: RenderContext, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Apply edited segment parameters"""
        is_valid, error = self.validate_json(json_data)
        if not is_valid:
            return False, error

        logger.info(f"Would re-segment with: {json.dumps(json_data, indent=2)}")
        return False, "Re-segmentation not implemented yet"
