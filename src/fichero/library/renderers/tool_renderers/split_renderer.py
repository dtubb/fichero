"""
SplitRenderer - Renderer for split tool output

Extends FolderRenderer since split creates multiple output images.
Shows gallery view of all split pages with split parameters.
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import FolderRenderer

logger = logging.getLogger(__name__)


class SplitRenderer(FolderRenderer):
    """
    Renderer for split tool output.

    Extends FolderRenderer since split creates a folder of split images:
    - Displays gallery view of all split pages
    - Provides editable JSON with split parameters
    - Can re-run split with new parameters

    Example manifest entry:
        {
            "path": "split/",
            "type": "folder",
            "split_method": "auto",
            "split_count": 2,
            "overlap": 0,
            "detection_threshold": 0.5,
            "files": ["page_1.jpg", "page_2.jpg"]
        }
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """
        Render split output with interactive split editor.

        If viewing with manifest data, show interactive split controls
        that allow adjusting split positions.

        Args:
            context: Rendering context

        Returns:
            RenderedOutput with HTML
        """
        # Use interactive split viewer if we have manifest data
        if context.interactive and context.show_content and context.manifest_entry:
            details = context.manifest_entry.get('details', {})
            split_positions = details.get('split_positions', [])

            # Get the source image path (before split)
            source_file = context.manifest_entry.get('source', '')
            logger.info(f"[SplitRenderer] source_file from manifest: {source_file}")

            if source_file and split_positions:
                # Build path to source image
                # context.file_path is like: .../item.tif/assets/split/
                # Source could be in various directories
                item_dir = context.file_path.parent.parent

                # Try to find source in various directories
                possible_dirs = ['split', 'rotated', 'cropped', 'original']
                source_path = None

                for dir_name in possible_dirs:
                    candidate_path = item_dir / 'assets' / dir_name / source_file
                    logger.info(f"[SplitRenderer] Checking: {candidate_path}")
                    if candidate_path.exists():
                        source_path = candidate_path
                        logger.info(f"[SplitRenderer] Found source at: {source_path}")
                        break

                if source_path and source_path.exists():
                    from ..html_templates_split import get_split_viewer

                    html = get_split_viewer(
                        image_path=source_path,
                        split_positions=split_positions,
                        title=f"Split Editor: {context.step_name}",
                        use_base64=True
                    )
                    return RenderedOutput(
                        html=html,
                        title=context.step_name,
                        description=f'Interactive split editor: {context.file_path.name}'
                    )
                else:
                    logger.warning(f"[SplitRenderer] Source not found: {source_file}")

        # Fallback: use parent FolderRenderer for gallery view
        return super().render_html(context)

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """Render split info for CLI"""
        text_parts = []

        # Title
        text_parts.append(f"Step {context.step_index}: {context.step_name}")
        text_parts.append("=" * 60)
        text_parts.append("")

        # Folder info
        text_parts.append(f"Folder: {context.file_path}")
        text_parts.append(f"Type: {context.file_type}")
        text_parts.append("")

        # Split info from manifest
        if context.manifest_entry:
            split_data = self._extract_split_data(context.manifest_entry)

            text_parts.append("Split Parameters:")
            text_parts.append(f"  Method: {split_data.get('split_method', 'auto')}")
            text_parts.append(f"  Split Count: {split_data.get('split_count', 2)}")
            text_parts.append(f"  Overlap: {split_data.get('overlap', 0)}px")
            text_parts.append(f"  Detection Threshold: {split_data.get('detection_threshold', 0.5)}")

            if 'files' in split_data:
                text_parts.append(f"  Output Files: {len(split_data['files'])}")

            text_parts.append("")

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f"Split pages: {context.file_path.name}"
        )

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """Get editable JSON for split parameters"""
        if not context.manifest_entry:
            logger.warning("No manifest entry in context")
            return None

        return self._extract_split_data(context.manifest_entry)

    def _extract_split_data(self, manifest_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract split-specific data from manifest entry"""
        return {
            'split_method': manifest_entry.get('split_method', 'auto'),
            'split_count': manifest_entry.get('split_count', 2),
            'overlap': manifest_entry.get('overlap', 0),
            'detection_threshold': manifest_entry.get('detection_threshold', 0.5),
            'files': manifest_entry.get('files', [])
        }

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate edited split JSON"""
        if 'split_method' in json_data:
            method = json_data['split_method']
            if method not in ['auto', 'manual', 'center']:
                return False, f"split_method must be 'auto', 'manual', or 'center', got '{method}'"

        if 'split_count' in json_data:
            count = json_data['split_count']
            if not isinstance(count, int) or count < 2:
                return False, f"split_count must be integer >= 2, got {count}"

        if 'overlap' in json_data:
            overlap = json_data['overlap']
            if not isinstance(overlap, int) or overlap < 0:
                return False, f"overlap must be non-negative integer, got {overlap}"

        if 'detection_threshold' in json_data:
            threshold = json_data['detection_threshold']
            if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
                return False, f"detection_threshold must be 0-1, got {threshold}"

        return True, None

    def apply_json_edits(self, context: RenderContext, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Apply edited split parameters and re-run tool"""
        is_valid, error = self.validate_json(json_data)
        if not is_valid:
            return False, error

        logger.info(f"Would re-split with parameters: {json.dumps(json_data, indent=2)}")
        logger.warning("apply_json_edits not fully implemented yet")

        return False, "Re-splitting not implemented yet (placeholder)"
