"""
Entry point for Fichero - handles both GUI and CLI modes

Briefcase usage:
    briefcase dev (gui)
    briefcase dev -- --help (cli)

Direct Python usage:
    python -m fichero (gui - no args)
    python -m fichero --help (cli - with args)
"""

import sys

def main():
    # No arguments = GUI mode
    if len(sys.argv) == 1:
        from fichero.app import main as gui_main
        gui_main()

    # Arguments present = CLI mode
    else:
        from fichero.cli import app as typer_app
        typer_app()

if __name__ == "__main__":
    main() 