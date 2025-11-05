"""
RendererRegistry - Central registry for tool renderers

Maps tool names to renderer classes and provides fallback behavior.
Supports auto-discovery of renderers and intelligent fallbacks based on file type.
"""

import logging
from typing import Dict, Type, Optional
from pathlib import Path

from .base_renderer import BaseRenderer, FallbackRenderer
from .type_renderers import (
    ImageRenderer,
    TextRenderer,
    JsonRenderer,
    DocumentRenderer,
    SvgRenderer,
    FolderRenderer
)

logger = logging.getLogger(__name__)


class RendererRegistry:
    """
    Central registry for tool renderers.

    Provides:
    - Tool name → Renderer class mapping
    - File type-based fallbacks
    - Auto-discovery of custom renderers
    - Singleton pattern for global access

    Example:
        # Register a custom renderer
        RendererRegistry.register('prepare_images', PrepareImagesRenderer)

        # Get renderer for a tool
        renderer = RendererRegistry.get_renderer('prepare_images')

        # Get renderer with fallback
        renderer = RendererRegistry.get_renderer_for_step(
            tool_name='unknown_tool',
            file_type='image'
        )
    """

    _instance = None
    _renderers: Dict[str, Type[BaseRenderer]] = {}
    _type_renderers: Dict[str, Type[BaseRenderer]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize registry with built-in type renderers and tool renderers"""
        logger.info("Initializing RendererRegistry")

        # Clear registries
        self._renderers = {}
        self._type_renderers = {}

        # Register type-based fallback renderers
        self._type_renderers = {
            'image': ImageRenderer,
            'text': TextRenderer,
            'json': JsonRenderer,
            'document': DocumentRenderer,
            'svg': SvgRenderer,
            'folder': FolderRenderer
        }

        logger.info(f"Registered {len(self._type_renderers)} type renderers")

        # Register tool-specific renderers
        self._register_tool_renderers()

    def _register_tool_renderers(self):
        """Register tool-specific renderers"""
        try:
            from .tool_renderers import (
                # Image processing
                CropRenderer, RotateRenderer, EnhanceRenderer, RemoveBackgroundRenderer,
                PrepareImagesRenderer, SplitRenderer, SegmentRenderer, RecombineRenderer,
                # AI/text processing
                TranscribeRenderer, DescribeRenderer, LLMProcessRenderer,
                # Document generation
                ConvertToWordRenderer, ConvertToSVGRenderer, JsonToWordRenderer, JsonToExcelRenderer,
                # Metadata/analysis
                AnalyzeGroupsRenderer, ExtractMetadataRenderer, BuildManifestRenderer, FuzzyCleanRenderer
            )

            # Image processing renderers
            self._renderers['crop'] = CropRenderer
            self._renderers['rotate'] = RotateRenderer
            self._renderers['enhance'] = EnhanceRenderer
            self._renderers['remove_background'] = RemoveBackgroundRenderer
            self._renderers['prepare_images'] = PrepareImagesRenderer
            self._renderers['split'] = SplitRenderer
            self._renderers['segment'] = SegmentRenderer
            self._renderers['recombine_segments'] = RecombineRenderer

            # AI/text processing renderers
            self._renderers['transcribe_qwen_max'] = TranscribeRenderer
            self._renderers['transcribe_lmstudio'] = TranscribeRenderer  # Same renderer for both
            self._renderers['describe_images'] = DescribeRenderer
            self._renderers['llm_process'] = LLMProcessRenderer

            # Document generation renderers
            self._renderers['convert_to_word'] = ConvertToWordRenderer
            self._renderers['convert_to_svg'] = ConvertToSVGRenderer
            self._renderers['json_to_word'] = JsonToWordRenderer
            self._renderers['json_to_excel'] = JsonToExcelRenderer

            # Metadata/analysis renderers
            self._renderers['analyze_document_groups'] = AnalyzeGroupsRenderer
            self._renderers['extract_library_metadata'] = ExtractMetadataRenderer
            self._renderers['build_documents_manifest'] = BuildManifestRenderer
            self._renderers['fuzzy_clean'] = FuzzyCleanRenderer

            logger.info(f"Registered {len(self._renderers)} tool-specific renderers")

        except ImportError as e:
            logger.warning(f"Could not import tool renderers: {e}")
            logger.warning("Tool-specific renderers will not be available")

    @classmethod
    def register(cls, tool_name: str, renderer_class: Type[BaseRenderer]):
        """
        Register a renderer for a specific tool.

        Args:
            tool_name: Tool name (e.g. "prepare_images", "transcribe_qwen_max")
            renderer_class: Renderer class (must subclass BaseRenderer)

        Example:
            RendererRegistry.register('prepare_images', PrepareImagesRenderer)
        """
        instance = cls()

        if not issubclass(renderer_class, BaseRenderer):
            raise ValueError(f"Renderer must subclass BaseRenderer: {renderer_class}")

        instance._renderers[tool_name] = renderer_class
        logger.info(f"Registered renderer for tool: {tool_name} -> {renderer_class.__name__}")

    @classmethod
    def register_type(cls, file_type: str, renderer_class: Type[BaseRenderer]):
        """
        Register a renderer for a file type (for fallback).

        Args:
            file_type: File type ("image", "text", "json", etc.)
            renderer_class: Renderer class

        Example:
            RendererRegistry.register_type('image', CustomImageRenderer)
        """
        instance = cls()

        if not issubclass(renderer_class, BaseRenderer):
            raise ValueError(f"Renderer must subclass BaseRenderer: {renderer_class}")

        instance._type_renderers[file_type] = renderer_class
        logger.info(f"Registered type renderer: {file_type} -> {renderer_class.__name__}")

    @classmethod
    def get_renderer(
        cls,
        tool_name: str,
        create_instance: bool = True
    ) -> Optional[BaseRenderer | Type[BaseRenderer]]:
        """
        Get renderer for a specific tool.

        Args:
            tool_name: Tool name
            create_instance: If True, return instance; if False, return class

        Returns:
            Renderer instance/class or None if not found
        """
        instance = cls()

        renderer_class = instance._renderers.get(tool_name)

        if renderer_class:
            return renderer_class() if create_instance else renderer_class

        return None

    @classmethod
    def get_renderer_for_file_type(
        cls,
        file_type: str,
        create_instance: bool = True
    ) -> Optional[BaseRenderer | Type[BaseRenderer]]:
        """
        Get renderer based on file type.

        Args:
            file_type: File type ("image", "text", "json", "document", "folder", "svg")
            create_instance: If True, return instance; if False, return class

        Returns:
            Renderer instance/class or None

        Example:
            renderer = RendererRegistry.get_renderer_for_file_type('image')
        """
        instance = cls()

        renderer_class = instance._type_renderers.get(file_type)

        if renderer_class:
            return renderer_class() if create_instance else renderer_class

        return None

    @classmethod
    def get_renderer_for_step(
        cls,
        tool_name: str,
        file_type: Optional[str] = None,
        file_path: Optional[Path] = None,
        create_instance: bool = True
    ) -> BaseRenderer | Type[BaseRenderer]:
        """
        Get renderer for a processing step with intelligent fallback.

        Tries in order:
        1. Tool-specific renderer (e.g., PrepareImagesRenderer)
        2. File type renderer (e.g., ImageRenderer)
        3. File extension-based guess
        4. Generic FallbackRenderer

        Args:
            tool_name: Tool name
            file_type: File type hint ("image", "text", etc.)
            file_path: Optional path for extension-based detection
            create_instance: If True, return instance; if False, return class

        Returns:
            Renderer instance/class (never None, uses FallbackRenderer as last resort)

        Example:
            renderer = RendererRegistry.get_renderer_for_step(
                tool_name='prepare_images',
                file_type='image',
                file_path=Path('output.jpg')
            )
        """
        instance = cls()

        # 1. Try tool-specific renderer
        renderer_class = instance._renderers.get(tool_name)
        if renderer_class:
            logger.debug(f"Using tool-specific renderer for {tool_name}: {renderer_class.__name__}")
            return renderer_class() if create_instance else renderer_class

        # 2. Try file type renderer
        if file_type:
            renderer_class = instance._type_renderers.get(file_type)
            if renderer_class:
                logger.debug(f"Using type renderer for {file_type}: {renderer_class.__name__}")
                return renderer_class() if create_instance else renderer_class

        # 3. Try extension-based detection
        if file_path:
            guessed_type = cls._guess_file_type_from_extension(file_path)
            if guessed_type:
                renderer_class = instance._type_renderers.get(guessed_type)
                if renderer_class:
                    logger.debug(f"Using extension-based renderer for {file_path.suffix}: {renderer_class.__name__}")
                    return renderer_class() if create_instance else renderer_class

        # 4. Fallback to generic renderer
        logger.debug(f"Using fallback renderer for {tool_name}")
        return FallbackRenderer() if create_instance else FallbackRenderer

    @staticmethod
    def _guess_file_type_from_extension(file_path: Path) -> Optional[str]:
        """
        Guess file type from extension.

        Args:
            file_path: Path to file

        Returns:
            File type string or None
        """
        ext = file_path.suffix.lower()

        # Image extensions
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp']:
            return 'image'

        # Text extensions
        if ext in ['.txt', '.md', '.rst']:
            return 'text'

        # JSON extensions
        if ext in ['.json', '.jsonl']:
            return 'json'

        # Document extensions
        if ext in ['.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt']:
            return 'document'

        # SVG
        if ext == '.svg':
            return 'svg'

        return None

    @classmethod
    def list_registered_tools(cls) -> list[str]:
        """List all registered tool names"""
        instance = cls()
        return list(instance._renderers.keys())

    @classmethod
    def list_registered_types(cls) -> list[str]:
        """List all registered file types"""
        instance = cls()
        return list(instance._type_renderers.keys())

    @classmethod
    def clear(cls):
        """Clear all registrations (useful for testing)"""
        instance = cls()
        instance._renderers.clear()
        instance._type_renderers.clear()
        logger.info("Cleared RendererRegistry")

    @classmethod
    def reset(cls):
        """Reset to default state"""
        instance = cls()
        instance._initialize()
        logger.info("Reset RendererRegistry to defaults")


# Auto-initialize on import
_registry = RendererRegistry()
