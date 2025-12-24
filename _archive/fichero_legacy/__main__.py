"""
Fichero entry point

Usage:
    python -m fichero serve         # Start API server
    python -m fichero ingest ...    # CLI
    python -m fichero search ...    # CLI
"""

import sys


def main():
    # All args go to CLI (GUI is now Swift app)
    from fichero.cli import app
    app()


if __name__ == "__main__":
    main()
