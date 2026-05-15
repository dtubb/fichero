"""Fichero command-line client.

A thin HTTP-only client for the Fichero backend. It drives the same FastAPI
endpoints the SwiftUI app uses, so the backend can be exercised live without
the app. Contains no backend logic — every operation is one or two HTTP calls.
"""

from fichero.cli.client import DEFAULT_BASE_URL, FicheroClient, FicheroError

__all__ = ["FicheroClient", "FicheroError", "DEFAULT_BASE_URL"]
