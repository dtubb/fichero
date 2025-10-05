"""
Workflow Outputs Manager

Manages processing outputs, enabling viewing, editing, and re-running workflows.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ToolOutput:
    """Represents outputs from a single tool"""
    tool_name: str
    output_folder: Path
    manifest_path: Path
    _files: Optional[List[Path]] = field(default=None, init=False, repr=False)
    _parameters: Optional[Dict[str, Any]] = field(default=None, init=False, repr=False)

    @property
    def files(self) -> List[Path]:
        """Get list of output files (excluding manifest)"""
        if self._files is None:
            self._files = []
            if self.output_folder.exists():
                # Get all files except the manifest itself
                for file_path in self.output_folder.iterdir():
                    if file_path.is_file() and file_path != self.manifest_path:
                        self._files.append(file_path)
            self._files.sort()
        return self._files

    @property
    def parameters(self) -> Dict[str, Any]:
        """Extract tool parameters from first manifest entry"""
        if self._parameters is None:
            self._parameters = {}
            if self.manifest_path.exists():
                try:
                    with open(self.manifest_path, 'r') as f:
                        # Read first line to get parameters
                        first_line = f.readline().strip()
                        if first_line:
                            entry = json.loads(first_line)
                            # Extract params if available
                            if 'params' in entry:
                                self._parameters = entry['params']
                            else:
                                # Fall back to using the whole entry as params
                                # Filter out source/output/tool metadata
                                self._parameters = {
                                    k: v for k, v in entry.items()
                                    if k not in ['source', 'output', 'tool']
                                }
                except Exception as e:
                    logger.warning(f"Could not read parameters from {self.manifest_path}: {e}")
        return self._parameters


@dataclass
class OutputSession:
    """Represents a loaded output folder session"""
    output_path: Path
    _tools: Optional[List[ToolOutput]] = field(default=None, init=False, repr=False)


class OutputsManager:
    """
    Manages workflow outputs for viewing, editing, and re-processing.

    Provides:
    - Navigation through tool outputs
    - Tool parameter extraction
    - File listing and access
    - Foundation for editing and re-running
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def load_output_folder(self, output_path: Path) -> OutputSession:
        """
        Load a Director output folder

        Args:
            output_path: Path to the Director output folder

        Returns:
            OutputSession with discovered tools

        Raises:
            FileNotFoundError: If output_path doesn't exist
        """
        output_path = Path(output_path)

        if not output_path.exists():
            raise FileNotFoundError(f"Output folder not found: {output_path}")

        self.logger.info(f"Loading output folder: {output_path}")

        session = OutputSession(output_path=output_path)

        return session

    def list_tools(self, session: OutputSession) -> List[ToolOutput]:
        """
        List all tools that produced outputs in this session

        Args:
            session: OutputSession to scan

        Returns:
            List of ToolOutput objects
        """
        if session._tools is not None:
            return session._tools

        tools = []

        # Scan for manifests to discover tools
        # Check common locations

        # 1. Check assets/manifests/ folder
        manifests_dir = session.output_path / "assets" / "manifests"
        if manifests_dir.exists():
            for manifest_file in manifests_dir.glob("*_manifest.jsonl"):
                tool_name = self._extract_tool_name_from_manifest(manifest_file)
                if tool_name:
                    # Determine output folder based on manifest name
                    output_folder = self._find_output_folder_for_tool(session.output_path, tool_name, manifest_file)
                    if output_folder:
                        tools.append(ToolOutput(
                            tool_name=tool_name,
                            output_folder=output_folder,
                            manifest_path=manifest_file
                        ))

        # 2. Check for manifests in output folders
        assets_dir = session.output_path / "assets"
        if assets_dir.exists():
            for subfolder in assets_dir.iterdir():
                if subfolder.is_dir() and subfolder.name != "manifests":
                    # Look for manifest in this folder
                    for manifest_file in subfolder.glob("*_manifest.jsonl"):
                        tool_name = self._extract_tool_name_from_manifest(manifest_file)
                        if tool_name:
                            # Check if not already added
                            if not any(t.tool_name == tool_name for t in tools):
                                tools.append(ToolOutput(
                                    tool_name=tool_name,
                                    output_folder=subfolder,
                                    manifest_path=manifest_file
                                ))

        session._tools = tools
        self.logger.info(f"Found {len(tools)} tool outputs")

        return tools

    def get_tool_output(self, session: OutputSession, tool_name: str) -> Optional[ToolOutput]:
        """
        Get outputs for a specific tool

        Args:
            session: OutputSession
            tool_name: Name of the tool

        Returns:
            ToolOutput if found, None otherwise
        """
        tools = self.list_tools(session)

        for tool in tools:
            if tool.tool_name == tool_name:
                return tool

        self.logger.warning(f"Tool '{tool_name}' not found in outputs")
        return None

    def _extract_tool_name_from_manifest(self, manifest_path: Path) -> Optional[str]:
        """Extract tool name from manifest file"""
        # Try to read tool name from manifest content
        try:
            with open(manifest_path, 'r') as f:
                first_line = f.readline().strip()
                if first_line:
                    entry = json.loads(first_line)
                    if 'tool' in entry:
                        return entry['tool']
        except Exception as e:
            self.logger.debug(f"Could not read tool from manifest {manifest_path}: {e}")

        # Fall back to inferring from filename
        # prepare_images_manifest.jsonl → prepare_images
        # transcriptions_manifest.jsonl → transcribe (need mapping)
        filename = manifest_path.stem  # Remove .jsonl

        # Handle common patterns
        if filename == "documents_manifest":
            return "build_documents_manifest"
        elif filename == "prepare_images_manifest":
            return "prepare_images"
        elif filename == "transcriptions_manifest":
            return "transcribe_qwen_max"
        elif filename == "llm_process_manifest":
            return "catalogue_folder"
        else:
            # Remove _manifest suffix
            if filename.endswith("_manifest"):
                return filename[:-9]  # Remove "_manifest"
            return filename

    def _find_output_folder_for_tool(self, output_path: Path, tool_name: str, manifest_path: Path) -> Optional[Path]:
        """Find the output folder for a tool"""
        # If manifest is in the output folder, use that folder
        if manifest_path.parent != output_path / "assets" / "manifests":
            return manifest_path.parent

        # Otherwise, map tool to expected output folder
        folder_map = {
            "build_documents_manifest": output_path / "assets" / "manifests",
            "prepare_images": output_path / "assets" / "prepared",
            "transcribe_qwen_max": output_path / "assets" / "transcriptions",
            "catalogue_folder": output_path / "assets" / "llm_catalogue",
            "convert_to_word": output_path / "assets" / "word",
            "catalogue_to_word": output_path / "assets" / "llm_catalogue_word"
        }

        if tool_name in folder_map and folder_map[tool_name].exists():
            return folder_map[tool_name]

        # Fall back to manifest location
        return manifest_path.parent
