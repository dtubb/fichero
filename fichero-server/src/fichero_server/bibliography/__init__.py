"""Bibliographic metadata extraction (#908)."""

from fichero_server.bibliography.extractor import (
    extract_from_pdf_metadata,
    extract_full,
)

__all__ = ["extract_from_pdf_metadata", "extract_full"]
