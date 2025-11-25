"""
Transcription provider plugins for Fichero.

This package contains provider implementations for different OCR/transcription services:
- dashscope_provider: DashScope SDK (qwen-vl-max, qwen-vl-ocr)
- openai_provider: OpenAI-compatible API
- lmstudio_provider: Local LMStudio instance

Each provider implements a consistent interface for the main transcribe tool.
"""

from .base_provider import BaseTranscriptionProvider

__all__ = ['BaseTranscriptionProvider']
