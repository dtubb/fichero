"""
EnhanceRenderer - Renderer for enhance tool output

Extends ImageRenderer to provide enhance-specific JSON editing capabilities.
Displays enhanced images with interactive viewer and allows editing enhancement parameters.
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import ImageRenderer

logger = logging.getLogger(__name__)


class EnhanceRenderer(ImageRenderer):
    """
    Renderer for enhance tool output.

    Extends ImageRenderer with enhance-specific JSON editing:
    - Displays enhanced image with interactive viewer
    - Provides editable JSON with contrast, brightness, sharpness
    - Can re-run enhance with new parameters

    Example manifest entry:
        {
            "path": "enhanced/file.jpg",
            "type": "file",
            "contrast": 1.5,
            "brightness": 1.1,
            "sharpness": 1.2,
            "method": "auto"
        }
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """
        Render enhanced image with interactive viewer.

        Uses parent ImageRenderer for display, which handles
        interactive viewer with zoom/rotate controls.

        Args:
            context: Rendering context

        Returns:
            RenderedOutput with HTML
        """
        # Use parent ImageRenderer for HTML rendering
        return super().render_html(context)

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """
        Render enhancement info for CLI.

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

        # Enhancement info from manifest
        if context.manifest_entry:
            enhance_data = self._extract_enhance_data(context.manifest_entry)

            text_parts.append("Enhancement Parameters:")
            text_parts.append(f"  Contrast: {enhance_data.get('contrast', 1.0)}")
            text_parts.append(f"  Brightness: {enhance_data.get('brightness', 1.0)}")
            text_parts.append(f"  Sharpness: {enhance_data.get('sharpness', 1.0)}")
            text_parts.append(f"  Method: {enhance_data.get('method', 'auto')}")
            text_parts.append("")

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f"Enhanced image: {context.file_path.name}"
        )

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """
        Get editable JSON for enhancement parameters.

        Returns contrast, brightness, sharpness from manifest entry.

        Args:
            context: Rendering context

        Returns:
            Dictionary with editable enhancement parameters or None
        """
        if not context.manifest_entry:
            logger.warning("No manifest entry in context, cannot extract enhancement data")
            return None

        enhance_data = self._extract_enhance_data(context.manifest_entry)

        if not enhance_data:
            logger.warning("No enhancement data found in manifest entry")
            return None

        return enhance_data

    def _extract_enhance_data(self, manifest_entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract enhancement-specific data from manifest entry.

        Args:
            manifest_entry: Manifest entry dictionary

        Returns:
            Dictionary with contrast, brightness, sharpness, method
        """
        enhance_data = {}

        # Contrast (default 1.0)
        enhance_data['contrast'] = manifest_entry.get('contrast', 1.0)

        # Brightness (default 1.0)
        enhance_data['brightness'] = manifest_entry.get('brightness', 1.0)

        # Sharpness (default 1.0)
        enhance_data['sharpness'] = manifest_entry.get('sharpness', 1.0)

        # Method (default 'auto')
        enhance_data['method'] = manifest_entry.get('method', 'auto')

        return enhance_data

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate edited enhancement JSON.

        Checks:
        - contrast is a positive number
        - brightness is a positive number
        - sharpness is a positive number
        - method is valid ('auto', 'manual')

        Args:
            json_data: Edited JSON data

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check contrast
        if 'contrast' in json_data:
            contrast = json_data['contrast']

            if not isinstance(contrast, (int, float)):
                return False, f"contrast must be a number, got {type(contrast).__name__}"

            if contrast <= 0:
                return False, f"contrast must be positive, got {contrast}"

        # Check brightness
        if 'brightness' in json_data:
            brightness = json_data['brightness']

            if not isinstance(brightness, (int, float)):
                return False, f"brightness must be a number, got {type(brightness).__name__}"

            if brightness <= 0:
                return False, f"brightness must be positive, got {brightness}"

        # Check sharpness
        if 'sharpness' in json_data:
            sharpness = json_data['sharpness']

            if not isinstance(sharpness, (int, float)):
                return False, f"sharpness must be a number, got {type(sharpness).__name__}"

            if sharpness <= 0:
                return False, f"sharpness must be positive, got {sharpness}"

        # Check method
        if 'method' in json_data:
            method = json_data['method']
            valid_methods = ['auto', 'manual']

            if method not in valid_methods:
                return False, f"method must be one of {valid_methods}, got '{method}'"

        return True, None

    def apply_json_edits(
        self,
        context: RenderContext,
        json_data: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Apply edited enhancement parameters and re-run enhance tool.

        This is a placeholder for now. Full implementation would:
        1. Get source image from previous step
        2. Call enhance tool with new parameters
        3. Update manifest with new enhancement data
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

        # TODO: Implement re-enhancement
        # For now, just log and return success
        logger.info(f"Would re-enhance with parameters: {json.dumps(json_data, indent=2)}")
        logger.warning("apply_json_edits not fully implemented yet - changes not saved")

        return False, "Re-enhancement not implemented yet (placeholder)"
