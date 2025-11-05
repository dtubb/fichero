"""
RotateRenderer - Renderer for rotate tool output

Extends ImageRenderer to provide rotate-specific JSON editing capabilities.
Displays rotated images with interactive viewer and allows editing rotation parameters.
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import ImageRenderer

logger = logging.getLogger(__name__)


class RotateRenderer(ImageRenderer):
    """
    Renderer for rotate tool output.

    Extends ImageRenderer with rotate-specific JSON editing:
    - Displays rotated image with interactive viewer
    - Provides editable JSON with rotation angle
    - Can re-run rotate with new angle

    Example manifest entry:
        {
            "path": "rotated/file.jpg",
            "type": "file",
            "rotation_angle": 90,
            "direction": "clockwise"
        }
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """
        Render rotated image with interactive rotation editor.

        If viewing with manifest data, show interactive rotation controls
        that allow adjusting the rotation angle.

        Args:
            context: Rendering context

        Returns:
            RenderedOutput with HTML
        """
        # Use interactive rotate viewer if we have manifest data
        if context.interactive and context.show_content and context.manifest_entry:
            details = context.manifest_entry.get('details', {})
            current_angle = details.get('angle', 0)

            # Get the source image path (before rotation)
            source_file = context.manifest_entry.get('source', '')
            logger.info(f"[RotateRenderer] source_file from manifest: {source_file}")

            if source_file:
                # Build path to source image
                # context.file_path is like: .../item.tif/assets/rotated/file.jpg
                # Source could be in 'original' or from previous step (e.g., 'cropped')
                item_dir = context.file_path.parent.parent.parent

                # Try to find source in various directories
                possible_dirs = ['rotated', 'cropped', 'original']
                source_path = None

                for dir_name in possible_dirs:
                    candidate_path = item_dir / 'assets' / dir_name / source_file
                    logger.info(f"[RotateRenderer] Checking: {candidate_path}")
                    if candidate_path.exists():
                        source_path = candidate_path
                        logger.info(f"[RotateRenderer] Found source at: {source_path}")
                        break

                if not source_path:
                    logger.warning(f"[RotateRenderer] Source not found in any directory: {source_file}")
                    # Fallback: use the rotated image itself
                    source_path = context.file_path

                if source_path and source_path.exists():
                    from ..html_templates_rotate import get_rotate_viewer

                    html = get_rotate_viewer(
                        image_path=source_path,
                        current_angle=current_angle,
                        title=f"Rotate Editor: {context.step_name}",
                        use_base64=True
                    )
                    return RenderedOutput(
                        html=html,
                        title=context.step_name,
                        description=f'Interactive rotation editor: {context.file_path.name}'
                    )

        # Fallback: use parent ImageRenderer for standard display
        return super().render_html(context)

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """
        Render rotation info for CLI.

        Args:
            context: Rendering context

        Returns:
            RenderedOutput with text
        """
        text_parts = []

        # Title
        text_parts.append(f"Step {context.step_index}: {context.step_name}")
        text_parts.append("=" * 60)
        text_parts.append("")

        # File info
        text_parts.append(f"File: {context.file_path}")
        text_parts.append(f"Type: {context.file_type}")
        text_parts.append("")

        # Rotation info from manifest
        if context.manifest_entry:
            rotate_data = self._extract_rotate_data(context.manifest_entry)

            if 'rotation_angle' in rotate_data:
                text_parts.append(f"Rotation Angle: {rotate_data['rotation_angle']}°")

            if 'direction' in rotate_data:
                text_parts.append(f"Direction: {rotate_data['direction']}")

            text_parts.append("")

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f"Rotated image: {context.file_path.name}"
        )

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """
        Get editable JSON for rotation parameters.

        Returns rotation angle and direction from manifest entry.

        Args:
            context: Rendering context

        Returns:
            Dictionary with editable rotation parameters or None
        """
        if not context.manifest_entry:
            logger.warning("No manifest entry in context, cannot extract rotation data")
            return None

        rotate_data = self._extract_rotate_data(context.manifest_entry)

        if not rotate_data:
            logger.warning("No rotation data found in manifest entry")
            return None

        return rotate_data

    def _extract_rotate_data(self, manifest_entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract rotation-specific data from manifest entry.

        Args:
            manifest_entry: Manifest entry dictionary

        Returns:
            Dictionary with rotation_angle, direction
        """
        rotate_data = {}

        # Rotation angle (optional, default 90)
        rotate_data['rotation_angle'] = manifest_entry.get('rotation_angle', 90)

        # Direction (optional, default 'clockwise')
        rotate_data['direction'] = manifest_entry.get('direction', 'clockwise')

        return rotate_data

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate edited rotation JSON.

        Checks:
        - rotation_angle is a valid angle (0, 90, 180, 270, or -90, -180, -270)
        - direction is valid ('clockwise', 'counterclockwise')

        Args:
            json_data: Edited JSON data

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check rotation_angle
        if 'rotation_angle' in json_data:
            angle = json_data['rotation_angle']

            if not isinstance(angle, (int, float)):
                return False, f"rotation_angle must be a number, got {type(angle).__name__}"

            # Normalize to 0-360 range
            normalized_angle = angle % 360

            # Check if it's a multiple of 90
            if normalized_angle % 90 != 0:
                return False, f"rotation_angle must be a multiple of 90, got {angle}"

        # Check direction
        if 'direction' in json_data:
            direction = json_data['direction']
            valid_directions = ['clockwise', 'counterclockwise', 'cw', 'ccw']

            if direction not in valid_directions:
                return False, f"direction must be one of {valid_directions}, got '{direction}'"

        return True, None

    def apply_json_edits(
        self,
        context: RenderContext,
        json_data: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Apply edited rotation parameters and re-run rotate tool.

        This is a placeholder for now. Full implementation would:
        1. Get source image from previous step
        2. Call rotate tool with new angle
        3. Update manifest with new rotation data
        4. Return success/failure

        Args:
            context: Rendering context
            json_data: Edited JSON data

        Returns:
            Tuple of (success, error_message)
        """
        # Validate first
        is_valid, error = self.validate_json(json_data)
        if not is_valid:
            return False, error

        # TODO: Implement re-rotation
        # For now, just log and return success
        logger.info(f"Would re-rotate with parameters: {json.dumps(json_data, indent=2)}")
        logger.warning("apply_json_edits not fully implemented yet - changes not saved")

        return False, "Re-rotation not implemented yet (placeholder)"
