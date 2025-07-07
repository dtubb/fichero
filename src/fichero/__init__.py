"""
Fichero - Document Processing and Transcription
"""

# Simple static version - works in all environments including Briefcase apps
__version__ = "0.1.0-dev"

from .app import main as gui_main

__all__ = ['gui_main', '__version__'] 