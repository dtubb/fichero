"""
JSON Editor

Editor for JSON outputs (transcriptions, catalogues, etc.)
"""

import json
from pathlib import Path
from typing import Any

from .base_editor import BaseToolEditor


class JSONEditor(BaseToolEditor):
    """
    Editor for JSON output files.

    Handles:
    - Transcription outputs (.json)
    - Catalogue outputs (.json)
    - Any JSON-based tool output
    """

    tool_name = "json"
    supported_extensions = ['.json']
    can_edit_files = True

    def can_edit(self, file_path: Path) -> bool:
        """Check if file is a JSON file"""
        return file_path.suffix.lower() in self.supported_extensions

    def load_content(self, file_path: Path) -> dict:
        """
        Load JSON content from file.

        Args:
            file_path: Path to JSON file

        Returns:
            Parsed JSON as dictionary

        Raises:
            json.JSONDecodeError: If file is not valid JSON
            FileNotFoundError: If file doesn't exist
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_content(self, file_path: Path, content: dict) -> bool:
        """
        Save JSON content to file.

        Args:
            file_path: Path to JSON file
            content: Dictionary to save as JSON

        Returns:
            True if save successful
        """
        try:
            # Validate content first
            is_valid, error = self.validate_content(content)
            if not is_valid:
                self.logger.error(f"Invalid content: {error}")
                return False

            # Write to temp file first (atomic write)
            temp_path = file_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=2, ensure_ascii=False)

            # Move temp file to actual file
            temp_path.replace(file_path)

            self.logger.info(f"Saved JSON to {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save JSON: {e}")
            return False

    def validate_content(self, content: Any) -> tuple[bool, str]:
        """
        Validate JSON content.

        Args:
            content: Content to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if content is JSON-serializable
        try:
            json.dumps(content)
            return True, ""
        except (TypeError, ValueError) as e:
            return False, f"Content is not JSON-serializable: {e}"

    def pretty_format(self, content: dict) -> str:
        """
        Format JSON content as pretty string.

        Args:
            content: JSON content

        Returns:
            Pretty-formatted JSON string
        """
        return json.dumps(content, indent=2, ensure_ascii=False)

    def extract_text(self, content: dict) -> str:
        """
        Extract text from transcription JSON.

        Handles common transcription formats.

        Args:
            content: JSON content

        Returns:
            Extracted text or empty string
        """
        # Try common text fields
        text_fields = ['text', 'transcription', 'content', 'result']

        for field in text_fields:
            if field in content:
                return str(content[field])

        # If no text field found, return string representation
        return str(content)
