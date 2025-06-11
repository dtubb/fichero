"""
Fichero - Document Processing and Transcription
"""

__version__ = "0.1.0"

from .app import main as gui_main
from .cli import main as cli_main

__all__ = ['gui_main', 'cli_main'] 