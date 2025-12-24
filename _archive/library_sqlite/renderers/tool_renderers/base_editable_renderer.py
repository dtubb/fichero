"""
EditableToolRenderer - Base class for tool renderers with interactive editing

This base class implements the DRY principle for tool renderers that need
to display interactive editors (crop, enhance, rotate, etc.).

Architecture:
- Library backend enriches manifests with resolved paths (SMART layer)
- Renderers trust the enriched data (DUMB layer)
- No path guessing or fallback logic in renderers

The library backend (_enrich_manifest_entry in library_manager.py) is
responsible for ALL path resolution. Renderers simply use the provided
paths without any fallback logic.
"""

import logging
from pathlib import Path
from typing import Optional

from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import ImageRenderer

logger = logging.getLogger(__name__)


class EditableToolRenderer(ImageRenderer):
    """
    Base class for tool renderers that support interactive editing.

    Subclasses override render_interactive() to provide tool-specific UI.

    Example:
        class CropRenderer(EditableToolRenderer):
            def render_interactive(self, context: RenderContext, source_path: Path) -> RenderedOutput:
                # Show crop editor with source image
                from ..html_templates_crop import get_rubberband_crop_viewer
                crop_box = context.manifest_entry.get('details', {}).get('box')
                html = get_rubberband_crop_viewer(
                    image_path=source_path,
                    crop_box=crop_box,
                    title=f"Crop Editor: {context.step_name}",
                    use_base64=True,
                    item_id=context.item_id,
                    step_index=context.step_index
                )
                return RenderedOutput(
                    html=html,
                    title=context.step_name,
                    description=f'Interactive crop editor: {context.file_path.name}'
                )
    """

    def get_source_path(self, context: RenderContext) -> Optional[Path]:
        """
        Get source file path from library-enriched manifest.

        Returns None if library backend didn't provide it.
        Renderers should fall back to static display when None.

        Args:
            context: Rendering context with manifest_entry

        Returns:
            Path to source file, or None if not available
        """
        if not context.manifest_entry:
            logger.debug(f"No manifest_entry in context for {context.step_name}")
            return None

        source_path_str = context.manifest_entry.get('source_image_path')
        if not source_path_str:
            logger.debug(f"No source_image_path in manifest_entry for {context.step_name}")
            return None

        source_path = Path(source_path_str)

        # Verify file exists (library backend should have checked this already)
        if not source_path.exists():
            logger.warning(
                f"source_image_path in manifest doesn't exist: {source_path}\n"
                f"This indicates a bug in library backend path resolution."
            )
            return None

        return source_path

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """
        Render with interactive editor if source path available.

        Args:
            context: Rendering context

        Returns:
            RenderedOutput with HTML for interactive editor or static display
        """
        # Only show interactive editor if all conditions are met
        if not (context.interactive and context.show_content and context.manifest_entry):
            logger.debug(
                f"Conditions not met for interactive editor: "
                f"interactive={context.interactive}, "
                f"show_content={context.show_content}, "
                f"has_manifest={context.manifest_entry is not None}"
            )
            return super().render_html(context)

        # Get source path from library-enriched manifest
        source_path = self.get_source_path(context)

        if not source_path:
            # No enriched path - fall back to static display
            logger.info(
                f"No source path available for {context.step_name}, "
                f"falling back to static display"
            )
            return super().render_html(context)

        # Call subclass method to render interactive editor
        logger.info(
            f"Rendering interactive editor for {context.step_name} "
            f"with source: {source_path}"
        )
        return self.render_interactive(context, source_path)

    def render_interactive(self, context: RenderContext, source_path: Path) -> RenderedOutput:
        """
        Render interactive editor for this tool.

        Subclasses MUST override this to show their specific editor UI.

        Args:
            context: Rendering context with all metadata
            source_path: Resolved path to source file (guaranteed to exist)

        Returns:
            RenderedOutput with interactive editor HTML
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement render_interactive()"
        )


# Template for implementing other editable renderers:
"""
Example: EnhanceRenderer

from ..tool_renderers.base_editable_renderer import EditableToolRenderer

class EnhanceRenderer(EditableToolRenderer):
    '''Renderer for enhance tool with interactive parameter editor'''

    def render_interactive(self, context: RenderContext, source_path: Path) -> RenderedOutput:
        '''Show interactive enhancement editor with sliders for contrast/brightness/sharpness'''
        # Extract enhancement parameters from manifest
        params = context.manifest_entry.get('details', {})

        # Use existing image editor template with enhancement controls
        from ..html_templates_image_editor import get_image_editor
        html = get_image_editor(
            image_path=source_path,
            title=f"Enhance Editor: {context.step_name}",
            use_base64=True,
            # Pass enhancement params to template
            enhancement_params={
                'contrast': params.get('contrast', 1.0),
                'brightness': params.get('brightness', 1.0),
                'sharpness': params.get('sharpness', 1.0)
            }
        )

        return RenderedOutput(
            html=html,
            title=context.step_name,
            description=f'Interactive enhancement editor: {context.file_path.name}'
        )

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        '''Extract enhancement parameters for JSON editor'''
        if not context.manifest_entry:
            return None

        return {
            'contrast': context.manifest_entry.get('contrast', 1.0),
            'brightness': context.manifest_entry.get('brightness', 1.0),
            'sharpness': context.manifest_entry.get('sharpness', 1.0),
            'method': context.manifest_entry.get('method', 'auto')
        }

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        '''Validate enhancement parameters are positive numbers'''
        for param in ['contrast', 'brightness', 'sharpness']:
            if param in json_data:
                value = json_data[param]
                if not isinstance(value, (int, float)) or value <= 0:
                    return False, f"{param} must be a positive number"
        return True, None

    async def apply_json_edits(self, context: RenderContext, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        '''Re-run enhance tool with new parameters'''
        # Use get_source_path() - no fallback logic needed!
        source_path = self.get_source_path(context)
        if not source_path:
            return False, "Source path not available"

        # Call enhance tool with new parameters
        from fichero.tools.enhance import enhance_image
        success = enhance_image(
            source_path,
            context.file_path,
            contrast=json_data.get('contrast', 1.0),
            brightness=json_data.get('brightness', 1.0),
            sharpness=json_data.get('sharpness', 1.0)
        )

        return success, None if success else "Enhancement failed"
"""
