"""
Entry point for Fichero - handles both GUI and CLI modes
Run with:
    briefcase dev (gui)
    briefcase dev -- --help (cli)
    python -m fichero --help (cli)
"""

import sys
from .app import main as gui_main

def main():
    # If no arguments are provided, run in GUI mode, using app.py
    if len(sys.argv) == 1:
        gui_main()  # This already calls app.main_loop() internally

    else:
        # If arguments are provided, run in CLI mode using cli.py
        # Only import CLI when actually needed (lazy import)
        # e.g. briefcase dev -- --help
        # briefcase dev -- --help
        # Requires -- to separate briefcase arguments from typer arguments

        from .cli import app as typer_app
        typer_app()

if __name__ == "__main__":
    main() 