"""
CLI version that passes through to the director
"""

import typer
from rich.console import Console
from .director import cli as director_cli

app = typer.Typer(help="Fichero CLI - Document Processing and Transcription")
console = Console()

# Add all the director commands to our CLI app
app.add_typer(director_cli, name="")

def main():
    """Main CLI entry point"""
    app()

if __name__ == "__main__":
    main() 