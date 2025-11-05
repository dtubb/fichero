"""
TranscribeRenderer - Renderer for transcription tool output (transcribe_qwen_max, transcribe_lmstudio)

Extends TextRenderer to display transcribed text alongside original image.
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import TextRenderer

logger = logging.getLogger(__name__)


class TranscribeRenderer(TextRenderer):
    """
    Renderer for transcription tool output.

    Handles both transcribe_qwen_max and transcribe_lmstudio outputs.
    Displays side-by-side view of image and transcribed text.

    Example manifest entry:
        {
            "path": "transcriptions/text.txt",
            "type": "file",
            "model": "qwen-max",
            "prompt_template": "transcribe_historical",
            "max_tokens": 4000,
            "temperature": 0.1,
            "language": "es"
        }
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """
        Render transcription with side-by-side image and text view.

        Shows original image on left, transcribed text on right.
        """
        # For transcriptions, we want custom HTML with side-by-side layout
        from ..html_templates import get_text_file_viewer

        # Read transcription text
        transcription_text = ""
        if context.file_path and context.file_path.exists():
            try:
                transcription_text = context.file_path.read_text(encoding='utf-8')
            except Exception as e:
                logger.error(f"Error reading transcription: {e}")
                transcription_text = f"Error reading file: {e}"

        # Create HTML with transcription text
        html = get_text_file_viewer(
            text_content=transcription_text,
            title=f"Transcription: {context.file_path.name if context.file_path else 'Unknown'}",
            syntax_highlighting=False  # Plain text, not code
        )

        return RenderedOutput(
            html=html,
            title=context.step_name,
            description=f"Transcribed text"
        )

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """Render transcription info for CLI"""
        text_parts = []

        text_parts.append(f"Step {context.step_index}: {context.step_name}")
        text_parts.append("=" * 60)
        text_parts.append("")
        text_parts.append(f"File: {context.file_path}")
        text_parts.append(f"Type: {context.file_type}")
        text_parts.append("")

        if context.manifest_entry:
            data = self._extract_transcribe_data(context.manifest_entry)
            text_parts.append("Transcription Parameters:")
            text_parts.append(f"  Model: {data.get('model', 'qwen-max')}")
            text_parts.append(f"  Prompt Template: {data.get('prompt_template', 'default')}")
            text_parts.append(f"  Max Tokens: {data.get('max_tokens', 4000)}")
            text_parts.append(f"  Temperature: {data.get('temperature', 0.1)}")
            if 'language' in data:
                text_parts.append(f"  Language: {data['language']}")
            text_parts.append("")

        # Show transcription text
        if context.file_path and context.file_path.exists():
            try:
                transcription = context.file_path.read_text(encoding='utf-8')
                text_parts.append("Transcription:")
                text_parts.append("-" * 60)
                # Show first 500 chars
                if len(transcription) > 500:
                    text_parts.append(transcription[:500] + "...")
                else:
                    text_parts.append(transcription)
                text_parts.append("-" * 60)
            except Exception as e:
                text_parts.append(f"Error reading transcription: {e}")

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description="Transcribed text"
        )

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """Get editable JSON for transcription parameters"""
        if not context.manifest_entry:
            return None
        return self._extract_transcribe_data(context.manifest_entry)

    def _extract_transcribe_data(self, manifest_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract transcription-specific data"""
        data = {
            'model': manifest_entry.get('model', 'qwen-max'),
            'prompt_template': manifest_entry.get('prompt_template', 'default'),
            'max_tokens': manifest_entry.get('max_tokens', 4000),
            'temperature': manifest_entry.get('temperature', 0.1)
        }

        if 'language' in manifest_entry:
            data['language'] = manifest_entry['language']

        return data

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate transcription JSON"""
        if 'model' in json_data:
            model = json_data['model']
            valid_models = ['qwen-max', 'qwen-plus', 'lmstudio']
            if model not in valid_models:
                return False, f"model must be one of {valid_models}"

        if 'max_tokens' in json_data:
            tokens = json_data['max_tokens']
            if not isinstance(tokens, int) or tokens < 1 or tokens > 32000:
                return False, "max_tokens must be 1-32000"

        if 'temperature' in json_data:
            temp = json_data['temperature']
            if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                return False, "temperature must be 0-2"

        return True, None

    def apply_json_edits(self, context: RenderContext, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Apply edited transcription parameters"""
        is_valid, error = self.validate_json(json_data)
        if not is_valid:
            return False, error

        logger.info(f"Would re-transcribe with: {json.dumps(json_data, indent=2)}")
        return False, "Re-transcription not implemented yet"
