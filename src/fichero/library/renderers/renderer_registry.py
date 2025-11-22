"""
RendererRegistry - Central registry for tool renderers

Maps tool names to renderer classes and provides fallback behavior.
Supports auto-discovery of renderers and intelligent fallbacks based on file type.
"""

import logging
from typing import Dict, Type, Optional
from pathlib import Path

from .base_renderer import BaseRenderer, FallbackRenderer
# SIMPLIFIED: Only 2 universal renderers needed
from .universal_image_renderer import UniversalImageRenderer
from .universal_metadata_renderer import UniversalMetadataRenderer

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
        """Initialize registry with SIMPLIFIED universal renderers"""
        logger.info("Initializing RendererRegistry (SIMPLIFIED - 2 universal renderers)")

        # Clear registries
        self._renderers = {}
        self._type_renderers = {}

        # Import universal renderers
        from .universal_image_renderer import UniversalImageRenderer
        from .type_renderers import JsonRenderer, TextRenderer

        # Register ONLY 2 universal renderers
        # UniversalImageRenderer handles ALL visual content
        self._type_renderers['image'] = UniversalImageRenderer
        self._type_renderers['photo'] = UniversalImageRenderer
        self._type_renderers['picture'] = UniversalImageRenderer
        self._type_renderers['pdf'] = UniversalImageRenderer

        # Use working concrete renderers for text/data content
        self._type_renderers['text'] = TextRenderer
        self._type_renderers['json'] = JsonRenderer
        self._type_renderers['transcription'] = TextRenderer
        self._type_renderers['metadata'] = JsonRenderer
        self._type_renderers['csv'] = TextRenderer

        # Register universal renderers for ALL tool names
        # This ensures get_renderer() works for any tool
        self._renderers['original'] = UniversalImageRenderer
        self._renderers['crop'] = UniversalImageRenderer
        self._renderers['rotate'] = UniversalImageRenderer
        self._renderers['enhance'] = UniversalImageRenderer
        self._renderers['segment'] = UniversalImageRenderer
        self._renderers['split'] = UniversalImageRenderer
        self._renderers['remove_background'] = UniversalImageRenderer
        self._renderers['prepare_images'] = UniversalImageRenderer
        self._renderers['recombine_segments'] = UniversalImageRenderer

        self._renderers['transcribe_qwen_max'] = TextRenderer
        self._renderers['transcribe_lmstudio'] = TextRenderer
        self._renderers['describe_images'] = TextRenderer
        self._renderers['llm_process'] = JsonRenderer
        self._renderers['extract_library_metadata'] = JsonRenderer
        self._renderers['fuzzy_clean'] = JsonRenderer
        self._renderers['analyze_document_groups'] = JsonRenderer
        self._renderers['json_to_word'] = JsonRenderer
        self._renderers['json_to_excel'] = JsonRenderer
        self._renderers['convert_to_word'] = JsonRenderer
        self._renderers['convert_to_svg'] = JsonRenderer
        self._renderers['build_documents_manifest'] = JsonRenderer

        logger.info(f"✅ Registered SIMPLIFIED renderer system:")
        logger.info(f"   - {len([k for k,v in self._renderers.items() if v == UniversalImageRenderer])} image tools → UniversalImageRenderer")
        logger.info(f"   - {len([k for k,v in self._renderers.items() if v == TextRenderer])} text tools → TextRenderer")
        logger.info(f"   - {len([k for k,v in self._renderers.items() if v == JsonRenderer])} JSON tools → JsonRenderer")

        # OLD COMPLEX SYSTEM REMOVED - No more 20+ specialized renderers!
        # self._register_tool_renderers()  # DELETED

    # OLD METHOD DELETED - No longer needed with universal renderers
    # def _register_tool_renderers(self): ...

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
