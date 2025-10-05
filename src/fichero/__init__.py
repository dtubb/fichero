"""
Fichero - Document Processing and Transcription
"""

# Simple static version - works in all environments including Briefcase apps
__version__ = "0.1.0-dev"

# Lazy import gui_main to avoid requiring Toga in CLI mode
def __getattr__(name):
    if name == 'gui_main':
        from fichero.app import main as gui_main
        return gui_main
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = ['gui_main', '__version__'] 