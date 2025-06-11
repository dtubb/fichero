"""
Entry point for Fichero - handles both GUI and CLI modes
"""

import sys
from .app import main as gui_main

def main():
    # If no arguments are provided, run in GUI mode
    if len(sys.argv) == 1:
        app = gui_main()
        app.main_loop()
    else:
        # Only import CLI when actually needed (lazy import)
        from .cli import app as typer_app
        typer_app()

if __name__ == "__main__":
    main() 