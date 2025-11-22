"""
StandardTool - Base class for all processing tools

Provides a unified interface that all tools must implement to work with
the ToolExecutionService. Follows crop's proven pattern for library
backend integration.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of tool execution"""
    success: bool
    output_path: Optional[Path] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate result state"""
        if self.success and not self.output_path:
            logger.warning("Tool reported success but no output_path provided")
        if not self.success and not self.error:
            logger.warning("Tool reported failure but no error message provided")


class StandardTool(ABC):
    """
    Base class for all processing tools.

    Enforces consistent interface following crop's pattern:
    1. Validate parameters
    2. Process source file
    3. Save to output path
    4. Create manifest entry
    5. Return metadata for library database

    All tools must implement this interface to work with ToolExecutionService.
    """

    def __init__(self):
        """Initialize the tool"""
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def get_tool_name(self) -> str:
        """
        Return the tool's identifier.

        This should match the tool's folder name in the Director output structure.
        Examples: 'crop', 'enhance', 'rotate', 'transcribe'

        Returns:
            Tool name string (lowercase, no spaces)
        """
        pass

    @abstractmethod
    def get_manifest_folder(self) -> str:
        """
        Return the folder name for this tool's outputs.

        This determines where outputs are stored in the assets folder.
        Examples: 'cropped', 'enhanced', 'rotated', 'transcriptions'

        Returns:
            Folder name string
        """
        pass

    @abstractmethod
    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate tool-specific parameters before execution.

        Args:
            parameters: Dictionary of tool-specific parameters

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if valid
            - (False, "error description") if invalid

        Example:
            >>> tool.validate_parameters({'method': 'auto', 'quality': 95})
            (True, None)
            >>> tool.validate_parameters({'method': 'invalid'})
            (False, "method must be 'auto' or 'manual'")
        """
        pass

    @abstractmethod
    async def process(
        self,
        source_path: Path,
        output_path: Path,
        parameters: Dict[str, Any]
    ) -> ToolResult:
        """
        Execute the tool on a source file.

        This is the main processing method. It should:
        1. Load the source file
        2. Apply the tool's transformation
        3. Save to output_path
        4. Return ToolResult with success status and metadata

        Args:
            source_path: Path to input file (already resolved by library backend)
            output_path: Path where output should be saved
            parameters: Tool-specific parameters (already validated)

        Returns:
            ToolResult with success status, output path, and metadata

        Example:
            >>> result = await tool.process(
            ...     source_path=Path('/input/image.jpg'),
            ...     output_path=Path('/output/image.jpg'),
            ...     parameters={'method': 'auto'}
            ... )
            >>> result.success
            True
            >>> result.output_path
            Path('/output/image.jpg')
        """
        pass

    @abstractmethod
    def create_manifest_entry(
        self,
        source_path: Path,
        output_path: Path,
        parameters: Dict[str, Any],
        result: ToolResult
    ) -> Dict[str, Any]:
        """
        Create a manifest entry for this tool execution.

        The manifest entry will be written as a JSONL line in the tool's manifest file.
        It should contain all information needed to understand and reproduce this execution.

        Standard fields (all tools should include):
        - path: Relative path to output file (str)
        - source: Source filename for library backend path resolution (str)
        - type: "file" or "directory" (str)
        - details: Tool-specific results (dict)
        - metadata: Additional info like timestamps (dict)

        Library backend will enrich with:
        - source_image_path: Absolute path to source (added by library backend)

        Args:
            source_path: Path to source file that was processed
            output_path: Path to output file that was created
            parameters: Parameters that were used
            result: ToolResult from process() method

        Returns:
            Dictionary to be written as JSONL line

        Example:
            >>> entry = tool.create_manifest_entry(
            ...     source_path=Path('/input/image.jpg'),
            ...     output_path=Path('/output/cropped/image.jpg'),
            ...     parameters={'box': {'x1': 0, 'y1': 0, 'x2': 100, 'y2': 100}},
            ...     result=ToolResult(success=True, output_path=Path(...))
            ... )
            >>> entry
            {
                'path': 'image.jpg',
                'source': 'image.jpg',
                'type': 'file',
                'details': {
                    'box': {'x1': 0, 'y1': 0, 'x2': 100, 'y2': 100},
                    'method': 'manual'
                },
                'metadata': {
                    'timestamp': '2025-01-18T10:30:00',
                    'execution_mode': 'interactive'
                }
            }
        """
        pass

    def get_default_parameters(self) -> Dict[str, Any]:
        """
        Get default parameters for this tool.

        Override this to provide sensible defaults for your tool.
        These will be used if the user doesn't specify parameters.

        Returns:
            Dictionary of default parameters

        Example:
            >>> tool.get_default_parameters()
            {'method': 'auto', 'quality': 95}
        """
        return {}

    def supports_batch_processing(self) -> bool:
        """
        Whether this tool can process multiple files at once.

        Override this to return True if your tool has a batch mode.
        Default is False (single file at a time).

        Returns:
            True if batch processing is supported
        """
        return False

    def get_supported_input_formats(self) -> list[str]:
        """
        Get list of supported input file formats.

        Override this to specify which file formats this tool accepts.
        Use lowercase extensions without dots.

        Returns:
            List of supported extensions

        Example:
            >>> tool.get_supported_input_formats()
            ['jpg', 'jpeg', 'png', 'tif', 'tiff']
        """
        return []  # Empty list means "accept all"

    def get_output_format(self, parameters: Dict[str, Any]) -> str:
        """
        Get the output format for given parameters.

        Override this to specify what format the tool outputs.
        Default is 'jpg'.

        Args:
            parameters: Tool parameters that might affect output format

        Returns:
            Output format extension (without dot)

        Example:
            >>> tool.get_output_format({'format': 'png'})
            'png'
        """
        return 'jpg'

    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"<{self.__class__.__name__}: {self.get_tool_name()}>"
