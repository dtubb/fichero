"""
RemoveBackgroundRenderer - Renderer for remove_background tool output

Extends ImageRenderer to provide background removal-specific JSON editing.
Displays images with transparent/removed backgrounds and allows editing removal parameters.
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import ImageRenderer

logger = logging.getLogger(__name__)


class RemoveBackgroundRenderer(ImageRenderer):
    """
    Renderer for remove_background tool output.

    Extends ImageRenderer with background removal-specific JSON editing:
    - Displays image with removed background
    - Provides editable JSON with method, threshold, edge_smoothing
    - Can re-run background removal with new parameters

    Example manifest entry:
        {
            "path": "no_bg/file.png",
            "type": "file",
            "method": "rembg",
            "model": "u2net",
            "alpha_matting": true,
            "alpha_matting_foreground_threshold": 240,
            "alpha_matting_background_threshold": 10
        }
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """
        Render image with removed background.

        Uses parent ImageRenderer for display, which handles
        interactive viewer with zoom/rotate controls.

        Args:
            context: Rendering context

        Returns:
            RenderedOutput with HTML
        """
        # Use parent ImageRenderer for HTML rendering
        # The image will have transparency if background was removed
        return super().render_html(context)

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """
        Render background removal info for CLI.

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

        # Background removal info from manifest
        if context.manifest_entry:
            bg_data = self._extract_bg_removal_data(context.manifest_entry)

            text_parts.append("Background Removal Parameters:")
            text_parts.append(f"  Method: {bg_data.get('method', 'rembg')}")
            text_parts.append(f"  Model: {bg_data.get('model', 'u2net')}")
            text_parts.append(f"  Alpha Matting: {bg_data.get('alpha_matting', False)}")

            if bg_data.get('alpha_matting'):
                text_parts.append(f"  Foreground Threshold: {bg_data.get('alpha_matting_foreground_threshold', 240)}")
                text_parts.append(f"  Background Threshold: {bg_data.get('alpha_matting_background_threshold', 10)}")

            text_parts.append("")

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f"Background removed: {context.file_path.name}"
        )

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """
        Get editable JSON for background removal parameters.

        Returns method, model, alpha_matting settings from manifest entry.

        Args:
            context: Rendering context

        Returns:
            Dictionary with editable parameters or None
        """
        if not context.manifest_entry:
            logger.warning("No manifest entry in context, cannot extract background removal data")
            return None

        bg_data = self._extract_bg_removal_data(context.manifest_entry)

        if not bg_data:
            logger.warning("No background removal data found in manifest entry")
            return None

        return bg_data

    def _extract_bg_removal_data(self, manifest_entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract background removal-specific data from manifest entry.

        Args:
            manifest_entry: Manifest entry dictionary

        Returns:
            Dictionary with method, model, alpha_matting parameters
        """
        bg_data = {}

        # Method (default 'rembg')
        bg_data['method'] = manifest_entry.get('method', 'rembg')

        # Model (default 'u2net')
        bg_data['model'] = manifest_entry.get('model', 'u2net')

        # Alpha matting (default False)
        bg_data['alpha_matting'] = manifest_entry.get('alpha_matting', False)

        # Alpha matting thresholds
        if bg_data['alpha_matting']:
            bg_data['alpha_matting_foreground_threshold'] = manifest_entry.get(
                'alpha_matting_foreground_threshold', 240
            )
            bg_data['alpha_matting_background_threshold'] = manifest_entry.get(
                'alpha_matting_background_threshold', 10
            )

        return bg_data

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate edited background removal JSON.

        Checks:
        - method is valid ('rembg', 'custom')
        - model is valid ('u2net', 'u2netp', 'u2net_human_seg', 'u2net_cloth_seg', 'silueta', 'isnet-general-use', 'isnet-anime')
        - alpha_matting is boolean
        - thresholds are in valid range (0-255)

        Args:
            json_data: Edited JSON data

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check method
        if 'method' in json_data:
            method = json_data['method']
            valid_methods = ['rembg', 'custom']

            if method not in valid_methods:
                return False, f"method must be one of {valid_methods}, got '{method}'"

        # Check model
        if 'model' in json_data:
            model = json_data['model']
            valid_models = [
                'u2net', 'u2netp', 'u2net_human_seg', 'u2net_cloth_seg',
                'silueta', 'isnet-general-use', 'isnet-anime'
            ]

            if model not in valid_models:
                return False, f"model must be one of {valid_models}, got '{model}'"

        # Check alpha_matting
        if 'alpha_matting' in json_data:
            alpha_matting = json_data['alpha_matting']

            if not isinstance(alpha_matting, bool):
                return False, f"alpha_matting must be boolean, got {type(alpha_matting).__name__}"

        # Check thresholds if alpha_matting is enabled
        if json_data.get('alpha_matting', False):
            # Foreground threshold
            if 'alpha_matting_foreground_threshold' in json_data:
                fg_threshold = json_data['alpha_matting_foreground_threshold']

                if not isinstance(fg_threshold, int):
                    return False, f"alpha_matting_foreground_threshold must be integer, got {type(fg_threshold).__name__}"

                if not 0 <= fg_threshold <= 255:
                    return False, f"alpha_matting_foreground_threshold must be 0-255, got {fg_threshold}"

            # Background threshold
            if 'alpha_matting_background_threshold' in json_data:
                bg_threshold = json_data['alpha_matting_background_threshold']

                if not isinstance(bg_threshold, int):
                    return False, f"alpha_matting_background_threshold must be integer, got {type(bg_threshold).__name__}"

                if not 0 <= bg_threshold <= 255:
                    return False, f"alpha_matting_background_threshold must be 0-255, got {bg_threshold}"

        return True, None

    def apply_json_edits(
        self,
        context: RenderContext,
        json_data: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Apply edited background removal parameters and re-run tool.

        This is a placeholder for now. Full implementation would:
        1. Get source image from previous step
        2. Call remove_background tool with new parameters
        3. Update manifest with new data
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

        # TODO: Implement re-processing
        # For now, just log and return success
        logger.info(f"Would re-remove background with parameters: {json.dumps(json_data, indent=2)}")
        logger.warning("apply_json_edits not fully implemented yet - changes not saved")

        return False, "Background removal re-processing not implemented yet (placeholder)"
